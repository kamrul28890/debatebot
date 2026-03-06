"""Best-effort LAN sync bus for dual-laptop debate fallback."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
import importlib


def _from_keys(attr: str):
    try:
        keys = importlib.import_module("keys")
    except Exception:
        return None
    return getattr(keys, attr, None)


class LanSyncBus:
    def __init__(self):
        self.channel = (
            os.getenv("DEBATE_LAN_CHANNEL")
            or _from_keys("debate_lan_channel")
            or "debatebot-dual-v1"
        )
        port_raw = os.getenv("DEBATE_LAN_PORT") or _from_keys("debate_lan_port") or "46883"
        try:
            self.port = int(str(port_raw).strip())
        except ValueError:
            self.port = 46883
        self.broadcast_host = (
            os.getenv("DEBATE_LAN_BROADCAST")
            or _from_keys("debate_lan_broadcast")
            or "255.255.255.255"
        )
        raw_peers = (os.getenv("DEBATE_LAN_PEERS") or _from_keys("debate_lan_peers") or "").strip()
        self.peer_hosts = [host.strip() for host in raw_peers.split(",") if host.strip()]
        try:
            heartbeat = float(os.getenv("DEBATE_LAN_HEARTBEAT_SECONDS", "1.5"))
        except ValueError:
            heartbeat = 1.5
        self._heartbeat_seconds = max(0.5, heartbeat)
        self.sender_id = str(uuid.uuid4())

        self._send_sock: socket.socket | None = None
        self._recv_sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._peer_last_seen: dict[str, float] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

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
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop(self) -> None:
        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=1.0)
            self._heartbeat_thread = None

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
        targets = [(self.broadcast_host, self.port)] + [(host, self.port) for host in self.peer_hosts]
        for target in targets:
            try:
                self._send_sock.sendto(raw, target)
            except Exception:
                continue

    def drain_events(self) -> list[dict]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def connection_snapshot(self, timeout_seconds: float = 6.0) -> dict:
        now = time.time()
        timeout = max(0.5, float(timeout_seconds))
        with self._lock:
            recent = [sid for sid, ts in self._peer_last_seen.items() if (now - ts) <= timeout]
            last_seen = max(self._peer_last_seen.values()) if self._peer_last_seen else 0.0
        return {
            "running": self._running,
            "recent_peer_count": len(recent),
            "last_peer_seen_age_s": (now - last_seen) if last_seen else None,
        }

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

            # Local receive timestamp avoids cross-device clock-skew issues.
            payload["_recv_ts"] = time.time()
            with self._lock:
                sender = str(payload.get("sender_id", "")).strip()
                if sender:
                    self._peer_last_seen[sender] = payload["_recv_ts"]
                    if len(self._peer_last_seen) > 64:
                        # Keep map bounded.
                        recent = sorted(self._peer_last_seen.items(), key=lambda item: item[1], reverse=True)[:32]
                        self._peer_last_seen = dict(recent)
                self._events.append(payload)
                # Keep queue bounded.
                if len(self._events) > 300:
                    self._events = self._events[-150:]

    def _heartbeat_loop(self) -> None:
        # Heartbeats keep peer liveness visible in UI and speed fallback readiness.
        while self._running:
            self.publish("heartbeat")
            time.sleep(self._heartbeat_seconds)
