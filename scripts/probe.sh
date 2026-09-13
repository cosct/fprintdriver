#!/usr/bin/env bash
# 无手指探测：20 秒轮询日志，验证初始化序列 + 背景预热 + 空轮询稳定性。
# 成功标准：
#   1) 无 "Timeout at ... recycling claim" 反复出现
#   2) 日志出现 "Background warmup: grabbed idle baseline" 且计数归零
#   3) 之后稳定循环 "below threshold" / "zero frame"
# 用法：./scripts/probe.sh [秒数]

set -euo pipefail
cd "$(dirname "$0")/.."

DUR=${1:-20}
LOG=/tmp/eh575-probe.log

echo "== EH575 无手指探测（${DUR}s），日志: $LOG =="
echo "6" | timeout -s INT -k 5 "$DUR" env G_MESSAGES_DEBUG=all \
  EGIS0575_ACTIVE_WIDTH="${EGIS0575_ACTIVE_WIDTH:-103}" \
  ./libfprint/builddir/examples/enroll 2>&1 | tee "$LOG" || true

echo
echo "== 结果摘要 =="
# grep -c 在零匹配时返回 1，pipefail 下会中止脚本；探测失败时恰恰要打摘要
echo "背景预热帧数: $(grep -c "Background warmup: grabbed" "$LOG" || true)"
echo "claim 配额回收次数(真实): $(grep -c "budget reached" "$LOG" || true)"
echo "超时次数: $(grep -c "Timeout at" "$LOG" || true)"
echo "无指轮询帧数: $(grep -c "below threshold\|zero frame" "$LOG" || true)"
grep -m3 "finger_detected:" "$LOG" || echo "(无 finger_detected 日志)"
