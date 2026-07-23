from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests


class TuyaAPIError(Exception):
    def __init__(self, message: str, *, code: int | str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass
class TuyaToken:
    access_token: str
    expires_at: float


class TuyaService:
    """Backend-only Tuya OpenAPI integration service."""

    TOKEN_CACHE_KEY = "tuya:access_token"

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        device_id: str,
        timeout_seconds: int = 10,
        max_retries: int = 3,
        redis_url: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.device_id = device_id
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.log = logging.getLogger("tuya")
        self._token: TuyaToken | None = None
        self._functions_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._redis = self._build_redis_client(redis_url)

    def _build_redis_client(self, redis_url: str | None):
        if not redis_url:
            return None
        try:
            import redis  # type: ignore

            return redis.Redis.from_url(redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover
            self._log("redis_unavailable", level="warning", error=str(exc))
            return None

    def is_configured(self) -> bool:
        return bool(self.base_url and self.client_id and self.client_secret and self.device_id)

    def _log(self, event: str, level: str = "info", **fields: Any) -> None:
        payload = {"event": event, **fields}
        getattr(self.log, level)(json.dumps(payload, ensure_ascii=True))

    def _hash_body(self, body: str) -> str:
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def _build_sign_payload(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> tuple[str, str, str, str]:
        timestamp = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        query_string = f"?{urlencode(query)}" if query else ""
        request_path = f"{path}{query_string}"
        body_text = ""
        if body is not None:
            body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=True)
        string_to_sign = f"{method.upper()}\n{self._hash_body(body_text)}\n\n{request_path}"
        return timestamp, nonce, string_to_sign, body_text

    def _sign(self, *, timestamp: str, nonce: str, string_to_sign: str, access_token: str = "") -> str:
        sign_content = f"{self.client_id}{access_token}{timestamp}{nonce}{string_to_sign}"
        return hmac.new(
            self.client_secret.encode("utf-8"),
            sign_content.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()

    def _cache_token(self, token: TuyaToken) -> None:
        self._token = token
        if not self._redis:
            return
        try:
            ttl = max(int(token.expires_at - time.time()), 1)
            self._redis.setex(self.TOKEN_CACHE_KEY, ttl, token.access_token)
        except Exception as exc:
            self._log("redis_set_failed", level="warning", error=str(exc))

    def _get_cached_token(self) -> TuyaToken | None:
        if self._token and self._token.expires_at > time.time() + 60:
            return self._token

        if not self._redis:
            return None

        try:
            token_value = self._redis.get(self.TOKEN_CACHE_KEY)
            if token_value:
                token = TuyaToken(access_token=token_value, expires_at=time.time() + 300)
                self._token = token
                return token
        except Exception as exc:
            self._log("redis_get_failed", level="warning", error=str(exc))
        return None

    def _request(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_token: bool = True,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise TuyaAPIError("Tuya is not configured")

        access_token = ""
        if use_token:
            token = self.get_access_token()
            access_token = token.access_token

        timestamp, nonce, string_to_sign, body_text = self._build_sign_payload(
            method=method,
            path=path,
            query=query,
            body=body,
        )
        signature = self._sign(
            timestamp=timestamp,
            nonce=nonce,
            string_to_sign=string_to_sign,
            access_token=access_token,
        )

        headers = {
            "client_id": self.client_id,
            "t": timestamp,
            "nonce": nonce,
            "sign": signature,
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json",
        }
        if access_token:
            headers["access_token"] = access_token

        url = f"{self.base_url}{path}"

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.request(
                    method=method.upper(),
                    url=url,
                    params=query,
                    data=body_text if body is not None else None,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    self._log("tuya_network_failure", level="error", error=str(exc), path=path)
                    raise TuyaAPIError("Tuya API network failure") from exc
                time.sleep(min(2 ** (attempt - 1), 4))
                continue

            payload = response.json() if response.content else {}
            if response.status_code >= 500 and attempt < self.max_retries:
                time.sleep(min(2 ** (attempt - 1), 4))
                continue

            if response.status_code >= 400:
                self._log(
                    "tuya_http_error",
                    level="error",
                    status=response.status_code,
                    path=path,
                    payload=payload,
                )
                raise TuyaAPIError(
                    payload.get("msg") or "Tuya API HTTP error",
                    code=payload.get("code"),
                    status_code=response.status_code,
                )

            if payload.get("success") is False:
                code = str(payload.get("code", ""))
                if use_token and code in {"1010", "1011", "1106", "28841002"} and attempt < self.max_retries:
                    self.invalidate_token()
                    access_token = self.get_access_token(force_refresh=True).access_token
                    headers["access_token"] = access_token
                    timestamp, nonce, string_to_sign, body_text = self._build_sign_payload(
                        method=method,
                        path=path,
                        query=query,
                        body=body,
                    )
                    headers["t"] = timestamp
                    headers["nonce"] = nonce
                    headers["sign"] = self._sign(
                        timestamp=timestamp,
                        nonce=nonce,
                        string_to_sign=string_to_sign,
                        access_token=access_token,
                    )
                    time.sleep(min(2 ** (attempt - 1), 4))
                    continue

                raise TuyaAPIError(
                    payload.get("msg") or "Tuya API business failure",
                    code=payload.get("code"),
                    status_code=response.status_code,
                )

            self._log("tuya_api_success", path=path, method=method.upper(), code=payload.get("code"))
            return payload.get("result", {})

        raise TuyaAPIError("Tuya API request failed after retries")

    def invalidate_token(self) -> None:
        self._token = None
        if self._redis:
            try:
                self._redis.delete(self.TOKEN_CACHE_KEY)
            except Exception:
                pass

    def get_access_token(self, *, force_refresh: bool = False) -> TuyaToken:
        if not force_refresh:
            cached = self._get_cached_token()
            if cached:
                return cached

        result = self._request(
            method="GET",
            path="/v1.0/token",
            query={"grant_type": 1},
            use_token=False,
        )
        access_token = result.get("access_token")
        expire_seconds = int(result.get("expire_time", 3600))
        if not access_token:
            raise TuyaAPIError("Tuya token response missing access_token")

        token = TuyaToken(access_token=access_token, expires_at=time.time() + max(expire_seconds - 60, 60))
        self._cache_token(token)
        self._log("tuya_token_generated", expires_in=expire_seconds)
        return token

    def discover_device(self, device_id: str | None = None) -> dict[str, Any]:
        device_id = device_id or self.device_id
        return self._request(method="GET", path=f"/v1.0/devices/{device_id}")

    def get_device_functions(self, device_id: str | None = None, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        device_id = device_id or self.device_id
        if self._functions_cache and not force_refresh and self._functions_cache[0] > time.time():
            return self._functions_cache[1]

        result = self._request(method="GET", path=f"/v1.0/devices/{device_id}/functions")
        functions = result.get("functions", []) if isinstance(result, dict) else []
        self._functions_cache = (time.time() + 300, functions)
        return functions

    def get_device_status(self, device_id: str | None = None) -> list[dict[str, Any]]:
        device_id = device_id or self.device_id
        result = self._request(method="GET", path=f"/v1.0/devices/{device_id}/status")
        return result if isinstance(result, list) else result.get("status", [])

    def get_device_properties(self, device_id: str | None = None) -> dict[str, Any]:
        device_id = device_id or self.device_id
        result = self._request(method="GET", path=f"/v1.0/devices/{device_id}/specifications")
        return result

    def _resolve_switch_codes(self, device_id: str | None = None) -> list[str]:
        functions = self.get_device_functions(device_id)
        switch_codes: list[str] = []
        for item in functions:
            code = str(item.get("code", "")).strip()
            value_type = str(item.get("type", "")).lower()
            if not code:
                continue
            if "switch" in code.lower() and value_type in {"bool", "boolean"}:
                switch_codes.append(code)

        if not switch_codes:
            raise TuyaAPIError("No switch command codes discovered from Tuya capabilities")

        switch_codes = sorted(set(switch_codes))
        return switch_codes

    def control_device(
        self,
        *,
        commands: list[dict[str, Any]],
        device_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        device_id = device_id or self.device_id
        body = {"commands": commands}
        if request_id:
            body["request_id"] = request_id

        self._log("tuya_command_sent", device_id=device_id, request_id=request_id, commands=commands)
        result = self._request(method="POST", path=f"/v1.0/devices/{device_id}/commands", body=body)
        self._log("tuya_command_result", device_id=device_id, request_id=request_id, result=result)
        return result

    def turn_switch(self, switch_index: int, on: bool, *, request_id: str | None = None) -> dict[str, Any]:
        switch_codes = self._resolve_switch_codes(self.device_id)
        if switch_index < 1 or switch_index > len(switch_codes):
            raise TuyaAPIError(f"Switch channel {switch_index} is not available")
        switch_code = switch_codes[switch_index - 1]
        return self.control_device(
            device_id=self.device_id,
            request_id=request_id,
            commands=[{"code": switch_code, "value": bool(on)}],
        )

    def turn_switch1_on(self, *, request_id: str | None = None) -> dict[str, Any]:
        return self.turn_switch(1, True, request_id=request_id)

    def turn_switch1_off(self, *, request_id: str | None = None) -> dict[str, Any]:
        return self.turn_switch(1, False, request_id=request_id)

    def turn_switch2_on(self, *, request_id: str | None = None) -> dict[str, Any]:
        return self.turn_switch(2, True, request_id=request_id)

    def turn_switch2_off(self, *, request_id: str | None = None) -> dict[str, Any]:
        return self.turn_switch(2, False, request_id=request_id)

    def turn_all_on(self, *, request_id: str | None = None) -> dict[str, Any]:
        switch_codes = self._resolve_switch_codes(self.device_id)
        commands = [{"code": code, "value": True} for code in switch_codes]
        return self.control_device(device_id=self.device_id, commands=commands, request_id=request_id)

    def turn_all_off(self, *, request_id: str | None = None) -> dict[str, Any]:
        switch_codes = self._resolve_switch_codes(self.device_id)
        commands = [{"code": code, "value": False} for code in switch_codes]
        return self.control_device(device_id=self.device_id, commands=commands, request_id=request_id)

    def station_power_on(self, station: str, *, request_id: str | None = None) -> dict[str, Any]:
        station_key = station.strip().lower()
        if station_key in {"station1", "1", "switch1", "plug-001"}:
            return self.turn_switch1_on(request_id=request_id)
        if station_key in {"station2", "2", "switch2", "plug-002"}:
            return self.turn_switch2_on(request_id=request_id)
        raise TuyaAPIError("Invalid station value")

    def station_power_off(self, station: str, *, request_id: str | None = None) -> dict[str, Any]:
        station_key = station.strip().lower()
        if station_key in {"station1", "1", "switch1", "plug-001"}:
            return self.turn_switch1_off(request_id=request_id)
        if station_key in {"station2", "2", "switch2", "plug-002"}:
            return self.turn_switch2_off(request_id=request_id)
        raise TuyaAPIError("Invalid station value")


def build_tuya_service_from_env() -> TuyaService:
    return TuyaService(
        base_url=os.getenv("TUYA_BASE_URL", "https://openapi.tuya.com"),
        client_id=os.getenv("TUYA_CLIENT_ID", ""),
        client_secret=os.getenv("TUYA_CLIENT_SECRET", ""),
        device_id=os.getenv("TUYA_DEVICE_ID", ""),
        timeout_seconds=int(os.getenv("TUYA_TIMEOUT_SECONDS", "10")),
        max_retries=int(os.getenv("TUYA_MAX_RETRIES", "3")),
        redis_url=os.getenv("REDIS_URL", "") or None,
    )
