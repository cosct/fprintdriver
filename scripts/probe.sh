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
if ! [[ "$DUR" =~ ^[0-9]+$ ]] || [[ "$DUR" -lt 1 ]]; then
  echo "✗ 秒数必须是正整数（收到 '$DUR'）" >&2
  exit 1
fi
# mktemp：/tmp 固定文件名可被其他用户符号链接预占
LOG=$(mktemp /tmp/eh575-probe.XXXXXX.log)

if [[ ! -x ./libfprint/builddir/examples/enroll ]]; then
  echo "✗ 找不到 ./libfprint/builddir/examples/enroll（先按 README 构建）" >&2
  exit 1
fi

echo "== EH575 无手指探测（${DUR}s），日志: $LOG =="
set +e
echo "6" | timeout -s INT -k 5 "$DUR" env G_MESSAGES_DEBUG=all \
  EGIS0575_ACTIVE_WIDTH="${EGIS0575_ACTIVE_WIDTH:-103}" \
  ./libfprint/builddir/examples/enroll 2>&1 | tee "$LOG"
RUN_RC=${PIPESTATUS[1]}
set -e
# 0=stdin 结束前正常退出；124=timeout 到点；130=SIGINT——其余是真失败，
# 摘要里的全 0 不可信，明确警告而不是吞掉
if [[ "$RUN_RC" -ne 0 && "$RUN_RC" -ne 124 && "$RUN_RC" -ne 130 ]]; then
  echo "⚠ enroll 以退出码 $RUN_RC 结束（非超时/中断），下面摘要可能不完整" >&2
fi

echo
echo "== 结果摘要 =="
# grep -c 在零匹配时返回 1，pipefail 下会中止脚本；探测失败时恰恰要打摘要
echo "背景预热帧数: $(grep -c "Background warmup: grabbed" "$LOG" || true)"
echo "claim 配额回收次数(真实): $(grep -c "budget reached" "$LOG" || true)"
echo "超时次数: $(grep -c "Timeout at" "$LOG" || true)"
echo "无指轮询帧数: $(grep -c "below threshold\|zero frame" "$LOG" || true)"
grep -m3 "finger_detected:" "$LOG" || echo "(无 finger_detected 日志)"
