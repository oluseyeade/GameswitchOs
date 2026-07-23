from __future__ import annotations

import json
import queue
import threading
from collections import defaultdict
from typing import Iterator


class EventBus:
    """In-memory pub/sub bus for server-sent events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._channels: dict[str, list[queue.Queue]] = defaultdict(list)

    def subscribe(self, channel: str) -> queue.Queue:
        listener: queue.Queue = queue.Queue()
        with self._lock:
            self._channels[channel].append(listener)
        return listener

    def unsubscribe(self, channel: str, listener: queue.Queue) -> None:
        with self._lock:
            listeners = self._channels.get(channel, [])
            if listener in listeners:
                listeners.remove(listener)
            if not listeners and channel in self._channels:
                self._channels.pop(channel, None)

    def publish(self, channel: str, event: dict) -> None:
        with self._lock:
            listeners = list(self._channels.get(channel, []))
        for listener in listeners:
            listener.put_nowait(event)

    def stream(self, channel: str) -> Iterator[str]:
        listener = self.subscribe(channel)
        try:
            # Initial handshake event.
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    event = listener.get(timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            self.unsubscribe(channel, listener)
