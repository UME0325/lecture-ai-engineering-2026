"""第4回 宿題（実装）: コードで判定できる基準を、決定的に判定する。

LLM に聞かなくても文字列やツールの記録（trace）から決まる基準をまとめて判定し、
人のラベル・LLM の判定と並べて「どの基準はコードに任せられるか」を確かめる。

使い方:
    uv run python -m app.code_checks                          # 判定だけ（API キー不要）
    uv run python -m app.code_checks \
        --labels lectures/04/my_labels.jsonl \
        --judge lectures/04/my_judge_result.json \
        --out lectures/04/my_code_checks.md                   # 人・LLM と比べて Markdown に保存

各ケースの "checks" に、そのケースで見るべきことを書いておく（書いていない項目は n/a）。
    "tools":    呼ばれるべきツール名のリスト（trace を見る）
    "lectures": 末尾の「第N回」として正しい回のリスト
    "hide_definitions_of": この回の用語の定義（＝確認問題の答え）が回答に出ていないか
    "no_code_block": 宿題の答えとなるコードを書いていないか
"""

import argparse
import json
import re
from pathlib import Path

from app import tools
from app.judge import ROOT, check_lecture_mark, load_labels, read_jsonl

DEFAULT_CASES = ROOT / "data" / "eval" / "my_cases.jsonl"
MAX_CHARS = 400  # 「簡潔」の代わりに使う文字数の上限（コードブロックは数えない）

