"""第5回: ページ単位のベクトル検索。"""

import argparse
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from collections import defaultdict, deque
from pathlib import Path

from google import genai
from google.genai import types
from pydantic_ai.exceptions import ModelHTTPError
import sqlite_vec

from app.config import (
    EMBEDDING_DIMENSIONS, EMBEDDING_MAX_TOKENS, EMBEDDING_MODEL,
    RAG_DB, RAG_DOCUMENT_IDS, RAG_SOURCE, RAG_TOP_K, RAG_TREE, get_api_key,
    RAG_GRAPH, GRAPH_START_K, GRAPH_HOPS, GRAPH_MAX_RESULTS,
    GUIDED_HUB_MAX_PAGES, GUIDED_HOP_PENALTY, GUIDED_MAX_CANDIDATES, GUIDED_READ_MAX_PAGES,
    GUIDED_V2_AUTO_FULL_K,
)


def get_all_materials() -> str:
    """全資料を、講義・章・ページの情報付きで1つの文字列にまとめる。"""
    documents = json.loads(RAG_SOURCE.read_text(encoding="utf-8"))
    return "\n\n".join(
        f"資料: {document['id']} / {document['title']}\n"
        f"章: {section['section']}\n"
        f"ページ: PDF p.{page['page']} / {page['title']}\n{page['content']}"
        for document in documents
        for section in document["content"]
        for page in section["content"]
    )

def load_pages(source: Path = RAG_SOURCE) -> list[dict]:
    """資料→章→ページのJSONを、対象資料のページ一覧に変換する。"""
    documents = json.loads(source.read_text(encoding="utf-8"))
    pages = []
    for document in documents:
        if document["id"] not in RAG_DOCUMENT_IDS:
            continue
        for section in document["content"]:
            for page in section["content"]:
                pages.append({"page_id": page["id"], "document_id": document["id"],
                              "lecture": int(document["id"][3:5]), "document_title": document["title"],
                              "section": section["section"], "title": page["title"],
                              "page": page["page"], "content": page["content"]})
    return pages


def browse_tree(node_id: str | None = None) -> dict:
    """直下のページは先頭文、指定したページ自身は全文を返す。"""
    tree = json.loads(RAG_TREE.read_text(encoding="utf-8"))
    tree["children"] = [node for node in tree["children"] if node["id"] in RAG_DOCUMENT_IDS]
    node_id = node_id or tree["id"]
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}

    def describe(node, full=False):
        info = {key: node[key] for key in ("id", "kind", "title")}
        if node["kind"] == "page":
            info.update({key: value for key, value in pages[node["id"]].items() if key != "page_id"})
            if not full:
                info["content"] = re.split(r"(?<=[。！？])|\n", info["content"].strip(), maxsplit=1)[0]
        return info

    remaining = [tree]
    while remaining:
        node = remaining.pop()
        if node["id"] == node_id:
            return {
                "node": describe(node, full=True),
                "children": [describe(child) for child in node.get("children", [])],
            }
        remaining.extend(node.get("children", []))
    raise ValueError("対象の目次ノードが見つかりません。")


def read_page(page_id: str) -> dict:
    """第1〜3回の本講義から、指定した1ページの本文と引用情報を返す。"""
    for page in load_pages(RAG_SOURCE):
        if page["page_id"] == page_id:
            return page
    raise ValueError("対象のページが見つかりません。")


def normalized_vector(values: list[float]) -> list[float]:
    """ベクトルの長さを1に揃える。"""
    norm = math.hypot(*values)
    if norm == 0:
        raise ValueError("埋め込みがゼロベクトルです。")
    return [value / norm for value in values]


def embed_text(text: str, task_type: str) -> list[float]:
    """Geminiで文章を埋め込む。入力上限を超えた場合は切り捨てず停止する。"""
    with genai.Client(api_key=get_api_key()) as client:
        count = client.models.count_tokens(model=EMBEDDING_MODEL, contents=text).total_tokens
        if count is None or count > EMBEDDING_MAX_TOKENS:
            raise ValueError(f"埋め込み入力が上限を超えるか計測不能です: {count} tokens。")
        response = client.models.embed_content(
            model=EMBEDDING_MODEL, contents=text,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIMENSIONS),
        )
    embedding = response.embeddings[0]
    if embedding.statistics and embedding.statistics.truncated:
        raise ValueError("埋め込みAPIが本文を切り捨てました。")
    return normalized_vector(embedding.values)


