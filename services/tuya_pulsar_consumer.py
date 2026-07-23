from __future__ import annotations

import json
import logging
import threading
from typing import Callable


class TuyaPulsarConsumer:
    """Optional Tuya Pulsar subscriber.

    Requires pulsar-client package and valid broker/topic config.
    """

    def __init__(
        self,
        *,
        broker_url: str,
        topic: str,
        subscription: str,
        message_handler: Callable[[dict], None],
    ) -> None:
        self.broker_url = broker_url
        self.topic = topic
        self.subscription = subscription
        self.message_handler = message_handler
        self.log = logging.getLogger("tuya.pulsar")
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="tuya-pulsar", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:  # pragma: no cover
        try:
            import pulsar
        except Exception as exc:
            self.log.warning("Pulsar client unavailable: %s", exc)
            return

        client = None
        consumer = None
        try:
            client = pulsar.Client(self.broker_url)
            consumer = client.subscribe(self.topic, subscription_name=self.subscription)
            self.log.info("Connected to Tuya Pulsar topic %s", self.topic)

            while not self._stop_event.is_set():
                try:
                    msg = consumer.receive(timeout_millis=1000)
                except Exception:
                    continue

                try:
                    payload = json.loads(msg.data().decode("utf-8"))
                    self.message_handler(payload)
                    consumer.acknowledge(msg)
                except Exception as exc:
                    self.log.error("Failed to process Pulsar message: %s", exc)
                    consumer.negative_acknowledge(msg)
        except Exception as exc:
            self.log.error("Tuya Pulsar consumer crashed: %s", exc)
        finally:
            if consumer:
                try:
                    consumer.close()
                except Exception:
                    pass
            if client:
                try:
                    client.close()
                except Exception:
                    pass
