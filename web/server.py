"""
server.py — Flask REST server for the Guildmaster combat web UI.

Run with:  python web/server.py
Then open: http://localhost:5000
"""

from __future__ import annotations

import json
import os
import sys

# Make the project root importable regardless of where the script is run from
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask import Flask, jsonify, request, send_from_directory

from web.combat_session import StepCombatSession
from hero.archetype_loader import load_archetype, list_archetypes
from enemy.enemy_loader import load_enemy, list_enemies

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
    static_url_path="",
)

# Single in-memory session (one fight at a time)
_session: StepCombatSession | None = None


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Catalogue endpoints
# ---------------------------------------------------------------------------

@app.route("/api/archetypes")
def api_archetypes():
    result = []
    for arch_id in sorted(list_archetypes()):
        try:
            hero = load_archetype(arch_id, "preview", "Preview")
            result.append({
                "id":              arch_id,
                "name":            hero.archetype,
                "max_health":      hero.max_health,
                "base_dice_count": hero.base_dice_count,
                "base_dice_sides": hero.base_dice_sides,
                "stats": {
                    "STR": hero.strength,
                    "DEX": hero.dexterity,
                    "INT": hero.intelligence,
                    "CHA": hero.charisma,
                    "CON": hero.constitution,
                },
                "skills": [
                    {
                        "name":        sk.name,
                        "description": sk.description,
                        "dice_slots":  sk.dice_slots,
                        "effect_type": sk.effect_type,
                        "charge_cost": sk.charge_cost,
                    }
                    for sk in hero.skills
                    if sk is not None
                ],
                "passives": [p.get("name", p.get("passive_id", "")) for p in hero.passives],
            })
        except Exception as exc:
            app.logger.warning("Could not load archetype %s: %s", arch_id, exc)
    return jsonify(result)


@app.route("/api/enemies")
def api_enemies():
    result = []
    for eid in sorted(list_enemies()):
        try:
            e = load_enemy(eid, act=1)
            result.append({
                "id":              eid,
                "name":            e.name,
                "max_health":      e.max_health,
                "base_dice_count": e.base_dice_count,
                "base_dice_sides": e.base_dice_sides,
                "skills": [
                    {"name": sk.name, "description": sk.description, "effect_type": sk.effect_type}
                    for sk in e.skills
                ],
            })
        except Exception as exc:
            app.logger.warning("Could not load enemy %s: %s", eid, exc)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Combat endpoints
# ---------------------------------------------------------------------------

@app.route("/api/combat/start", methods=["POST"])
def api_start():
    global _session
    data = request.get_json(force=True)

    heroes = []
    for i, h in enumerate(data.get("heroes", [])):
        try:
            hero = load_archetype(h["archetype_id"], f"h{i}", h["name"])
            heroes.append(hero)
        except Exception as exc:
            return jsonify({"error": f"Bad hero config: {exc}"}), 400

    enemies = []
    for entry in data.get("enemies", []):
        try:
            count = max(1, int(entry.get("count", 1)))
            act   = int(entry.get("act", 1))
            for _ in range(count):
                enemies.append(load_enemy(entry["enemy_id"], act=act))
        except Exception as exc:
            return jsonify({"error": f"Bad enemy config: {exc}"}), 400

    if not heroes:
        return jsonify({"error": "At least one hero required."}), 400
    if not enemies:
        return jsonify({"error": "At least one enemy required."}), 400

    _session = StepCombatSession(heroes, enemies)
    return jsonify(_session.get_state())


@app.route("/api/combat/begin-round", methods=["POST"])
def api_begin_round():
    if _session is None:
        return jsonify({"error": "No active combat. Call /api/combat/start first."}), 400
    return jsonify(_session.begin_round())


@app.route("/api/combat/assign", methods=["POST"])
def api_assign():
    """
    Body: { "assignments": { "h0": { "0": [4,7], "1": [2] }, "h1": { "0": [5] } } }
    Each key in inner dict is a string skill index; value is a list of die values.
    """
    if _session is None:
        return jsonify({"error": "No active combat."}), 400
    data = request.get_json(force=True)
    manual = data.get("assignments")
    return jsonify(_session.resolve_round(manual_assignments=manual))


@app.route("/api/combat/auto-turn", methods=["POST"])
def api_auto_turn():
    if _session is None:
        return jsonify({"error": "No active combat."}), 400
    return jsonify(_session.auto_turn())


@app.route("/api/combat/state")
def api_state():
    if _session is None:
        return jsonify({"error": "No active combat."}), 400
    return jsonify(_session.get_state())


@app.route("/api/combat/reset", methods=["POST"])
def api_reset():
    global _session
    _session = None
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("  Guildmaster Combat UI")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000, use_reloader=False)