@contextmanager
def open_index(path: Path):
    """既存の検索DBを読み取り専用で開き、終了時に閉じる。"""
    if not path.is_file():
        raise FileNotFoundError("検索DBがありません。")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        yield db
    finally:
        db.close()


def search(query: str) -> list[dict]:
    """質問を埋め込み、近いページを最大RAG_TOP_K件返す。"""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("検索語が空です。")
    with open_index(RAG_DB) as db:
        vector = embed_text(query.strip(), "RETRIEVAL_QUERY")
        rows = db.execute("""
            SELECT page_id, document_id, lecture, document_title, section, title, page, content,
                   vec_distance_cosine(embedding, ?) AS distance
            FROM chunks ORDER BY distance, page_id LIMIT ?
        """, (sqlite_vec.serialize_float32(vector), RAG_TOP_K))
        return [dict(row) for row in rows]


def search_graph(query: str) -> dict:
    """ベクトル検索を入口に、前後ページと共通用語で候補を広げる。"""
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}
    graph = json.loads(RAG_GRAPH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph["nodes"]
             if node["kind"] == "term" or node["id"] in pages}
    adjacent = defaultdict(set)
    for edge in graph["edges"]:
        a, b = edge["source"], edge["target"]
        if edge["relation"] in ("next_page", "mentions") and a in nodes and b in nodes:
            adjacent[a].add(b)
            adjacent[b].add(a)

    seeds = [hit for hit in search(query) if hit["page_id"] in pages][:min(GRAPH_START_K, GRAPH_MAX_RESULTS)]
    seed_ids = {seed["page_id"] for seed in seeds}
    results, candidates = [], {}
    for rank, seed in enumerate(seeds):
        root = seed["page_id"]
        results.append({**pages[root], "distance": seed["distance"], "hops": 0,
                        "path": [{"id": root, "title": pages[root]["title"]}]})
        queue = deque([(root, [root])])
        visited = {root}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= GRAPH_HOPS:
                continue
            # 同じ深さなら、接続先が少ない用語からたどる。
            neighbors = sorted(adjacent[current], key=lambda n: (len(adjacent[n]), n))
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                route = path + [neighbor]
                queue.append((neighbor, route))
                if neighbor not in pages or neighbor in seed_ids:
                    continue
                frequency = max((len(adjacent[n]) for n in route if nodes[n]["kind"] == "term"), default=0)
                priority = (len(route) - 1, frequency, rank, neighbor)
                candidate = {**pages[neighbor], "hops": len(route) - 1,
                             "path": [{"id": n, "title": nodes[n]["title"]} for n in route]}
                if neighbor not in candidates or priority < candidates[neighbor][0]:
                    candidates[neighbor] = (priority, candidate)
    expanded = [candidate for _, candidate in sorted(candidates.values())]
    return {"seeds": results, "expanded": expanded[:max(0, GRAPH_MAX_RESULTS - len(results))],
            "max_hops": GRAPH_HOPS}


# ---------------------------------------------------------------------------
# 第5回 宿題（発展）: 質問との類似度で候補を選び直すGraph ＋ Tree式の段階的な読み込み
#
# 元の search_graph の課題:
#   1. 広げた候補の順番が「hop数→用語の接続数」で決まり、質問を見ていない
#   2. 54ページに出る「AIエージェント」のようなハブ用語を経由すると、ほぼ無関係なページまで届く
#   3. 入口と候補の最大10ページを全文で返すため、入力トークンが大きい
# 改良:
#   1. 候補は検索DBに保存済みのページ埋め込みと質問ベクトルの距離で並べ直す（追加のAPI呼び出しなし）
#   2. GUIDED_HUB_MAX_PAGES より多くのページに出る用語は経由しない
#   3. 入口（seeds）だけ全文、候補（candidates）は冒頭の抜粋だけ返し、全文は read_pages で読む
# ---------------------------------------------------------------------------

