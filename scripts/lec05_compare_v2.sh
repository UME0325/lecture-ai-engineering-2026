#!/usr/bin/env bash
# 第5回 宿題（発展）v2 の比較。`bash scripts/lec05_compare_v2.sh` で実行する（約10分）。
# v2 を各質問3回、ばらつきを見るため q2 のベクトル検索と v1 を追加で2回ずつ実行する。
set -u
cd "$(dirname "$0")/.."
LOG=lectures/05/logs
WAIT=${AIE_WAIT:-20}
export PYDANTIC_AI_NO_BANNER=1

declare -A Q
Q[q1_lora]='第2回の説明では、LoRAは何を固定し何を学習しますか？ QLoRAは何を加えますか？'
Q[q2_memory]='第3回の例では、コンパクションとセッションをまたぐメモリはどう違いますか。日々のメモはすべて長期メモリに入りますか'
Q[q3_cross]='第2回では「FTでは直らない」とされたものは何で、どう補うとされていますか。第3回のメモリは、それとは別にどんな問題を解決しますか'
Q[q4_absent]='今回作ったRAGの実測平均応答時間と正答率を教えてください'

run() {
  local name=$1; shift
  local out="$LOG/$name.txt"
  if [[ -s "$out" ]] && grep -q '^\[usage\]' "$out"; then echo "skip $name（実行済み）"; return; fi
  for attempt in 1 2 3; do
    echo "run  $name（$attempt 回目）"
    uv run python "$@" > "$out" 2>&1
    if grep -q 'レート制限\|混み合っています' "$out"; then sleep 65; continue; fi
    break
  done
  sleep "$WAIT"
}

for r in 1 2 3; do
  for q in q1_lora q2_memory q3_cross q4_absent; do
    run "${q}__guided_v2_r$r" -m app.agent --graph-guided-v2 --trace "${Q[$q]}"
  done
done
for r in 2 3; do
  run "q2_memory__vector_r$r" -m app.agent --trace                "${Q[q2_memory]}"
  run "q2_memory__guided_r$r" -m app.agent --graph-guided --trace "${Q[q2_memory]}"
done

uv run python scripts/lec05_summarize.py > "$LOG/summary.md"
echo "完了: $LOG/summary.md"
