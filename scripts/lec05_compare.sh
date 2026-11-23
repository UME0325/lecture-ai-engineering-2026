#!/usr/bin/env bash
# 第5回 演習・宿題（発展）の比較実行。Codespaces で `bash scripts/lec05_compare.sh` と実行する。
# 結果は lectures/05/logs/ に1実行1ファイルで保存し、最後に summary.md にまとめる。
# 無料枠のレート制限を避けるため、実行の間に待ち時間を入れ、レート制限なら待って再実行する。
set -u
cd "$(dirname "$0")/.."
LOG=lectures/05/logs
mkdir -p "$LOG"
WAIT=${AIE_WAIT:-20}
export PYDANTIC_AI_NO_BANNER=1

declare -A Q
Q[q1_lora]='第2回の説明では、LoRAは何を固定し何を学習しますか？ QLoRAは何を加えますか？'
Q[q2_memory]='第3回の例では、コンパクションとセッションをまたぐメモリはどう違いますか。日々のメモはすべて長期メモリに入りますか'
Q[q3_cross]='第2回では「FTでは直らない」とされたものは何で、どう補うとされていますか。第3回のメモリは、それとは別にどんな問題を解決しますか'
Q[q4_absent]='今回作ったRAGの実測平均応答時間と正答率を教えてください'

run() {  # run <name> <args...>
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

# 演習 STEP 2：検索だけ
run step2_retrieval_only -m app.retrieval "LoRA QLoRA 違い"
# 演習 STEP 1・3・4 と 宿題（発展）の比較
for q in q1_lora q2_memory q3_cross q4_absent; do
  run "${q}__vector"       -m app.agent --trace                "${Q[$q]}"
  run "${q}__graph"        -m app.agent --graph --trace        "${Q[$q]}"
  run "${q}__guided"       -m app.agent --graph-guided --trace "${Q[$q]}"
done
run q1_lora__full_context  -m app.agent --full-context --trace "${Q[q1_lora]}"
run q1_lora__tree          -m app.agent --tree --trace         "${Q[q1_lora]}"
run q2_memory__tree        -m app.agent --tree --trace         "${Q[q2_memory]}"

uv run python scripts/lec05_summarize.py > "$LOG/summary.md"
echo "完了: $LOG/summary.md"