# v2（--graph-guided-v2）の切り替え。v1の結果を再現できるよう、既定は v1 の動き。
#   auto_full_k:  候補の上位k件には最初から全文を付ける（読むかどうかをモデルに任せず、コードで決める）
#   skip_reread:  すでに全文を渡したページを read_pages で求められたら、本文を返さずにそう伝える
GUIDED_OPTIONS = {"auto_full_k": 0, "skip_reread": False}
_delivered_full: set[str] = set()   # この実行でモデルに全文を渡したページ


def enable_guided_v2() -> None:
    GUIDED_OPTIONS.update(auto_full_k=GUIDED_V2_AUTO_FULL_K, skip_reread=True)


def page_preview(page: dict, limit: int = 120) -> str:
    """ページ本文から、タイトルの繰り返しや章の見出し行を除いた冒頭を返す。

    スライドの本文は「章の見出し→タイトル→要旨」の順で始まることが多い。
    Treeのように先頭文だけを切り出すと、見出しやタイトルしか残らないページがあるため。
    """
    skip = {page["title"].strip(), page["section"].strip()}
    lines = []
    for line in page["content"].splitlines():
        line = line.strip()
        if not line or line in skip or re.fullmatch(r"\d+\s*/\s*\d+.*", line) and page["section"] in line:
            continue
        lines.append(line)
    text = " ".join(lines)
    return text if len(text) <= limit else text[:limit] + "…"


def page_distances(query: str) -> dict[str, float]:
    """質問を1回だけ埋め込み、検索DBの全ページとの余弦距離を返す（214ページなので全件でも軽い）。"""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("検索語が空です。")
    with open_index(RAG_DB) as db:
        vector = embed_text(query.strip(), "RETRIEVAL_QUERY")
        rows = db.execute("SELECT page_id, vec_distance_cosine(embedding, ?) AS distance FROM chunks",
                          (sqlite_vec.serialize_float32(vector),))
        return {row["page_id"]: row["distance"] for row in rows}


def _guided_adjacency(pages: dict) -> tuple[dict, dict, set]:
    """前後ページ・用語の関係から、ハブ用語を除いた隣接リストを作る。"""
    graph = json.loads(RAG_GRAPH.read_text(encoding="utf-8"))
    titles = {node["id"]: node["title"] for node in graph["nodes"]}
    mentions = defaultdict(set)
    for edge in graph["edges"]:
        if edge["relation"] == "mentions" and edge["source"] in pages:
            mentions[edge["target"]].add(edge["source"])
    hubs = {term for term, members in mentions.items() if len(members) > GUIDED_HUB_MAX_PAGES}
    adjacent = defaultdict(set)
    for edge in graph["edges"]:
        a, b = edge["source"], edge["target"]
        if edge["relation"] == "next_page" and a in pages and b in pages:
            adjacent[a].add(b)
            adjacent[b].add(a)
        elif edge["relation"] == "mentions" and a in pages and b in mentions and b not in hubs:
            adjacent[a].add(b)
            adjacent[b].add(a)
    return adjacent, titles, {titles.get(h, h) for h in hubs}


