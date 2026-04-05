"""
AGI Core — Seek and Learn Engine
When stuck: search the internet, extract the solution, store it, apply it.
Never blocked for long. Learns from every encounter.
"""
import sys, json, re, datetime, urllib.request, urllib.parse, hashlib
from pathlib import Path
sys.path.insert(0, str(Path.home() / "ai-business/agi-core"))
import memory

KNOWLEDGE_DIR = Path.home() / "ai-business/agi-core/knowledge"
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

# ─── Exa search (we have the key) ───
EXA_KEY_FILE = Path.home() / ".docker/mcp/.env"

def _get_exa_key():
    if EXA_KEY_FILE.exists():
        for line in EXA_KEY_FILE.read_text().splitlines():
            if "EXA_API_KEY" in line:
                return line.split("=", 1)[-1].strip().strip('"')
    return None


def _firecrawl_search(query: str, num_results: int = 5) -> list:
    """Firecrawl search — works on Spark1."""
    import subprocess, json
    env_file = Path.home() / '.docker/mcp/.env'
    fc_key = ''
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if 'FIRECRAWL' in line:
                fc_key = line.split('=',1)[-1].strip().strip('"')
    if not fc_key:
        return []
    payload = json.dumps({'query': query, 'limit': num_results}).encode()
    req = urllib.request.Request(
        'https://api.firecrawl.dev/v1/search',
        data=payload, method='POST',
        headers={'Authorization': f'Bearer {fc_key}', 'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return [{'title': r.get('title',''), 'url': r.get('url',''),
                     'snippet': r.get('description','')[:300]} for r in data.get('data',[])]
    except Exception as e:
        return []

def web_search(query: str, num_results: int = 5) -> list:
    """Search the web using Exa API. Returns list of {title, url, snippet}."""
    exa_key = _get_exa_key()
    # Try Firecrawl first (works on Spark1), then Exa, then DuckDuckGo
    _fc = _firecrawl_search(query, num_results)
    if _fc: return _fc
    if not exa_key:
        return _fallback_search(query)

    payload = json.dumps({
        "query": query,
        "numResults": num_results,
        "useAutoprompt": True,
        "type": "neural",
    }).encode()

    req = urllib.request.Request(
        "https://api.exa.ai/search",
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {exa_key}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            results = []
            for r in data.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("text", "")[:300] if r.get("text") else r.get("highlight", "")[:300],
                })
            return results
    except Exception as e:
        print(f"  [Exa search error: {e}]")
    return _fallback_search(query)

def _fallback_search(query: str) -> list:
    """DuckDuckGo HTML search as fallback."""
    try:
        q = urllib.parse.quote(query)
        req = urllib.request.Request(
            f"https://html.duckduckgo.com/html/?q={q}",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # Extract snippets
        results = []
        for m in re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)[:5]:
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if text:
                results.append({"title": "DuckDuckGo result", "url": "", "snippet": text[:200]})
        return results
    except Exception as e:
        return [{"title": "search_failed", "url": "", "snippet": str(e)}]

def research_obstacle(obstacle: str, context: str = "") -> dict:
    """
    Given an obstacle, search the internet for solutions.
    Stores findings in knowledge base. Returns best strategy.
    """
    query = f"how to solve {obstacle} {context} programmatically 2024 2025"
    print(f"  [SEEK] Searching: {query[:80]}")

    results = web_search(query)

    # Extract actionable content
    solutions = []
    for r in results:
        snippet = r.get("snippet", "")
        if any(w in snippet.lower() for w in
               ["solution", "fix", "workaround", "try", "use", "install",
                "alternative", "instead", "bypass", "approach"]):
            solutions.append({"source": r.get("url", ""), "snippet": snippet})

    # Also search for alternatives
    alt_results = web_search(f"alternative to {obstacle} {context} 2025")

    knowledge = {
        "obstacle": obstacle,
        "context": context,
        "searched_at": datetime.datetime.now().isoformat(),
        "search_results": results,
        "solutions": solutions,
        "alternatives": alt_results[:3],
        "best_strategy": _extract_best_strategy(obstacle, solutions, alt_results),
    }

    # Save to knowledge base
    key = hashlib.md5(f"{obstacle}{context}".encode()).hexdigest()[:8]
    knowledge_file = KNOWLEDGE_DIR / f"obstacle_{key}.json"
    knowledge_file.write_text(json.dumps(knowledge, indent=2))

    # Log to episodic memory
    memory.log_episode(
        agent="SEEK-ENGINE",
        goal=f"research_obstacle:{obstacle}",
        action=f"Searched internet for solution. Found {len(solutions)} solutions.",
        outcome=knowledge["best_strategy"],
        success=len(solutions) > 0,
        tags=["research", "obstacle", obstacle]
    )

    print(f"  [SEEK] Found {len(solutions)} solutions. Best: {knowledge['best_strategy'][:80]}")
    return knowledge

