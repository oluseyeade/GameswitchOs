from __future__ import annotations

import json
import uuid
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from services import TuyaAPIError


def create_user_blueprints(
    db,
    User,
    Game,
    Payment,
    GamingSession,
    LoginHistory,
    Notification,
    ALLOWED_BRANCHES,
    ADMIN_ROLES,
    current_user,
    login_required,
    user_can_manage_branch,
    get_redirect_for_role,
    money,
    tuya_service,
    event_bus,
    TuyaDevice,
    TuyaDeviceStatus,
    TuyaCommandHistory,
    TuyaEventLog,
    AuditLog,
):
    user_bp = Blueprint("user", __name__, url_prefix="/user")
    user_api_bp = Blueprint("user_api", __name__, url_prefix="/api/user")

    def _user_channel(user_id: int) -> str:
        return f"user:{user_id}"

    def _publish_user_event(user_id: int, event_type: str, payload: dict):
        event_bus.publish(_user_channel(user_id), {"type": event_type, "payload": payload})

    def _station_to_plug(station: str) -> str:
        station_key = station.strip().lower()
        if station_key in {"station1", "1", "switch1", "plug-001"}:
            return "plug-001"
        if station_key in {"station2", "2", "switch2", "plug-002"}:
            return "plug-002"
        return station_key

    def _plug_to_station(plug_id: str) -> str:
        value = (plug_id or "").strip().lower()
        if value in {"plug-001", "station1", "switch1", "1"}:
            return "station1"
        if value in {"plug-002", "station2", "switch2", "2"}:
            return "station2"
        return "station1"

    def _record_audit(actor_user_id: int | None, action: str, entity_type: str, entity_id: str | None, metadata: dict):
        db.session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata_json=json.dumps(metadata, ensure_ascii=True),
            )
        )

    def _upsert_device_from_discovery(device_payload: dict):
        device_id = str(device_payload.get("id") or device_payload.get("device_id") or tuya_service.device_id)
        record = TuyaDevice.query.filter_by(device_id=device_id).first()
        if not record:
            record = TuyaDevice(device_id=device_id)
            db.session.add(record)

        record.name = device_payload.get("name")
        record.product_id = device_payload.get("product_id")
        record.category = device_payload.get("category")
        record.is_online = bool(device_payload.get("online", record.is_online))
        record.last_seen_at = datetime.utcnow()
        return record

    def _upsert_status_rows(device_id: str, status_rows: list[dict]):
        for row in status_rows:
            code = str(row.get("code", "")).strip()
            if not code:
                continue
            value = row.get("value")
            status = TuyaDeviceStatus.query.filter_by(device_id=device_id, code=code).first()
            if not status:
                status = TuyaDeviceStatus(device_id=device_id, code=code)
                db.session.add(status)
            status.value_text = str(value) if value is not None else None
            status.value_bool = value if isinstance(value, bool) else None
            status.value_number = float(value) if isinstance(value, (int, float)) else None
            status.last_updated_at = datetime.utcnow()

    def _create_command_history(
        request_id: str,
        station: str,
        session_id: int | None,
        user_id: int | None,
        command_payload: dict,
        success: bool,
        response_payload: dict | None,
    ):
        db.session.add(
            TuyaCommandHistory(
                device_id=tuya_service.device_id,
                session_id=session_id,
                user_id=user_id,
                request_id=request_id,
                station=station,
                command_json=json.dumps(command_payload, ensure_ascii=True),
                success=success,
                response_json=json.dumps(response_payload or {}, ensure_ascii=True),
            )
        )

    def _execute_station_power(*, station: str, turn_on: bool, request_id: str) -> dict:
        try:
            if turn_on:
                return tuya_service.station_power_on(station, request_id=request_id)
            return tuya_service.station_power_off(station, request_id=request_id)
        except TuyaAPIError as exc:
            raise TuyaAPIError(f"Device command failed: {exc}", code=exc.code, status_code=exc.status_code) from exc

    def _build_session_payload(game_session):
        return {
            "id": game_session.id,
            "status": game_session.status,
            "remaining_seconds": game_session.remaining_seconds,
            "duration_seconds": game_session.duration_seconds,
            "branch": game_session.branch,
            "plug_id": game_session.plug_id,
            "station": _plug_to_station(game_session.plug_id),
        }

    def _check_station_available(station: str, branch: str) -> tuple[bool, str | None]:
        plug_id = _station_to_plug(station)
        active = GamingSession.query.filter_by(branch=branch, plug_id=plug_id, status="active").first()
        if active:
            return False, "Selected station already has an active gaming session."

        if not tuya_service.is_configured():
            return False, "Tuya integration is not configured."

        try:
            device = tuya_service.discover_device()
            if not bool(device.get("online", False)):
                return False, "Device is offline. Please try again later."

            status_rows = tuya_service.get_device_status()
            by_code = {
                str(item.get("code", "")).strip().lower(): item.get("value")
                for item in status_rows
                if str(item.get("code", "")).strip()
            }

            if station == "station1":
                switch_state = by_code.get("switch_1")
            elif station == "station2":
                switch_state = by_code.get("switch_2")
            else:
                switch_state = None

            if switch_state is True:
                return False, "Selected station switch is already ON."

            return True, None
        except TuyaAPIError as exc:
            return False, f"Unable to verify station availability: {exc}"

    @user_bp.route("/welcome")
    def welcome():
        return render_template("welcome.html")

    @user_bp.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "").strip()
            branch = request.form.get("branch", "branch1").strip().lower()

            if branch not in ALLOWED_BRANCHES:
                branch = "branch1"

            if not (full_name and email and phone and password):
                return render_template("register.html", error="All fields are required.")

            if User.query.filter_by(email=email).first():
                return render_template("register.html", error="Email already exists.")

            user = User(
                full_name=full_name,
                email=email,
                phone=phone,
                branch=branch,
                role="user",
                password_hash=generate_password_hash(password),
            )
            db.session.add(user)
            db.session.commit()
            return redirect(url_for("user.login"))

        return render_template("register.html")

    @user_bp.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()

            user = User.query.filter_by(email=email, is_active=True).first()
            if not user or not check_password_hash(user.password_hash, password):
                return render_template("login.html", error="Invalid email or password.")

            session["user_id"] = user.id
            session["user_role"] = user.role
            session["user_branch"] = user.branch

            db.session.add(LoginHistory(user_id=user.id, ip_address=request.remote_addr))
            db.session.commit()

            return redirect(get_redirect_for_role(user.role))

        return render_template("login.html")

    @user_bp.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("user.welcome"))

    @user_bp.route("/available-games")
    @login_required
    def available_games():
        games = (
            Game.query.filter_by(is_active=True, is_deleted=False, status="active")
            .order_by(Game.display_order.asc(), Game.title.asc())
            .all()
        )
        return render_template("available_games.html", games=games)

    @user_bp.route("/payment")
    @login_required
    def payment():
        games = (
            Game.query.filter_by(is_active=True, is_deleted=False, status="active")
            .order_by(Game.display_order.asc(), Game.title.asc())
            .all()
        )
        return render_template("payment.html", games=games)

    @user_bp.route("/session")
    @login_required
    def session_page():
        games = (
            Game.query.filter_by(is_active=True, is_deleted=False, status="active")
            .order_by(Game.display_order.asc(), Game.title.asc())
            .all()
        )
        return render_template("session.html", games=games)

    def _start_session_from_payload(user, data: dict):
        branch = str(data.get("branch", user.branch)).lower()
        if branch not in ALLOWED_BRANCHES:
            raise ValueError("Invalid branch")

        game_id = int(data.get("game_id", 0))
        duration_minutes = max(int(data.get("duration_minutes", 60)), 10)
        station = str(data.get("station") or _plug_to_station(str(data.get("plug_id", "plug-001")))).strip().lower()
        plug_id = _station_to_plug(station)
        payment_status = str(data.get("payment_status", "successful")).lower()

        game = Game.query.get(game_id)
        if not game or not game.is_active:
            raise LookupError("Selected game is unavailable")

        is_available, availability_error = _check_station_available(station, branch)
        if not is_available:
            raise ValueError(availability_error or "Station unavailable")

        amount = (money(game.price_per_hour) * duration_minutes) / 60
        payment = Payment(
            user_id=user.id,
            game_id=game.id,
            branch=branch,
            amount=amount,
            status="declined" if payment_status == "declined" else "successful",
            provider_ref=f"GS-{int(datetime.utcnow().timestamp())}-{user.id}",
        )
        db.session.add(payment)
        db.session.flush()

        if payment.status == "declined":
            db.session.add(
                Notification(
                    user_id=user.id,
                    branch=branch,
                    message="Payment declined. Please retry with another method.",
                )
            )
            _record_audit(user.id, "payment_declined", "payment", str(payment.id), {"branch": branch, "amount": amount})
            db.session.commit()
            return {
                "ok": True,
                "payment": {"id": payment.id, "status": payment.status, "amount": amount},
                "session": None,
                "switch": None,
            }

        request_id = request.headers.get("Idempotency-Key") or data.get("request_id") or str(uuid.uuid4())
        existing = TuyaCommandHistory.query.filter_by(request_id=request_id).first()
        if existing:
            response_payload = json.loads(existing.response_json or "{}")
            return {
                "ok": True,
                "payment": {"id": payment.id, "status": payment.status, "amount": amount},
                "session": None,
                "switch": response_payload,
                "message": "Duplicate command prevented via idempotency key.",
            }

        switch_result = _execute_station_power(station=station, turn_on=True, request_id=request_id)

        duration_seconds = duration_minutes * 60
        game_session = GamingSession(
            user_id=user.id,
            game_id=game.id,
            branch=branch,
            plug_id=plug_id,
            duration_seconds=duration_seconds,
            remaining_seconds=duration_seconds,
            status="active",
            payment_id=payment.id,
            started_at=datetime.utcnow(),
        )
        db.session.add(game_session)
        db.session.flush()

        _create_command_history(
            request_id=request_id,
            station=station,
            session_id=game_session.id,
            user_id=user.id,
            command_payload={"station": station, "power": True},
            success=True,
            response_payload=switch_result,
        )

        user.total_spent = money(user.total_spent) + amount
        db.session.add(
            Notification(
                user_id=user.id,
                branch=branch,
                message=f"Session started in {branch} for {game.title}.",
            )
        )
        _record_audit(
            user.id,
            "session_started",
            "gaming_session",
            str(game_session.id),
            {"branch": branch, "station": station, "amount": amount},
        )
        db.session.commit()

        session_payload = _build_session_payload(game_session)
        _publish_user_event(user.id, "session_started", session_payload)

        return {
            "ok": True,
            "payment": {"id": payment.id, "status": payment.status, "amount": amount},
            "session": session_payload,
            "switch": switch_result,
        }

    @user_api_bp.route("/payment/checkout", methods=["POST"])
    @login_required
    def api_checkout_payment():
        user = current_user()
        data = request.get_json(silent=True) or {}
        try:
            return jsonify(_start_session_from_payload(user, data))
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        except LookupError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 404
        except TuyaAPIError as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": str(exc), "code": exc.code}), 502
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Checkout failed: {exc}"}), 500

    @user_api_bp.route("/session/start", methods=["POST"])
    @login_required
    def api_start_session():
        user = current_user()
        data = request.get_json(silent=True) or {}
        data["payment_status"] = data.get("payment_status", "successful")
        try:
            return jsonify(_start_session_from_payload(user, data))
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        except LookupError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 404
        except TuyaAPIError as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": str(exc), "code": exc.code}), 502
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Session start failed: {exc}"}), 500

    @user_api_bp.route("/session/current", methods=["GET"])
    @login_required
    def api_get_current_session():
        user = current_user()
        game_session = (
            GamingSession.query.filter_by(user_id=user.id)
            .order_by(GamingSession.created_at.desc())
            .first()
        )
        if not game_session:
            return jsonify({"ok": True, "session": None})

        return jsonify({"ok": True, "session": _build_session_payload(game_session)})

    @user_api_bp.route("/session/<int:session_id>", methods=["GET"])
    @login_required
    def api_get_session(session_id: int):
        game_session = GamingSession.query.get_or_404(session_id)
        user = current_user()

        if user.role not in ADMIN_ROLES and game_session.user_id != user.id:
            return jsonify({"ok": False, "message": "Forbidden."}), 403

        return jsonify({"ok": True, **_build_session_payload(game_session)})

    @user_api_bp.route("/session/<int:session_id>/tick", methods=["POST"])
    @login_required
    def api_tick_session(session_id: int):
        game_session = GamingSession.query.get_or_404(session_id)
        user = current_user()
        if user.role not in ADMIN_ROLES and game_session.user_id != user.id:
            return jsonify({"ok": False, "message": "Forbidden."}), 403

        if game_session.status != "active":
            return jsonify({"ok": False, "message": "Session is not active."}), 400

        try:
            game_session.remaining_seconds = max(game_session.remaining_seconds - 1, 0)
            switch_result = None

            if game_session.remaining_seconds == 0:
                game_session.status = "ended"
                game_session.ended_at = datetime.utcnow()
                request_id = str(uuid.uuid4())
                station = _plug_to_station(game_session.plug_id)
                switch_result = _execute_station_power(station=station, turn_on=False, request_id=request_id)
                _create_command_history(
                    request_id=request_id,
                    station=station,
                    session_id=game_session.id,
                    user_id=game_session.user_id,
                    command_payload={"station": station, "power": False},
                    success=True,
                    response_payload=switch_result,
                )
                db.session.add(
                    Notification(
                        user_id=game_session.user_id,
                        branch=game_session.branch,
                        message=f"Session #{game_session.id} ended and smart switch was turned off.",
                    )
                )
                _record_audit(
                    user.id,
                    "session_auto_ended",
                    "gaming_session",
                    str(game_session.id),
                    {"branch": game_session.branch, "station": station},
                )

            db.session.commit()
            payload = _build_session_payload(game_session)
            _publish_user_event(game_session.user_id, "session_tick", payload)
            return jsonify({"ok": True, **payload, "switch": switch_result})
        except TuyaAPIError as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": str(exc), "code": exc.code}), 502
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Tick failed: {exc}"}), 500

    @user_api_bp.route("/session/<int:session_id>/adjust", methods=["PATCH"])
    @login_required
    def api_adjust_session(session_id: int):
        game_session = GamingSession.query.get_or_404(session_id)
        user = current_user()

        if user.role in {"admin1", "admin2", "superadmin"}:
            if not user_can_manage_branch(user, game_session.branch):
                return jsonify({"ok": False, "message": "Forbidden for this branch."}), 403
        elif game_session.user_id != user.id:
            return jsonify({"ok": False, "message": "Forbidden."}), 403

        data = request.get_json(silent=True) or {}
        delta_seconds = int(data.get("delta_seconds", 0))

        if game_session.status != "active":
            return jsonify({"ok": False, "message": "Session is not active."}), 400

        try:
            game_session.remaining_seconds = max(game_session.remaining_seconds + delta_seconds, 0)
            if game_session.remaining_seconds == 0:
                game_session.status = "ended"
                game_session.ended_at = datetime.utcnow()
                request_id = str(uuid.uuid4())
                station = _plug_to_station(game_session.plug_id)
                _execute_station_power(station=station, turn_on=False, request_id=request_id)
                _create_command_history(
                    request_id=request_id,
                    station=station,
                    session_id=game_session.id,
                    user_id=game_session.user_id,
                    command_payload={"station": station, "power": False},
                    success=True,
                    response_payload={"reason": "adjust_to_zero"},
                )

            db.session.commit()
            payload = _build_session_payload(game_session)
            _publish_user_event(game_session.user_id, "session_adjusted", payload)
            return jsonify({"ok": True, **payload})
        except TuyaAPIError as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": str(exc), "code": exc.code}), 502
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Adjust failed: {exc}"}), 500

    @user_api_bp.route("/session/<int:session_id>/stop", methods=["POST"])
    @login_required
    def api_stop_session(session_id: int):
        game_session = GamingSession.query.get_or_404(session_id)
        user = current_user()

        if user.role in {"admin1", "admin2", "superadmin"}:
            if not user_can_manage_branch(user, game_session.branch):
                return jsonify({"ok": False, "message": "Forbidden for this branch."}), 403
        elif game_session.user_id != user.id:
            return jsonify({"ok": False, "message": "Forbidden."}), 403

        if game_session.status == "ended":
            return jsonify({"ok": True, "message": "Already ended."})

        try:
            request_id = str(uuid.uuid4())
            station = _plug_to_station(game_session.plug_id)

            game_session.status = "ended"
            game_session.remaining_seconds = 0
            game_session.ended_at = datetime.utcnow()
            switch_result = _execute_station_power(station=station, turn_on=False, request_id=request_id)
            _create_command_history(
                request_id=request_id,
                station=station,
                session_id=game_session.id,
                user_id=game_session.user_id,
                command_payload={"station": station, "power": False},
                success=True,
                response_payload=switch_result,
            )
            _record_audit(user.id, "session_stopped", "gaming_session", str(game_session.id), {"station": station})
            db.session.commit()

            payload = _build_session_payload(game_session)
            _publish_user_event(game_session.user_id, "session_stopped", payload)
            return jsonify({"ok": True, **payload, "switch": switch_result})
        except TuyaAPIError as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": str(exc), "code": exc.code}), 502
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Stop failed: {exc}"}), 500

    @user_api_bp.route("/session/events", methods=["GET"])
    @login_required
    def api_session_events():
        user = current_user()
        return Response(
            stream_with_context(event_bus.stream(_user_channel(user.id))),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @user_api_bp.route("/device/status", methods=["GET"])
    @login_required
    def api_get_device_status():
        user = current_user()
        if not tuya_service.is_configured():
            return jsonify({"ok": False, "message": "Tuya integration is not configured."}), 503

        try:
            discovery = tuya_service.discover_device()
            status_rows = tuya_service.get_device_status()
            functions = tuya_service.get_device_functions()

            _upsert_device_from_discovery(discovery)
            _upsert_status_rows(tuya_service.device_id, status_rows)
            db.session.commit()

            response = {
                "ok": True,
                "device": {
                    "id": discovery.get("id") or tuya_service.device_id,
                    "name": discovery.get("name"),
                    "online": bool(discovery.get("online", False)),
                },
                "functions": functions,
                "status": status_rows,
            }
            _publish_user_event(user.id, "device_status", response)
            return jsonify(response)
        except TuyaAPIError as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": str(exc), "code": exc.code}), 502
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Device status fetch failed: {exc}"}), 500

    @user_api_bp.route("/workflow/smart-switch")
    @login_required
    def api_workflow_switch():
        flow = [
            "1. User selects game, branch, station, and paid duration.",
            "2. Flask validates request and records payment.",
            "3. Backend retrieves cached Tuya access token (or refreshes automatically).",
            "4. Backend discovers switch command capabilities and validates station availability.",
            "5. Backend sends ON command and records command history + audit log.",
            "6. Session countdown runs with AJAX ticks and real-time SSE updates.",
            "7. At zero or manual stop, backend sends OFF command and closes session.",
            "8. Device events and status updates are persisted and pushed to frontend.",
        ]
        return jsonify({"ok": True, "workflow": flow})

    @user_api_bp.route("/tuya/events", methods=["POST"])
    def api_tuya_events_webhook():
        configured_secret = current_app.config.get("TUYA_EVENT_SECRET", "")
        if configured_secret:
            incoming = request.headers.get("X-Tuya-Event-Secret", "")
            if incoming != configured_secret:
                return jsonify({"ok": False, "message": "Unauthorized event source"}), 401

        payload = request.get_json(silent=True) or {}
        event_type = str(payload.get("eventType") or payload.get("bizCode") or "unknown")
        device_id = str(payload.get("devId") or payload.get("deviceId") or tuya_service.device_id)
        event_id = str(payload.get("id") or payload.get("eventId") or "")

        try:
            db.session.add(
                TuyaEventLog(
                    device_id=device_id,
                    event_type=event_type,
                    event_id=event_id,
                    payload_json=json.dumps(payload, ensure_ascii=True),
                )
            )

            # Keep device online status synchronized from event stream.
            device = TuyaDevice.query.filter_by(device_id=device_id).first()
            if not device:
                device = TuyaDevice(device_id=device_id)
                db.session.add(device)

            if event_type == "deviceOnline":
                device.is_online = True
            elif event_type == "deviceOffline":
                device.is_online = False
            device.last_seen_at = datetime.utcnow()

            status_list = payload.get("status") or payload.get("properties") or []
            if isinstance(status_list, list):
                _upsert_status_rows(device_id, status_list)

            db.session.commit()

            active_sessions = GamingSession.query.filter_by(status="active", plug_id="plug-001").all() + GamingSession.query.filter_by(status="active", plug_id="plug-002").all()
            for row in active_sessions:
                _publish_user_event(
                    row.user_id,
                    "tuya_event",
                    {
                        "event_type": event_type,
                        "device_id": device_id,
                        "event_id": event_id,
                    },
                )

            return jsonify({"ok": True})
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Event handling failed: {exc}"}), 500

    return user_bp, user_api_bp
