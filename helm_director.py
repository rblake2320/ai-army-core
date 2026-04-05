"""
AGI Core — HELM Director
Reads business metrics + memory outcomes → generates weekly priorities.
Posts to group chat for Craig's approval. Applies approved goals.
This is the self-directed goal-setting engine.
"""
import sys
import json
import socket
import datetime
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import memory

try:
    import boto3
    BEDROCK = boto3.client("bedrock-runtime", region_name="us-east-1")
    BEDROCK_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    HAS_BEDROCK = True
except Exception:
    HAS_BEDROCK = False

CHAT_DIR = Path.home() / "ai-business/shared/chat"
SERVICES = {
    8300: "Ultra-RAG",
    8500: "MemoryWeb",
    8765: "AI Army Hub",
}

def _check_port(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except Exception:
        return False

def _gather_perception() -> dict:
    """Perceive the current state of all systems."""
    service_status = {name: _check_port(port) for port, name in SERVICES.items()}
    stats = memory.get_stats()
    successes = memory.get_success_patterns(10)
    failures  = memory.get_failure_patterns(10)
    pending   = memory.get_pending_goals(5)
    corrections = memory.get_correction_count(applied=False)

    # Count recent chat activity
    chat_files = list(CHAT_DIR.glob("*.md"))
    recent_chats = len([f for f in chat_files
                        if (datetime.datetime.now() - datetime.datetime.fromtimestamp(f.stat().st_mtime)).total_seconds() < 86400])

    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "services": service_status,
        "memory_stats": stats,
        "recent_successes": successes[:3],
        "recent_failures": failures[:3],
        "pending_goals": pending,
        "nlf_corrections_pending": corrections,
        "chat_messages_24h": recent_chats,
    }

def _call_bedrock(prompt: str) -> str:
    if not HAS_BEDROCK:
        return "[Bedrock unavailable]"
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}]
    })
    resp = BEDROCK.invoke_model(modelId=BEDROCK_MODEL, body=body)
    result = json.loads(resp["body"].read())
    return result["content"][0]["text"]

def generate_priorities(perception: dict) -> list:
    """Ask Claude to generate the next 5 priorities based on all available context."""
    prompt = f"""You are HELM, the strategic director of an AGI system running on two NVIDIA DGX Sparks.
Your mission: grow an AI business that leads the tech space. The owner (Craig) has 11 patents on NLF (Natural Language Feedback) — a novel teacher-student learning paradigm.

Current perception:
{json.dumps(perception, indent=2)}

Based on what's working, what's failing, what's pending, and what Craig has been correcting — generate exactly 5 priorities for the next 24 hours.

Rules:
- Each priority must be concrete and verifiable (can be marked DONE or FAILED)
- Assign to the best agent: ORACLE (research), FORGE (build), SENTINEL (test), PRISM (synthesize), HELM (strategy), BEACON (outreach), LEDGER (tracking)
- Prioritize anything that compounds: NLF loop, flywheel, business growth
- Fix failures before adding new work
- Format: JSON array of objects with: priority(1-5), goal, agent, success_criteria

Return ONLY the JSON array. No explanation."""

    response = _call_bedrock(prompt)
    try:
        # Extract JSON from response
        m = re.search(r'\[.*\]', response, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    # Fallback priorities if Bedrock fails
    return [
        {"priority": 1, "goal": "Verify all services healthy", "agent": "SENTINEL", "success_criteria": "All ports respond"},
        {"priority": 2, "goal": "Scan chat for NLF corrections", "agent": "ORACLE", "success_criteria": "Correction count updated"},
        {"priority": 3, "goal": "Run flywheel audit", "agent": "FORGE", "success_criteria": "Audit report written"},
        {"priority": 4, "goal": "Generate NLF demo benchmark", "agent": "FORGE", "success_criteria": "benchmark.py runs successfully"},
        {"priority": 5, "goal": "Post business status to chat", "agent": "BEACON", "success_criteria": "Chat message posted"},
    ]

def post_priorities_to_chat(priorities: list, perception: dict):
    """Post HELM's priorities to the group chat for Craig's visibility."""
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    services_str = ", ".join(f"{n}:{'UP' if up else 'DOWN'}"
                              for n, up in perception["services"].items())
    goals_str = "\n".join(
        f"{i+1}. [{p['agent']}] {p['goal']} → {p['success_criteria']}"
        for i, p in enumerate(priorities)
    )
    stats = perception["memory_stats"]

    msg = f"""[FROM: HELM] [TO: @ALL] [THREAD: agi-priorities]

## AGI Daily Priorities — {datetime.datetime.now().strftime("%Y-%m-%d")}

**Services**: {services_str}
**Memory**: {stats['total_episodes']} episodes | {stats['win_rate']}% win rate | {stats['nlf_corrections']} NLF corrections
**24h chat**: {perception['chat_messages_24h']} messages

### Today's Goals
{goals_str}

Reply with APPROVE or corrections. I adapt.
"""
    fpath = CHAT_DIR / f"{ts}_helm-priorities.md"
    fpath.write_text(msg)
    print(f"Posted priorities to: {fpath.name}")
    return priorities

def load_goals_into_memory(priorities: list):
    """Store HELM's priorities as pending goals in episodic memory."""
    for p in priorities:
        memory.add_goal(
            goal=p.get("goal", ""),
            priority=p.get("priority", 5),
            assigned_agent=p.get("agent", "")
        )
    print(f"Loaded {len(priorities)} goals into memory")

def run_helm_cycle():
    print(f"[HELM] Starting director cycle: {datetime.datetime.now().isoformat()}")
    perception = _gather_perception()
    print(f"[HELM] Perception: services={perception['services']}, stats={perception['memory_stats']}")
    priorities = generate_priorities(perception)
    print(f"[HELM] Generated {len(priorities)} priorities")
    post_priorities_to_chat(priorities, perception)
    load_goals_into_memory(priorities)
    # Log this cycle as an episode
    memory.log_episode(
        agent="HELM",
        goal="generate_daily_priorities",
        action=f"Generated {len(priorities)} priorities based on perception",
        outcome=json.dumps(priorities),
        success=True
    )
    return priorities

if __name__ == "__main__":
    if "--perceive" in sys.argv:
        import pprint; pprint.pprint(_gather_perception())
    elif "--run" in sys.argv or len(sys.argv) == 1:
        run_helm_cycle()
    else:
        print("helm_director.py -- HELM strategic director")
        print("  --perceive  show current system perception")
        print("  --run       run full HELM cycle")
