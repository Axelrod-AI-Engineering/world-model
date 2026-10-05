"""The `/ws` stream (§12.3): trace events and runner status, with replay after `since_seq`."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()

HELLO_TIMEOUT_S = 2.0


class _Session:
    def __init__(self, websocket: WebSocket, state: Any) -> None:
        self.ws = websocket
        self.state = state
        self.queue: asyncio.Queue = asyncio.Queue()
        self.last_seq = 0
        self.send_lock = asyncio.Lock()
        self.gate = asyncio.Lock()          # a replay holds it, so live events wait and stay in order

    async def send(self, message: dict) -> None:
        async with self.send_lock:
            await self.ws.send_text(json.dumps(message, default=str))

    async def send_trace(self, event: dict) -> None:
        seq = int(event.get("seq", 0))
        if seq <= self.last_seq:
            return                   # already sent during a replay
        self.last_seq = seq
        await self.send({"type": "trace", "event": event})

    def status(self) -> dict | None:
        runner = self.state.runner
        if runner is None or not runner.loaded:
            return None
        return json.loads(runner.status().model_dump_json())

    async def replay(self, since_seq: int) -> None:
        """Replay the recorded events after `since_seq`, then the current status."""
        async with self.gate:
            self.last_seq = since_seq
            for ev in self.state.tracer.since(since_seq):
                await self.send_trace(json.loads(ev.model_dump_json()))
            st = self.status()
            if st is not None:
                await self.send({"type": "status", "status": st})

    async def pump(self) -> None:
        while True:
            msg = await self.queue.get()
            async with self.gate:
                if msg.get("type") == "trace":
                    await self.send_trace(msg["event"])
                else:
                    await self.send(msg)

    async def listen(self) -> None:
        while True:
            msg = await self.ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "hello":
                await self.replay(int(msg.get("since_seq") or 0))
            elif isinstance(msg, dict) and msg.get("type") == "ping":
                await self.send({"type": "pong"})


@ws_router.websocket("/ws")
async def stream(websocket: WebSocket) -> None:
    await websocket.accept()
    state = websocket.app.state.axelrod
    session = _Session(websocket, state)
    state.tracer.subscribe(asyncio.get_running_loop(), session.queue)
    try:
        # Client to server: {"type": "hello", "since_seq": n}. Without a hello, stream from now on.
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=HELLO_TIMEOUT_S)
        except TimeoutError:
            first = {"type": "hello", "since_seq": state.tracer.last_seq}
        since = int(first.get("since_seq") or 0) if isinstance(first, dict) and first.get("type") == "hello" \
            else state.tracer.last_seq
        await session.replay(since)
        pump = asyncio.create_task(session.pump())
        try:
            await session.listen()
        finally:
            pump.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump
    except WebSocketDisconnect:
        pass
    finally:
        state.tracer.unsubscribe(session.queue)
