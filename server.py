"""
server.py — FastAPI WebSocket server for Guildmaster.

Runs the game tick loop as an asyncio background task and pushes serialized
game state to all connected browsers after every tick. Player commands are
received over the same WebSocket connection and forwarded to GameLoop.

Usage:
    pip install fastapi uvicorn[standard]
    uvicorn server:app --reload
"""

import asyncio
import json
import random
from pathlib import Path
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from ui.game_loop import GameLoop

# ── App setup ──────────────────────────────────────────────────────────

app = FastAPI(title="Guildmaster")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Game state ─────────────────────────────────────────────────────────

random.seed(42)
game = GameLoop.create(starting_gold=500)
connected: List[WebSocket] = []

TICKS_PER_SECOND = 10


# ── State serializer ───────────────────────────────────────────────────

def _serialize() -> dict:
    """Build a JSON-compatible snapshot of the current game state."""
    ow = game._overworld
    econ = game._economy
    te = game._time_engine
    ms = ow.map_state

    current_tick = te.tick
    boss_duration = ms.boss_timer_duration
    boss_ticks_remaining = max(0, boss_duration - (current_tick - ms.act_start_tick))

    # Split quests into available vs in-progress
    available_quests = []
    active_quests = []
    for quest in ms.active_quests.values():
        q = quest.to_dict()
        spawned = q.get("spawned_at_tick", 0)
        exp_time = q.get("expiration_time", 50)
        q["expiry"] = max(0, spawned + exp_time - current_tick)
        if q["status"] == "available":
            available_quests.append(q)
        else:
            active_quests.append(q)

    # Heroes
    heroes = [h.to_dict() for h in econ.roster.heroes]

    # Boss
    boss = None
    if ms.boss:
        boss = {
            "boss_id": ms.boss.boss_id,
            "revealed": ms.boss.revealed,
            "defeated": ms.boss.defeated,
            "buffs": list(ms.boss.buffs),
        }

    # Shops
    shops = [
        {
            "shop_id": s.shop_id,
            "expiry": max(0, s.expiration_tick - current_tick),
        }
        for s in ms.active_shops.values()
    ]

    return {
        "tick": current_tick,
        "gold": econ.ledger.balance,
        "act": ms.current_act,
        "boss_ticks_remaining": boss_ticks_remaining,
        "boss_timer_duration": boss_duration,
        "available_quests": available_quests,
        "active_quests": active_quests,
        "heroes": heroes,
        "boss": boss,
        "shops": shops,
    }


# ── WebSocket broadcast ────────────────────────────────────────────────

async def _broadcast(msg: str) -> None:
    dead = []
    for ws in connected:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connected:
            connected.remove(ws)


# ── Tick loop ──────────────────────────────────────────────────────────

async def _tick_loop() -> None:
    while True:
        game.tick()
        payload = json.dumps({"type": "state", "data": _serialize()})
        await _broadcast(payload)
        await asyncio.sleep(1.0 / TICKS_PER_SECOND)


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_tick_loop())


# ── Routes ─────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    connected.append(ws)
    # Push current state immediately on connect
    await ws.send_text(json.dumps({"type": "state", "data": _serialize()}))
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "command":
                feedback = game.handle_input(msg["command"])
                await ws.send_text(json.dumps({"type": "feedback", "text": feedback}))
                await _broadcast(json.dumps({"type": "state", "data": _serialize()}))
            elif msg.get("type") == "pause":
                game._time_engine.pause("ui")
            elif msg.get("type") == "resume":
                game._time_engine.resume("ui")
    except WebSocketDisconnect:
        if ws in connected:
            connected.remove(ws)
