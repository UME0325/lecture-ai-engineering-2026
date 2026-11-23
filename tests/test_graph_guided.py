"""第5回 宿題（発展）: 類似度で選び直すGraph（search_graph_guided）と read_pages のテスト。

質問の埋め込み（Gemini API）の代わりに、検索DBに保存済みのページ埋め込みを質問ベクトルとして使う。
APIキーなしで、グラフのたどり方・候補の選び方・返す形を確かめられる。
"""

import json
import sqlite3
import struct

import pytest
import sqlite_vec
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.test import TestModel

import app.retrieval as retrieval
from app import tools
from app.agent import GUIDED_INSTRUCTIONS, agent
from app.config import GRAPH_START_K, GUIDED_MAX_CANDIDATES, GUIDED_READ_MAX_PAGES, RAG_DB


def _stored_vector(page_id: str) -> list[float]:
    db = sqlite3.connect(RAG_DB)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    (blob,) = db.execute("SELECT embedding FROM chunks WHERE page_id = ?", (page_id,)).fetchone()
    db.close()
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


@pytest.fixture
def memory_query(monkeypatch):
    """第3回 PDF p.39（実装例：Claude）の埋め込みを、質問ベクトルの代わりにする。"""
    vector = _stored_vector("lec03-main-p039")
    monkeypatch.setattr(retrieval, "embed_text", lambda text, task_type: vector)


def test_seeds_have_full_text_and_candidates_only_previews(memory_query):
    result = retrieval.search_graph_guided("コンパクションとメモリの違い")
    assert len(result["seeds"]) == GRAPH_START_K
    assert result["seeds"][0]["page_id"] == "lec03-main-p039"  # 自分自身が最も近い
    assert all("content" in seed for seed in result["seeds"])
    assert 0 < len(result["candidates"]) <= GUIDED_MAX_CANDIDATES
    assert all("content" not in c and c["preview"] for c in result["candidates"])


def test_candidates_are_new_unique_and_ordered_by_score(memory_query):
    result = retrieval.search_graph_guided("コンパクションとメモリの違い")
    seed_ids = {seed["page_id"] for seed in result["seeds"]}
    ids = [c["page_id"] for c in result["candidates"]]
    assert len(ids) == len(set(ids))
    assert not seed_ids & set(ids)
    scores = [c["distance"] + retrieval.GUIDED_HOP_PENALTY * c["hops"] for c in result["candidates"]]
    assert scores == sorted(scores)
    # メモリの模式図（第3回 PDF p.13）は、共通用語「メモリ」を経由して2 hopで届く
    assert "lec03-main-p013" in ids


def test_hub_terms_are_not_used_as_bridges(memory_query):
    result = retrieval.search_graph_guided("コンパクションとメモリの違い")
    hubs = result["skipped_hub_terms"]
    assert "AIエージェント" in hubs and "メモリ" not in hubs
    for c in result["candidates"]:
        assert not any(f"共通用語: {hub}" in c["via"] for hub in hubs)


def test_read_pages_deduplicates_and_limits():
    pages = retrieval.read_pages(["lec02-main-p052", "lec02-main-p052"])["pages"]
    assert [p["page"] for p in pages] == [52]
    assert "元の重みは固定" in pages[0]["content"]
    with pytest.raises(ValueError, match="まで"):
        retrieval.read_pages([f"lec03-main-p0{n:02d}" for n in range(10, 11 + GUIDED_READ_MAX_PAGES)])
    error = json.loads(tools.read_pages(["lec09-main-p001"]))
    assert "見つかりません" in error["error"]


def test_preview_skips_repeated_title_and_section_header():
    page = retrieval.read_page("lec02-main-p052")
    preview = retrieval.page_preview(page)
    assert not preview.startswith("4/4")
    assert preview.startswith("元の重みは固定")


def test_guided_mode_wiring_with_test_model(monkeypatch):
    hit = {"seeds": [], "candidates": [], "candidate_pool": 0, "skipped_hub_terms": []}
    monkeypatch.setattr(retrieval, "search_graph_guided", lambda query: hit)
    model = TestModel(call_tools=["search_graph_guided"])
    with agent.override(model=model, instructions=GUIDED_INSTRUCTIONS,
                        tools=[tools.search_graph_guided, tools.read_pages]):
        result = agent.run_sync("コンパクションとメモリの違いは？")
    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert offered == {"search_graph_guided", "read_pages"}
    returns = [p for m in result.all_messages() for p in m.parts if isinstance(p, ToolReturnPart)]
    assert json.loads(returns[0].content) == hit
