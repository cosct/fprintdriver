#!/usr/bin/env bash
# enroll→verify 闭环测试（Phase 3 核心）。
# 用法：
#   ./scripts/test-enroll-verify.sh enroll        # 录入右食指（12 次按压，每次要抬手）
#   ./scripts/test-enroll-verify.sh verify [次数]  # 验证 N 次，统计成功率与匹配分数
#   ./scripts/test-enroll-verify.sh clear         # 删除已存模板
set -euo pipefail
cd "$(dirname "$0")/.."

FINGER=${EGIS0575_TEST_FINGER:-6}   # 6=右食指, 1=左食指（可用环境变量切换槽位）
case "$FINGER" in
  6) FINGER_NAME=右食指 ;;
  1) FINGER_NAME=左食指 ;;
  *) FINGER_NAME="槽位$FINGER" ;;
esac
BIN=./libfprint/builddir/examples

case "${1:-}" in
  enroll)
    echo "== 录入${FINGER_NAME}（槽位 ${FINGER}）：需要 12 次按压，每次之间完全抬起 =="
    echo "== 关键：刻意改变按压位置，覆盖整个指尖区域 =="
    echo "==   第 1-4 次：正常中心按压 =="
    echo "==   第 5-8 次：手指稍向下/向上轻移 2-3 毫米再按 =="
    echo "==   第 9-12 次：稍向左/向右轻移 2-3 毫米再按 =="
    echo "$FINGER" | timeout -s INT -k 5 480 env G_MESSAGES_DEBUG=all \
      EGIS0575_ACTIVE_WIDTH="${EGIS0575_ACTIVE_WIDTH:-103}" \
      "$BIN/enroll" 2>&1 | tee /tmp/eh575-enroll.log | grep -E "Enroll|stage|Stage-2 at|finger|Write|complete" || true
    echo
    # grep -c 在零匹配时返回 1，pipefail 下会杀死脚本——失败时更要打印摘要
    STAGES=$(grep -c "Enroll stage" /tmp/eh575-enroll.log || true)
    echo "已录入阶段日志: ${STAGES} 条 ÷ 2 = $(( STAGES / 2 ))/12"
    ;;

  verify)
    N=${2:-5}
    if ! [[ "$N" =~ ^[0-9]+$ ]] || [[ "$N" -lt 1 ]]; then
      echo "✗ 次数必须是正整数（收到 '$N'）" >&2
      exit 1
    fi
    MATCH=0; FAIL=0
    STAMP=$(date +%H%M%S)
    echo "== 验证 ${N} 次（每次自然中心按压即可，按住 1-2 秒再抬）=="
    echo "== probe/画廊转储: datasets/verify-run-$STAMP-{1..$N} =="
    for i in $(seq 1 "$N"); do
      echo "-- 第 $i/$N 次，请按压手指 --"
      OUT=$(echo "$FINGER" | timeout -s INT -k 5 60 env G_MESSAGES_DEBUG=all \
        EGIS0575_ACTIVE_WIDTH="${EGIS0575_ACTIVE_WIDTH:-103}" \
        EGIS0575_VERIFY_DUMP_DIR="datasets/verify-run-$STAMP-$i" \
        "$BIN/verify" 2>&1 || true)
      echo "$OUT" > "/tmp/eh575-verify-$i.log"
      SCORE=$(echo "$OUT" | grep -o "best_score=[0-9/]*" | head -1 || true)
      if echo "$OUT" | grep -q "=> MATCH"; then
        MATCH=$((MATCH+1)); echo "   ✓ MATCH  $SCORE"
      else
        FAIL=$((FAIL+1)); echo "   ✗ NO-MATCH  $SCORE"
      fi
    done
    echo
    echo "== 结果: $MATCH/$N 通过，$FAIL 失败 ($(( MATCH * 100 / N ))%) =="
    echo "== 离线分析: python3 scripts/analyze-ncc.py datasets/verify-run-$STAMP-1 =="
    ;;

  clear)
    rm -f test-storage.variant
    echo "已删除测试模板存储（项目根目录）"
    ;;

  *)
    grep -m14 "^#" "$0" | sed 's/^# \{0,2\}//'
    ;;
esac
