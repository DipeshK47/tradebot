"""Upstox v3 live market-data feed (websocket) via the official SDK.

Wraps MarketDataStreamerV3 (which handles the protobuf decode + auth + auto
-reconnect). Ticks flow only during market hours (09:15-15:30 IST); outside that
the socket connects but stays quiet. Pair with TickAggregator to turn ticks into
candles and run the scanners on bar-close.

    feed = UpstoxFeed(token, ["NSE_EQ|INE002A01018"], mode="ltpc")
    feed.on_tick(lambda msg: ...)
    feed.connect()        # blocking — run in a thread
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import upstox_client


class UpstoxFeed:
    def __init__(self, access_token: str, instrument_keys: list[str], mode: str = "ltpc"):
        if not access_token:
            raise ValueError("UpstoxFeed needs a valid access token (live feed is authenticated).")
        cfg = upstox_client.Configuration()
        cfg.access_token = access_token
        self._client = upstox_client.ApiClient(cfg)
        self._keys = list(instrument_keys)
        self._mode = mode
        self._streamer = upstox_client.MarketDataStreamerV3(self._client, self._keys, mode)
        self._on_tick: Optional[Callable] = None
        self.opened = threading.Event()
        self.msg_count = 0
        self.last_error: Optional[str] = None
        self._streamer.on("open", lambda *a: self.opened.set())
        self._streamer.on("message", self._handle)
        self._streamer.on("error", lambda e=None, *a: setattr(self, "last_error", str(e)))

    def on_tick(self, cb: Callable) -> "UpstoxFeed":
        self._on_tick = cb
        return self

    def _handle(self, message) -> None:
        self.msg_count += 1
        if self._on_tick:
            try:
                self._on_tick(message)
            except Exception:
                pass

    def subscribe(self, keys: list[str], mode: Optional[str] = None) -> None:
        self._streamer.subscribe(keys, mode or self._mode)

    def connect(self) -> None:
        """Open the websocket (blocking event loop) — run in a daemon thread."""
        self._streamer.connect()

    def disconnect(self) -> None:
        try:
            self._streamer.disconnect()
        except Exception:
            pass