# (キー, 表示名, 比べる人のラベルの基準 or None)
CHECKS = [
    ("lecture_mark", "回の表示", "lecture_mark"),
    ("lecture_correct", "回の正しさ", None),
    ("tools_called", "ツールを使った", "grounding"),
    ("no_code_block", "コードを書かない", "hint"),
    ("hide_definitions", "答えを見せない", None),
    ("length", f"{MAX_CHARS}字以内", "clarity"),
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _last_line(answer: str) -> str:
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def body_length(answer: str) -> int:
    """コードブロックと末尾の「関係する回」の行を除いた本文の文字数。"""
    body = re.sub(r"```.*?```", "", answer, flags=re.S)
    lines = [line for line in body.strip().splitlines() if line.strip()]
    if lines and re.search(r"第\s*\d+\s*回", lines[-1]):
        lines = lines[:-1]
    return len(_norm("".join(lines)))


def run_checks(case: dict) -> dict[str, dict]:
    """1 件の回答に、コードで決まる基準を当てる。戻り値は {キー: {verdict, reason}}。"""
    answer = case.get("answer", "")
    spec = case.get("checks", {})
    out: dict[str, dict] = {}

    def put(key, verdict, reason):
        out[key] = {"verdict": verdict, "reason": reason}

    mark = check_lecture_mark(answer)
    put("lecture_mark", mark, "末尾（最後の行）に「第N回」がある" if mark == "pass" else "末尾に「第N回」がない")

    if "lectures" in spec:
        shown = {int(n) for n in re.findall(r"第\s*(\d+)\s*回", _last_line(answer))}
        want = set(spec["lectures"])
        if not shown:
            put("lecture_correct", "fail", f"末尾に回の表示がない（正しくは第{'・'.join(map(str, sorted(want)))}回）")
        elif shown <= want:
            put("lecture_correct", "pass", f"末尾の回 {sorted(shown)} は参照の回 {sorted(want)} に含まれる")
        else:
            put("lecture_correct", "fail", f"末尾の回 {sorted(shown)} に、参照にない回 {sorted(shown - want)} がある")
    else:
        put("lecture_correct", "n/a", "このケースでは見ない")

    if "tools" in spec:
        if "trace" not in case:
            put("tools_called", "n/a", "trace がない（--generate で生成し直すと記録される）")
        else:
            called = [t["tool"] for t in case["trace"]]
            missing = [t for t in spec["tools"] if t not in called]
            if missing:
                put("tools_called", "fail", f"{', '.join(missing)} を呼んでいない（呼んだ: {called or 'なし'}）")
            else:
                put("tools_called", "pass", f"呼んだツール: {called}")
    else:
        put("tools_called", "n/a", "このケースでは見ない")

    if spec.get("no_code_block"):
        code = "```" in answer or re.search(r"^\s*(def|class|import|from)\s", answer, flags=re.M)
        put("no_code_block", "fail" if code else "pass", "コード（``` や def/import の行）がある" if code else "コードはない")
    else:
        put("no_code_block", "n/a", "このケースでは見ない")

    if "hide_definitions_of" in spec:
        lec = spec["hide_definitions_of"]
        a = _norm(answer)
        leaked = [e["term"] for e in tools.load_glossary()
                  if e["lecture"] == lec and _norm(e["definition"])[:20] in a]
        put("hide_definitions", "fail" if leaked else "pass",
            f"確認問題の答え（{', '.join(leaked)} の定義）が回答に出ている" if leaked else "定義の文はそのまま出ていない")
    else:
        put("hide_definitions", "n/a", "このケースでは見ない")

    n = body_length(answer)
    put("length", "pass" if n <= MAX_CHARS else "fail", f"本文 {n} 字（上限 {MAX_CHARS} 字）")
    return out


# ---------------------------------------------------------------- 人・LLM と比べる
def compare(cases: list[dict], results: dict[str, dict], labels: dict[str, dict] | None,
            judge: dict | None) -> str:
    """コード判定を、人のラベル（対応する基準）と LLM の判定に並べた Markdown を返す。"""
    verdicts = (judge or {}).get("verdicts", {})
    mark = {"pass": "T", "fail": "F", "unsure": "?", "n/a": "–", None: " "}
    lines = ["## コード判定の一覧", "", "| id | 種類 | " + " | ".join(n for _, n, _ in CHECKS) + " | 呼んだツール |",
             "|---|---|" + "---|" * len(CHECKS) + "---|"]
    for c in cases:
        r = results[c["id"]]
        called = ", ".join(t["tool"] for t in c.get("trace", [])) or "なし"
        lines.append(f"| {c['id']} | {c.get('category', '')} | "
                     + " | ".join(mark[r[k]["verdict"]] for k, _, _ in CHECKS) + f" | {called} |")

    lines += ["", "## 人のラベル・LLM の判定との一致（対応する基準があるものだけ）", "",
              "| コード判定 | 比べる基準 | 対象 | 人と一致 | LLM と一致 |", "|---|---|---|---|---|"]
    detail = []
    for key, name, crit in CHECKS:
        if not crit:
            continue
        ids = [c["id"] for c in cases if results[c["id"]][key]["verdict"] in ("pass", "fail")]
        h = [cid for cid in ids if labels and labels.get(cid, {}).get(crit) in ("pass", "fail")]
        j = [cid for cid in ids if verdicts.get(cid, {}).get(crit, {}).get("verdict") in ("pass", "fail")]
        h_ok = sum(results[cid][key]["verdict"] == labels[cid][crit] for cid in h)
        j_ok = sum(results[cid][key]["verdict"] == verdicts[cid][crit]["verdict"] for cid in j)
        lines.append(f"| {name} | {crit} | {len(ids)} 件 | {h_ok}/{len(h) if labels else '–'} | {j_ok}/{len(j) if judge else '–'} |")
        for cid in h:
            if results[cid][key]["verdict"] != labels[cid][crit]:
                jv = verdicts.get(cid, {}).get(crit, {}).get("verdict", "–")
                detail.append(f"- #{cid} {name}：コード={results[cid][key]['verdict']} 人={labels[cid][crit]} LLM={jv}"
                              f"（{results[cid][key]['reason']}）")

    lines += ["", "## 人とコードが割れた項目", ""] + (detail or ["- なし"])

    only_code = [f"- #{c['id']} {n}：{results[c['id']][k]['reason']}" for c in cases for k, n, crit in CHECKS
                 if crit is None and results[c["id"]][k]["verdict"] == "fail"]
    lines += ["", "## 人の 5 基準にはない、コードだけが見た失敗", ""] + (only_code or ["- なし"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="コードで決まる基準を判定し、人・LLM と比べる")
    p.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    p.add_argument("--labels", type=Path, help="人のラベル（jsonl）")
    p.add_argument("--judge", type=Path, help="app.judge の結果（json）")
    p.add_argument("--out", type=Path, help="Markdown の保存先")
    args = p.parse_args(argv)

    cases = read_jsonl(args.cases)
    if not any(c.get("answer") for c in cases):
        raise SystemExit("回答がありません。先に app.judge --generate で回答を生成してください")
    results = {c["id"]: run_checks(c) for c in cases}
    labels = load_labels(args.labels) if args.labels and args.labels.exists() else None
    judge = json.loads(args.judge.read_text(encoding="utf-8")) if args.judge and args.judge.exists() else None
    md = compare(cases, results, labels, judge)
    print(md)
    if args.out:
        args.out.write_text("# 第4回 宿題（実装）：コード判定\n\n" + md, encoding="utf-8")
        print(f"→ {args.out} に保存しました")


if __name__ == "__main__":
    main()
