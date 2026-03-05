"""Best-effort LAN sync bus for dual-laptop debate fallback."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid


class LanSyncBus:
    def __init__(self):
        self.channel = os.getenv("DEBATE_LAN_CHANNEL", "debatebot-dual-v1")
        self.port = int(os.getenv("DEBATE_LAN_PORT", "46883"))
        self.broadcast_host = os.getenv("DEBATE_LAN_BROADCAST", "255.255.255.255")
        self.sender_id = str(uuid.uuid4())

        self._send_sock: socket.socket | None = None
        self._recv_sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._send_sock = send_sock

        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        recv_sock.bind(("", self.port))
        recv_sock.settimeout(0.5)
        self._recv_sock = recv_sock

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._recv_sock is not None:
            try:
                self._recv_sock.close()
            except Exception:
                pass
            self._recv_sock = None

        if self._send_sock is not None:
            try:
                self._send_sock.close()
            except Exception:
                pass
            self._send_sock = None

    def publish(self, event_type: str, **payload) -> None:
        if not self._running or self._send_sock is None:
            return

        message = {
            "channel": self.channel,
            "sender_id": self.sender_id,
            "type": event_type,
            "ts": time.time(),
            **payload,
        }
        raw = json.dumps(message, ensure_ascii=True).encode("utf-8")
        try:
            self._send_sock.sendto(raw, (self.broadcast_host, self.port))
        except Exception:
            pass

    def drain_events(self) -> list[dict]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def _listen_loop(self) -> None:
        sock = self._recv_sock
        if sock is None:
            return

        while self._running:
            try:
                data, _addr = sock.recvfrom(65536)
            except socket.timeout:
                continue
            except Exception:
                break

            try:
                payload = json.loads(data.decode("utf-8", errors="ignore"))
            except Exception:
                continue

            if payload.get("channel") != self.channel:
                continue
            if payload.get("sender_id") == self.sender_id:
                continue

            with self._lock:
                self._events.append(payload)
                # Keep queue bounded.
                if len(self._events) > 300:
                    self._events = self._events[-150:]
