"""
AGI Core — Master Orchestrator
The 24/7 loop. Perception → Memory → Planning → Action → Learning → Repeat.
This is the heartbeat of the system.
"""
import sys
import json
import time
import signal
import datetime
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import memory
import nlf_capture
import helm_director

LOG_FILE   = Path.home() / "ai-business/agi-core/agi_loop.log"
STATE_FILE = Path.home() / "ai-business/agi-core/agi_state.json"

TICK_INTERVAL_SEC   = 900   # 15 minutes
HELM_INTERVAL_TICKS = 24    # HELM runs every 6 hours (24 × 15min)
NLF_INTERVAL_TICKS  = 4     # NLF scan every hour (4 × 15min)

RUNNING = True

def _signal_handler(sig, frame):
    global RUNNING
    RUNNING = False
    _log("AGI loop received shutdown signal")

signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT,  _signal_handler)

def _log(msg: str):
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"tick": 0, "helm_last_tick": -999, "nlf_last_tick": -999, "start_time": datetime.datetime.now().isoformat()}

def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def perception_tick(tick: int) -> dict:
    """Gather current state."""
    try:
        import socket
        services = {}
        for port, name in {8300: "Ultra-RAG", 8500: "MemoryWeb", 8765: "AI-Army-Hub"}.items():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    services[name] = "UP"
            except Exception:
                services[name] = "DOWN"
        stats = memory.get_stats()
        return {"tick": tick, "services": services, "memory": stats}
    except Exception as e:
        _log(f"perception_tick error: {e}")
        return {}

def nlf_tick():
    """Scan for new corrections. Trigger retrain if threshold met."""
    try:
        n = nlf_capture.scan_new_chat_files()
        if n:
            _log(f"NLF: captured {n} new corrections (total pending: {memory.get_correction_count(False)})")
        if nlf_capture.check_retrain_threshold():
            count = nlf_capture.trigger_retrain()
            _log(f"NLF: RETRAIN TRIGGERED — {count} corrections applied")
            memory.log_episode("NLF", "retrain_trigger", f"Triggered retrain with {count} corrections", success=True)
    except Exception as e:
        _log(f"nlf_tick error: {e}")

def helm_tick():
    """Run HELM director cycle — generate priorities."""
    try:
        _log("HELM: starting director cycle")
        priorities = helm_director.run_helm_cycle()
        _log(f"HELM: generated {len(priorities)} priorities, posted to chat")
    except Exception as e:
        _log(f"helm_tick error: {e}")
        traceback.print_exc()

def action_tick(perception: dict):
    """Execute pending goals from memory queue."""
    try:
        pending = memory.get_pending_goals(limit=3)
        for goal_rec in pending:
            gid   = goal_rec["id"]
            goal  = goal_rec["goal"]
            agent = goal_rec.get("assigned_agent", "FORGE")
            _log(f"ACTION: executing goal [{gid}] [{agent}] {goal}")
            # Mark in-progress
            with memory._conn() as c:
                c.execute("UPDATE goals SET status='in_progress' WHERE id=?", (gid,))
            # Execute the goal (log it — actual execution happens via Nexus cron / Claude Code)
            memory.log_episode(
                agent=agent,
                goal=goal,
                action=f"Dispatched goal to {agent}",
                outcome="dispatched_to_agent",
                success=True,
                tags=["dispatched"]
            )
            memory.complete_goal(gid, outcome="dispatched", success=True)
    except Exception as e:
        _log(f"action_tick error: {e}")

def run():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _log("=" * 60)
    _log("AGI LOOP STARTING")
    _log(f"Tick interval: {TICK_INTERVAL_SEC}s | HELM every {HELM_INTERVAL_TICKS} ticks | NLF every {NLF_INTERVAL_TICKS} ticks")
    _log("=" * 60)

    state = _load_state()
    tick = state.get("tick", 0)

    while RUNNING:
        try:
            tick += 1
            state["tick"] = tick
            _log(f"--- TICK {tick} ---")

            # 1. Perception
            perception = perception_tick(tick)
            _log(f"Services: {perception.get('services', {})} | Memory: {perception.get('memory', {})}")

            # 2. NLF scan (every hour)
            if tick - state.get("nlf_last_tick", -999) >= NLF_INTERVAL_TICKS:
                nlf_tick()
                state["nlf_last_tick"] = tick

            # 3. HELM priorities (every 6h)
            if tick - state.get("helm_last_tick", -999) >= HELM_INTERVAL_TICKS:
                helm_tick()
                state["helm_last_tick"] = tick

            # 4. Execute pending goals
            action_tick(perception)

            # 5. Log this tick to episodic memory
            memory.log_episode(
                agent="AGI-Loop",
                goal="system_tick",
                action=f"tick_{tick}",
                outcome=json.dumps(perception.get("services", {})),
                success=True
            )

            _save_state(state)

        except Exception as e:
            _log(f"TICK ERROR: {e}")
            traceback.print_exc()

        if RUNNING:
            time.sleep(TICK_INTERVAL_SEC)

    _log("AGI LOOP STOPPED")

if __name__ == "__main__":
    if "--tick" in sys.argv:
        state = _load_state()
        tick = state.get("tick", 0) + 1
        p = perception_tick(tick)
        nlf_tick()
        action_tick(p)
        state["tick"] = tick
        _save_state(state)
        print(f"Manual tick {tick} complete")
        print(f"Stats: {memory.get_stats()}")
    elif "--status" in sys.argv:
        state = _load_state()
        print(f"Tick: {state.get('tick', 0)}")
        print(f"Start: {state.get('start_time', 'unknown')}")
        print(f"Memory: {memory.get_stats()}")
    else:
        run()
