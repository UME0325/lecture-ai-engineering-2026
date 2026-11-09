"""Pi の `--mode json` の出力（JSONL）から、app.agent の --trace と同じ形でツール呼び出しを表示する。

使い方:
    pi --mode json --model google/gemini-3.5-flash-lite "質問" > run.jsonl
    uv run python lectures/03/pi/pi_trace.py run.jsonl
"""

import json
import sys


def main(path: str) -> None:
    turns = 0
    total_tokens = 0
    final_text = ""
    with open(path, "rb") as f:
        for raw in f.read().split(b"\n"):  # Pi の JSONL は LF だけで区切る（json.md）
            raw = raw.rstrip(b"\r")
            if not raw.strip():
                continue
            ev = json.loads(raw)
            t = ev.get("type")
            if t == "turn_start":
                turns += 1  # 1ターン = LLM への1回の呼び出し（requests に相当）
            elif t == "tool_execution_start":
                print(f"[tool call]   {ev['toolName']}({json.dumps(ev['args'], ensure_ascii=False)})")
            elif t == "tool_execution_end":
                content = ev.get("result", {}).get("content", [])
                text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
                err = " (error)" if ev.get("isError") else ""
                print(f"[tool return] {ev['toolName']}{err} -> {text[:120].replace(chr(10), ' ')}…")
            elif t == "message_end" and ev["message"].get("role") == "assistant":
                msg = ev["message"]
                total_tokens += (msg.get("usage") or {}).get("totalTokens", 0)
                texts = [c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text"]
                if texts:
                    final_text = "".join(texts)
    print(f"[usage] turns(requests)={turns} total_tokens={total_tokens}")
    print("\n--- 最終回答 ---")
    print(final_text)


if __name__ == "__main__":
    main(sys.argv[1])