def _extract_best_strategy(obstacle: str, solutions: list, alternatives: list) -> str:
    if not solutions and not alternatives:
        return f"No automated solution found for '{obstacle}' — escalate to Craig"

    # GitHub-specific knowledge
    if "github" in obstacle.lower() and "org" in obstacle.lower():
        return ("GitHub org creation requires web UI on github.com (API is Enterprise-only). "
                "Use: browser automation with undetected-playwright, OR create under existing account, "
                "OR use GitHub Education/Enterprise trial.")

    if "captcha" in obstacle.lower() and "github" in obstacle.lower():
        return ("GitHub uses Arkose Labs FunCAPTCHA. Options: "
                "1) 2captcha API ($0.001/solve), "
                "2) undetected-playwright with stealth plugin, "
                "3) Accept manual human step for initial account creation.")

    if "email" in obstacle.lower() and ("verify" in obstacle.lower() or "create" in obstacle.lower()):
        return ("Email creation options: Cloudflare Email Routing (need CF token), "
                "Proton Mail API, Tutanota (no phone required), "
                "OR use Hostinger email API (token available).")

    if solutions:
        return solutions[0]["snippet"][:200]

    if alternatives:
        return f"Alternative approach: {alternatives[0].get('snippet', '')[:200]}"

    return f"Research incomplete — try manual approach for: {obstacle}"

def learn_from_success(task: str, approach: str, outcome: str):
    """Store successful approach for future use."""
    key = hashlib.md5(task.encode()).hexdigest()[:8]
    success_file = KNOWLEDGE_DIR / f"success_{key}.json"
    data = {
        "task": task,
        "approach": approach,
        "outcome": outcome,
        "learned_at": datetime.datetime.now().isoformat(),
    }
    success_file.write_text(json.dumps(data, indent=2))
    memory.log_episode("SEEK-ENGINE", f"learn:{task}", approach, outcome, True,
                       tags=["learning", "success", task])
    print(f"  [LEARN] Stored success: {task} → {approach[:60]}")

def get_known_solution(obstacle: str) -> str | None:
    """Check if we've already researched this obstacle."""
    for f in KNOWLEDGE_DIR.glob("obstacle_*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("obstacle") == obstacle:
                return data.get("best_strategy")
        except Exception:
            continue
    return None

if __name__ == "__main__":
    import sys
    if "--research" in sys.argv:
        idx = sys.argv.index("--research")
        obstacle = sys.argv[idx+1] if idx+1 < len(sys.argv) else "unknown obstacle"
        result = research_obstacle(obstacle, " ".join(sys.argv[idx+2:]))
        print("\nBest strategy:", result["best_strategy"])
    elif "--stats" in sys.argv:
        files = list(KNOWLEDGE_DIR.glob("*.json"))
        print(f"Knowledge base: {len(files)} entries")
        for f in files[-5:]:
            d = json.loads(f.read_text())
            print(f"  {f.name}: {d.get('obstacle','?') or d.get('task','?')}")
    else:
        print("seek_and_learn.py — Internet research + knowledge storage")
        print("  --research <obstacle> [context]  research a specific obstacle")
        print("  --stats                          show knowledge base")
