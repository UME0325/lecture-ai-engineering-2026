"""lectures/05/logs/*.txt から、方式ごとの時間・トークン・費用・ツール呼び出し・引用ページを表にする。"""

import re
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "lectures/05/logs"


def parse(text: str) -> dict:
    get = lambda pattern: (m.group(1) if (m := re.search(pattern, text)) else "")
    usage = re.search(r"\[usage\] 入力 ([\d,]+) tokens / 出力 ([\d,]+) tokens / モデル応答 (\d+) 回", text)
    calls = re.findall(r"\[tool call\]\s+(\w+)\(", text)
    answer = text.split("--- trace ---")[0]
    # 「第3回・PDF p.39, p.65」「第2回・PDF p.46, 53」のように、1つの回に複数ページを並べた書き方も拾う
    cited = set()
    for lecture, pages in re.findall(r"第(\d+)回[・\s]*PDF\s*(p\.\s*\d+(?:\s*[,、・]\s*(?:p\.\s*)?\d+)*)", answer):
        cited.update((lecture, page) for page in re.findall(r"\d+", pages))
    cited = sorted(cited, key=lambda x: (int(x[0]), int(x[1])))
    return {
        "time": get(r"\[time\] 回答完了まで ([\d.]+) 秒"),
        "in": usage.group(1) if usage else "", "out": usage.group(2) if usage else "",
        "req": usage.group(3) if usage else "",
        "cost": get(r"\[cost\] 生成APIの推定コスト: (\S+)"),
        "calls": ", ".join(f"{name}×{calls.count(name)}" for name in dict.fromkeys(calls)) or "なし",
        "cited": ", ".join(f"{l}回p.{p}" for l, p in cited) or "なし",
        "error": "エラー" if re.search(r"APIエラー|Traceback|レート制限", text) else "",
    }


def main() -> None:
    print("| 質問 | 方式 | 時間(秒) | 入力/出力 tokens | 応答回数 | 推定費用 | ツール呼び出し | 回答中の引用 | 備考 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for path in sorted(LOG.glob("q*__*.txt")):
        question, method = path.stem.split("__")
        r = parse(path.read_text(encoding="utf-8"))
        print(f"| {question} | {method} | {r['time']} | {r['in']}/{r['out']} | {r['req']} | {r['cost']} "
              f"| {r['calls']} | {r['cited']} | {r['error']} |")


if __name__ == "__main__":
    main()
