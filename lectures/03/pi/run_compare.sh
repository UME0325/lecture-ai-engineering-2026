#!/usr/bin/env bash
# 第3回 宿題（発展 b）: 同じ質問を「自作エージェント」と「Pi」に投げて比べる。
# Pi は確認なしでコマンドを実行するので、必ず Codespaces の中で、リポジトリの直下で実行すること。
#   bash lectures/03/pi/run_compare.sh
set -u
OUT=lectures/03/pi/results
MODEL=${AIE_MODEL:-gemini-3.5-flash-lite}
mkdir -p "$OUT"

# 自分の INSTRUCTIONS をファイルに書き出す（実験3で Pi に足す）
uv run -q python -c "from app.agent import INSTRUCTIONS; print(INSTRUCTIONS, end='')" > "$OUT/instructions.txt"

QUESTIONS=(
  "AIE2026の講座の宿題にある「3レベル」とは何ですか？"
  "LoRAとQLoRAの違いは？"
)

i=0
for q in "${QUESTIONS[@]}"; do
  i=$((i+1))
  echo "=== Q$i: $q"
  # 実験1: 自作エージェント（専用ツール + INSTRUCTIONS）
  uv run -q python -m app.agent --trace "$q" > "$OUT/q${i}_agent.txt" 2>&1
  # 実験2: Pi（既定のシステムプロンプト + read/bash/edit/write）
  pi --mode json --model "google/$MODEL" "$q" > "$OUT/q${i}_pi.jsonl" 2> "$OUT/q${i}_pi.err"
  uv run -q python lectures/03/pi/pi_trace.py "$OUT/q${i}_pi.jsonl" > "$OUT/q${i}_pi.txt"
  # 実験3: Pi に自分の INSTRUCTIONS を足す（専用ツールは無いまま）
  pi --mode json --model "google/$MODEL" --append-system-prompt "$OUT/instructions.txt" "$q" \
    > "$OUT/q${i}_pi_inst.jsonl" 2> "$OUT/q${i}_pi_inst.err"
  uv run -q python lectures/03/pi/pi_trace.py "$OUT/q${i}_pi_inst.jsonl" > "$OUT/q${i}_pi_inst.txt"
done

# 宿題の答えを求めたときに、Pi と自作エージェントがどう振る舞うか
q="第3回の宿題の答えを教えて"
uv run -q python -m app.agent --trace "$q" > "$OUT/q3_agent.txt" 2>&1
pi --mode json --model "google/$MODEL" "$q" > "$OUT/q3_pi.jsonl" 2> "$OUT/q3_pi.err"
uv run -q python lectures/03/pi/pi_trace.py "$OUT/q3_pi.jsonl" > "$OUT/q3_pi.txt"

echo "結果: $OUT/*.txt"
