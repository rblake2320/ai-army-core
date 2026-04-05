"""
AGI Core — NLF Capture
Watches all agent outputs + Craig's corrections. Feeds the learning loop.
Triggers retrain automatically at threshold.
"""
import re
import os
import sys
import time
import json
import glob
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import memory

CHAT_DIR   = Path.home() / "ai-business/shared/chat"
STATE_FILE = Path.home() / "ai-business/agi-core/.nlf_state.json"
RETRAIN_THRESHOLD = 10   # corrections before retrain triggers (was 50, tightened)

# Patterns that indicate Craig is making a correction
CORRECTION_PATTERNS = [
    r'\b(no|wrong|incorrect|fix|change|should be|not right|that\'s wrong|don\'t|stop)\b',
    r'\b(actually|instead|rather|correction)\b',
    r'\b(make sure|always|never|you need to)\b',
    r'^\s*(no,|wrong,|actually,|correction:)',
]

CRAIG_SENDERS = {'craig', 'rblake2320', 'owner', 'user'}

def _load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_file": None, "processed": [], "retrain_count": 0}

def _save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def _is_correction(text: str) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in CORRECTION_PATTERNS)

def _extract_sender(content: str) -> str:
    m = re.search(r'\[FROM:\s*([^\]]+)\]', content, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()
    m = re.search(r'\*\*from\*\*:\s*(\S+)', content, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()
    return ""

def scan_new_chat_files() -> int:
    state = _load_state()
    processed = set(state.get("processed", []))
    captured = 0

    files = sorted(glob.glob(str(CHAT_DIR / "*.md")))
    for fpath in files:
        fname = os.path.basename(fpath)
        if fname in processed:
            continue
        try:
            content = open(fpath).read()
        except Exception:
            continue

        sender = _extract_sender(content)
        if sender in CRAIG_SENDERS and _is_correction(content):
            # Extract the correction text (strip headers/metadata)
            lines = [l for l in content.splitlines() if l.strip() and not l.startswith('#')]
            correction_text = "\n".join(lines[:10])  # first 10 meaningful lines
            memory.log_nlf_correction(
                source=f"chat:{fname}",
                original="[prior agent output]",
                correction=correction_text
            )
            captured += 1

        processed.add(fname)

    state["processed"] = list(processed)
    _save_state(state)
    return captured

def check_retrain_threshold() -> bool:
    count = memory.get_correction_count(applied=False)
    return count >= RETRAIN_THRESHOLD

def trigger_retrain():
    """Log the retrain event and mark corrections applied."""
    ts = datetime.datetime.now().isoformat()
    retrain_log = Path.home() / "ai-business/agi-core/retrain_log.jsonl"
    count = memory.get_correction_count(applied=False)
    with open(retrain_log, "a") as f:
        json.dump({"ts": ts, "corrections_used": count, "status": "triggered"}, f)
        f.write("\n")
    memory.mark_corrections_applied()
    # Post to chat
    chat_msg = Path.home() / f"ai-business/shared/chat/{ts.replace(':','').replace('-','')[:15]}_agi-nlf.md"
    chat_msg.write_text(
        f"[FROM: AGI-Core] [TO: @ALL] [THREAD: nlf-loop]\n\n"
        f"NLF retrain triggered: {count} corrections accumulated.\n"
        f"Flywheel turning. Model improvement cycle started.\n"
    )
    return count

if __name__ == "__main__":
    if "--scan" in sys.argv:
        n = scan_new_chat_files()
        print(f"Captured {n} new NLF corrections")
        print(f"Total pending: {memory.get_correction_count(applied=False)}")
        if check_retrain_threshold():
            print("THRESHOLD REACHED — triggering retrain")
            trigger_retrain()
    elif "--status" in sys.argv:
        print(f"Pending corrections: {memory.get_correction_count(applied=False)}")
        print(f"Applied corrections: {memory.get_correction_count(applied=True)}")
        print(f"Retrain threshold: {RETRAIN_THRESHOLD}")
        print(f"Ready to retrain: {check_retrain_threshold()}")
    else:
        print("nlf_capture.py -- NLF correction watcher")
        print("  --scan    scan chat dir for new corrections")
        print("  --status  show correction counts")
