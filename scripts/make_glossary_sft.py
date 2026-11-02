"""第2回 宿題（発展）: 用語集から LoRA 用の学習データと評価データを作る。

make_sft_dataset.py（配布版）を次の点で拡張したもの。
- 出力を演習と同じ JSON 1 行（{"answer": 定義文, "needs_review": 真偽値}）にし、形式と内容を自動で採点できるようにする
- system プロンプトを入れ、評価時と同じ入力で学習させる
- 用語集に無い用語（根拠なし）を学習にも評価にも入れ、「知らない語に確認を求めるか」を測れるようにする
- 評価用の質問は、学習で見た言い回し（seen）・学習に無い言い回し（paraphrase）・学習に無い別名（alias）・
  用語集に無い語（unknown_far / unknown_near）の 5 種類に分け、どこで崩れるかを見分けられるようにする

使い方（Codespaces でも Colab でも、標準ライブラリだけで動く）:
    uv run python scripts/make_glossary_sft.py            # data/sft/ に書き出す
    uv run python scripts/make_glossary_sft.py --check    # 件数と重複チェックだけ表示

書き出すファイル（data/sft/）:
    glossary_sft_train.jsonl  学習用。各行が {"messages": [system, user, assistant]}（ノートブックの to_chat と同じ形式）
    glossary_sft_valid.jsonl  検証用（同じ形式）
    glossary_eval.json        評価用の質問と正解（question, category, surface, gold_id, needs_review）
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.tools import load_glossary, search_glossary  # noqa: E402  第3回の検索ツールをそのまま使う

OUT_DIR = ROOT / "data" / "sft"
SEED = 42

SYSTEM = (
    "あなたはAIエンジニアリング実践講座（AIE2026）の用語集の回答係です。"
    "用語の意味を聞かれたら、用語集の定義で答えてください。必ず JSON 1 行で答えます。"
    "形式: {\"answer\": 文字列, \"needs_review\": 真偽値}。"
    "用語集に無い用語は answer に『用語集に記載がありません。確認が必要です。』と書き、needs_review を true にします。"
)
UNKNOWN_ANSWER = "用語集に記載がありません。確認が必要です。"

# 言い回しはテンプレート単位で train / valid / test に分ける（学習で見た文がそのまま test に出ないように）
TRAIN_TEMPLATES = ["「{t}」とは何ですか？", "{t}について簡単に説明してください。"]  # 配布版と同じ 2 つ
VALID_TEMPLATES = ["{t}の意味を教えてください。"]
TEST_TEMPLATES = ["{t}って何？", "講座で出てきた{t}がよく分かりません。どういうものですか？", "{t}を一言で説明すると？"]

# 用語集に無い語（根拠なし）。どれも app.tools.search_glossary で「見つかりませんでした」になるものを選ぶ
# （near のみ、名前が用語集の語と似ている／一部が重なる語を意図的に入れ、検索側の誤ヒットも観察する）
UNKNOWN_TRAIN = [
    "RAG（検索拡張生成）", "埋め込みベクトル", "ベクトルデータベース", "RLHF", "DPO", "知識蒸留", "Mixture of Experts", "KVキャッシュ",
    "Transformer", "Self-Attention", "トークナイザー", "Docker", "ビームサーチ", "ドロップアウト",
]
UNKNOWN_TEST_FAR = [
    "強化学習", "GAN", "拡散モデル", "ベイズ最適化", "Kubernetes", "勾配ブースティング", "交差検証", "データ拡張",
]
UNKNOWN_TEST_NEAR = [
    "DoRA", "継続事前学習", "A2A", "LangGraph", "MCPインスペクター", "早期終了", "重み減衰", "GitHub Actions",
]

N_SEEN = 10        # 学習で見た言い回しそのまま（暗記できたかの確認）
N_PARAPHRASE = 24  # 学習に無い言い回し
N_ALIAS = 10       # 学習に出していない別名で聞く


def _alias_ok(a: str) -> bool:
    # 「r」「env」「prefix」のように単独では意味が決まらない短い別名は、質問に使わない
    return len(a) >= 3 and a.lower() not in {"env", "prefix", "fetch", "rank"}


def chat(question: str, answer: str, needs_review: bool) -> dict:
    target = json.dumps({"answer": answer, "needs_review": needs_review}, ensure_ascii=False)
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"質問: {question}"},
        {"role": "assistant", "content": target},
    ]}


def build() -> tuple[list[dict], list[dict], list[dict]]:
    rng = random.Random(SEED)
    terms = load_glossary()
    train, valid, test = [], [], []

    # 学習: 正式名 × 2 テンプレート、最初の別名 × 1 テンプレート。2 つ目以降の別名は test 用に取っておく
    held_out_alias = []
    for t in terms:
        for tpl in TRAIN_TEMPLATES:
            train.append(chat(tpl.format(t=t["term"]), t["definition"], False))
        usable = [a for a in t["aliases"] if _alias_ok(a)]
        if usable:
            train.append(chat(TRAIN_TEMPLATES[0].format(t=usable[0]), t["definition"], False))
            held_out_alias += [(t, a) for a in usable[1:]]
    for u in UNKNOWN_TRAIN:
        for tpl in TRAIN_TEMPLATES:
            train.append(chat(tpl.format(t=u), UNKNOWN_ANSWER, True))

    # 検証: 学習に無いテンプレート。根拠あり 9 件・根拠なし 3 件
    for t in rng.sample(terms, 9):
        valid.append(chat(VALID_TEMPLATES[0].format(t=t["term"]), t["definition"], False))
    for u in rng.sample(UNKNOWN_TRAIN, 3):
        valid.append(chat(VALID_TEMPLATES[0].format(t=u), UNKNOWN_ANSWER, True))

    def q(question, category, surface, gold_id):
        test.append({"question": question, "category": category, "surface": surface,
                     "gold_id": gold_id, "needs_review": gold_id is None})

    for t in rng.sample(terms, N_SEEN):
        q(TRAIN_TEMPLATES[0].format(t=t["term"]), "seen", t["term"], t["id"])
    for i, t in enumerate(rng.sample(terms, N_PARAPHRASE)):
        q(TEST_TEMPLATES[i % len(TEST_TEMPLATES)].format(t=t["term"]), "paraphrase", t["term"], t["id"])
    for i, (t, a) in enumerate(rng.sample(held_out_alias, min(N_ALIAS, len(held_out_alias)))):
        q(TEST_TEMPLATES[i % len(TEST_TEMPLATES)].format(t=a), "alias", a, t["id"])
    for i, u in enumerate(UNKNOWN_TEST_FAR):
        q(TEST_TEMPLATES[i % len(TEST_TEMPLATES)].format(t=u), "unknown_far", u, None)
    for i, u in enumerate(UNKNOWN_TEST_NEAR):
        q(TEST_TEMPLATES[i % len(TEST_TEMPLATES)].format(t=u), "unknown_near", u, None)
    return train, valid, test


def check(train, valid, test) -> None:
    def user_text(ex):
        return ex["messages"][1]["content"]
    tr = {user_text(e) for e in train}
    va = {user_text(e) for e in valid}
    te = {f"質問: {e['question']}" for e in test if e["category"] != "seen"}
    assert not (tr & va), f"train と valid で質問が重複: {tr & va}"
    assert not (tr & te), f"train と test で質問が重複: {tr & te}"
    assert all(f"質問: {e['question']}" in tr for e in test if e["category"] == "seen"), "seen は train に含まれるはず"
    for u in UNKNOWN_TRAIN + UNKNOWN_TEST_FAR:
        assert "見つかりませんでした" in search_glossary(u), f"根拠なしのはずの {u} が用語集検索でヒットする"
    near_hits = {u: "見つかりませんでした" not in search_glossary(u) for u in UNKNOWN_TEST_NEAR}
    cats = {}
    for e in test:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
    n_neg = sum(e["messages"][2]["content"].endswith("true}") for e in train)
    print(f"train={len(train)}（根拠なし {n_neg}） valid={len(valid)} test={len(test)} {cats}", file=sys.stderr)
    print(f"unknown_near のうち用語集検索が何か返す語: {[u for u, h in near_hits.items() if h]}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="書き出さずに件数と重複だけ確認する")
    args = ap.parse_args()
    train, valid, test = build()
    check(train, valid, test)
    if args.check:
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in [("glossary_sft_train.jsonl", train), ("glossary_sft_valid.jsonl", valid)]:
        (OUT_DIR / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (OUT_DIR / "glossary_eval.json").write_text(
        json.dumps({"system": SYSTEM, "unknown_answer": UNKNOWN_ANSWER, "questions": test}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"wrote {OUT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
