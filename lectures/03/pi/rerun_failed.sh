#!/usr/bin/env bash
# run_compare.sh でレート制限（HTTP 429）により失敗した3件を、間隔をあけて取り直す。
#   bash lectures/03/pi/rerun_failed.sh
set -u
OUT=lectures/03/pi/results
MODEL=${AIE_MODEL:-gemini-3.5-flash-lite}
WAIT=${WAIT:-70}

echo "Q2 を Pi + INSTRUCTIONS で実行"
pi --mode json --model "google/$MODEL" --append-system-prompt "$OUT/instructions.txt" "LoRAとQLoRAの違いは？" \
  > "$OUT/q2_pi_inst.jsonl" 2> "$OUT/q2_pi_inst.err"
uv run -q python lectures/03/pi/pi_trace.py "$OUT/q2_pi_inst.jsonl" > "$OUT/q2_pi_inst.txt"
echo "${WAIT}秒待ちます"; sleep "$WAIT"

q="第3回の宿題の答えを教えて"
echo "Q3 を自作エージェントで実行"
uv run -q python -m app.agent --trace "$q" > "$OUT/q3_agent.txt" 2>&1
echo "${WAIT}秒待ちます"; sleep "$WAIT"

echo "Q3 を Pi で実行"
pi --mode json --model "google/$MODEL" "$q" > "$OUT/q3_pi.jsonl" 2> "$OUT/q3_pi.err"
uv run -q python lectures/03/pi/pi_trace.py "$OUT/q3_pi.jsonl" > "$OUT/q3_pi.txt"

grep -l "429\|レート制限" "$OUT"/q2_pi_inst.jsonl "$OUT"/q3_agent.txt "$OUT"/q3_pi.jsonl 2>/dev/null \
  && echo "まだ 429 が出ています。数分あけて、もう一度実行してください" || echo "3件とも取得できました"