def search_graph_guided(query: str) -> dict:
    """ベクトル検索の入口からグラフで候補を集め、質問との距離で選び直して抜粋だけ返す。"""
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}
    distances = {pid: d for pid, d in page_distances(query).items() if pid in pages}
    adjacent, titles, hubs = _guided_adjacency(pages)

    ranked = sorted(distances, key=lambda pid: (distances[pid], pid))
    seed_ids = ranked[:GRAPH_START_K]
    # BFS で各ページへの最短経路を記録する（同じ深さなら接続先が少ない用語＝具体的な用語を優先）
    routes = {}
    for root in seed_ids:
        queue, visited = deque([(root, [root])]), {root}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= GRAPH_HOPS:
                continue
            for neighbor in sorted(adjacent[current], key=lambda n: (len(adjacent[n]), n)):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                route = path + [neighbor]
                queue.append((neighbor, route))
                if neighbor in pages and neighbor not in seed_ids:
                    if neighbor not in routes or len(route) < len(routes[neighbor]):
                        routes[neighbor] = route

    def via(route):
        """経路を「前後ページ」「共通用語: X」の言葉にする。"""
        steps = []
        for a, b in zip(route, route[1:]):
            if a in pages and b in pages:
                steps.append("前後ページ")
            elif b not in pages:
                steps.append(f"共通用語: {titles.get(b, b)}")
        return " → ".join(steps)

    scored = sorted(
        ((distances[pid] + GUIDED_HOP_PENALTY * (len(route) - 1), pid) for pid, route in routes.items()),
    )
    cite = ("page_id", "lecture", "document_title", "section", "title", "page")
    seeds = [{**{k: pages[pid][k] for k in cite}, "distance": round(distances[pid], 4),
              "content": pages[pid]["content"]} for pid in seed_ids]
    candidates = [{**{k: pages[pid][k] for k in cite}, "distance": round(distances[pid], 4),
                   "hops": len(routes[pid]) - 1, "via": via(routes[pid]), "from_seed": routes[pid][0],
                   "preview": page_preview(pages[pid])}
                  for _, pid in scored[:GUIDED_MAX_CANDIDATES]]
    for candidate in candidates[:GUIDED_OPTIONS["auto_full_k"]]:
        candidate["content"] = pages[candidate["page_id"]]["content"]
    _delivered_full.update(item["page_id"] for item in seeds + candidates if "content" in item)
    return {"seeds": seeds, "candidates": candidates, "candidate_pool": len(routes),
            "skipped_hub_terms": sorted(hubs)}


def read_pages(page_ids: list[str]) -> dict:
    """指定したページ（最大 GUIDED_READ_MAX_PAGES 件）の全文と引用情報を返す。重複は1回にまとめる。"""
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}
    unique = list(dict.fromkeys(page_ids or []))
    if not unique:
        raise ValueError("page_ids が空です。search_graph_guided の candidates から page_id を選んでください。")
    if len(unique) > GUIDED_READ_MAX_PAGES:
        raise ValueError(f"一度に読めるのは {GUIDED_READ_MAX_PAGES} ページまでです（指定: {len(unique)}）。"
                         "質問に必要なページに絞ってください。")
    missing = [pid for pid in unique if pid not in pages]
    if missing:
        raise ValueError(f"対象のページが見つかりません: {', '.join(missing)}")
    already = [pid for pid in unique if GUIDED_OPTIONS["skip_reread"] and pid in _delivered_full]
    to_read = [pid for pid in unique if pid not in already]
    _delivered_full.update(to_read)
    result = {"pages": [{k: v for k, v in pages[pid].items() if k != "document_id"} for pid in to_read]}
    if already:
        result["already_included"] = already
        result["note"] = "already_included のページは、検索結果ですでに全文（content）を渡しています。そちらを使ってください。"
    return result



def run_full_context(agent, question: str, model, instructions: str, prompt_template: str):
    """全資料を一括投入し、検索ツールを使わずに回答する。"""
    prompt = prompt_template.format(materials=get_all_materials(), question=question)
    print(f"[full-context] 入力{len(prompt):,}文字")
    try:
        with agent.override(tools=[], instructions=instructions):
            return agent.run_sync(prompt, model=model)
    except ModelHTTPError as e:
        print(f"[full-context] APIエラー HTTP {e.status_code}: {e.body}")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="エージェントを使わず、講義資料の検索だけを実行する")
    parser.add_argument("query", help="調べたい内容")
    args = parser.parse_args()
    for i, result in enumerate(search(args.query), 1):
        print(f"\n{'=' * 60}\n検索結果 {i}\n{'=' * 60}")
        print(f"講義: {result['document_title']}")
        print(f"章: {result['section']}")
        print(f"タイトル: {result['title']}")
        print(f"ページ: {result['page']}")
        print(f"\n{result['content']}")
