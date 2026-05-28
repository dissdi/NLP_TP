"""Phase E tools — real-time data fetched at query time (not via RAG corpus).

Each tool implements:
  - matches(query: str) -> bool      # keyword check
  - run(query: str) -> dict | None   # returns {"context": str, "sources": list[dict]}
"""
from .cafeteria import CafeteriaTool

TOOLS = [CafeteriaTool()]


def maybe_use_tool(query: str):
    """Return (tool_name, result_dict) of the first matching tool, or None."""
    for t in TOOLS:
        if t.matches(query):
            try:
                r = t.run(query)
                if r:
                    return t.name, r
            except Exception as e:
                print(f"[tools] {t.name} failed: {e}", flush=True)
                return None
    return None
