"""Phase E tools — real-time data fetched at query time (not via RAG corpus).

Each tool implements:
  - matches(query: str) -> bool      # keyword check
  - run(query: str) -> dict | None   # returns {"context": str, "sources": list[dict]}

Tool order matters: more specific (dorm, shuttle) before generic
(cafeteria, notice) so narrowly-scoped queries route correctly.
"""
from .dorm_cafeteria import DormCafeteriaTool
from .cafeteria import CafeteriaTool
from .shuttle import ShuttleTool
from .notice import NoticeTool

TOOLS = [
    DormCafeteriaTool(),
    CafeteriaTool(),
    ShuttleTool(),
    NoticeTool(),
]

# Category-to-tool map (label_5way -> preferred tools for forced realtime fetch).
# Used by realtime_model.py when --refresh forces a tool call regardless of
# matches() keyword routing.
CATEGORY_TOOLS = {
    1: [NoticeTool()],                    # 공지
    2: [NoticeTool()],                    # 학사일정 (게시판 백본)
    3: [DormCafeteriaTool(), CafeteriaTool()],  # 식단
    4: [ShuttleTool()],                   # 셔틀
}


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


def force_use_tool(query: str, category: int):
    """Force-call the category's preferred tool(s), ignoring matches().

    Used by realtime_model.py to guarantee freshness for categories whose
    data changes daily/weekly (식단·셔틀) or with each new post (공지·학사일정).
    """
    tools = CATEGORY_TOOLS.get(int(category), [])
    for t in tools:
        try:
            r = t.run(query)
            if r:
                return t.name, r
        except Exception as e:
            print(f"[tools.force] {t.name} failed: {e}", flush=True)
            continue
    return None
