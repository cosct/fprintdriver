#!/usr/bin/env bash
# 一次性安装临时 udev 规则，让当前用户直连 EH575 传感器做实验。
# 需要你自己跑一次（要 sudo 密码）：
#   ./scripts/setup-access.sh
# 撤销：
#   sudo rm /etc/udev/rules.d/99-eh575-test.rules && sudo udevadm control --reload

set -euo pipefail

RULE_PATH=/etc/udev/rules.d/99-eh575-test.rules

if [[ $EUID -ne 0 ]]; then
  exec sudo "$0" "$@"
fi

# 触发脚本时记住真实用户（sudo 下 SUDO_USER）；直接以 root 运行时
# 用位置参数显式给出（sudo 会覆盖命令行里赋值的 SUDO_USER，所以不能用
# sudo SUDO_USER=... 的形式）
REAL_USER=${1:-${SUDO_USER:-}}
if [[ -z "$REAL_USER" ]]; then
  echo "✗ 无法确定要授权的用户。用法："
  echo "  普通用户:  ./scripts/setup-access.sh            # 自动走 sudo，取 SUDO_USER"
  echo "  root shell: ./scripts/setup-access.sh <用户名>"
  exit 1
fi

cat > "$RULE_PATH" <<'EOF'
# fprintdriver 实验项目：允许本地用户直连 EgisTec EH575 (1c7a:0575)
# TAG+=uaccess 给当前活动会话用户 ACL 写权限，不影响 fprintd（root 始终可用）
SUBSYSTEM=="usb", ATTRS{idVendor}=="1c7a", ATTRS{idProduct}=="0575", TAG+="uaccess", MODE="0660"
EOF

udevadm control --reload

# 从 lsusb 派生当前设备节点（总线/设备号随枚举变化，不可硬编码）
LSUSB_LINE=$(lsusb -d 1c7a:0575 || true)
DEVNODE=$(printf '%s' "$LSUSB_LINE" | awk 'NR==1 {gsub(/:/, "", $4); print "/dev/bus/usb/" $2 "/" $4}')

# uaccess 的 ACL 由 systemd-logind 响应 add 动作投放；默认 trigger 动作不够，
# 这里对目标设备显式重放 add 事件
SYSPATH=""
if [[ -n "$DEVNODE" && -c "$DEVNODE" ]]; then
  SYSPATH="/sys$(udevadm info -q path -n "$DEVNODE" 2>/dev/null || true)"
fi
if [[ -n "$SYSPATH" && "$SYSPATH" != "/sys" && -d "$SYSPATH" ]]; then
  udevadm trigger --action=add "$SYSPATH" 2>/dev/null || \
    udevadm trigger --action=add --subsystem-match=usb
else
  udevadm trigger --action=add --subsystem-match=usb
fi

sleep 2

echo "规则已安装：$RULE_PATH"

if [[ -z "$DEVNODE" || ! -c "$DEVNODE" ]]; then
  echo "⚠ 当前未找到 1c7a:0575 设备节点；规则已装好，插入设备后自动生效"
  exit 0
fi

# 若 logind 仍未投放 ACL（无座席会话/触发时序问题），直接 setfacl 兜底。
# 注意：setfacl 的 ACL 在设备重插后消失（届时重跑本脚本），udev 规则仍在。
if ! getfacl "$DEVNODE" 2>/dev/null | grep -q "user:${REAL_USER}:rw"; then
  if command -v setfacl >/dev/null; then
    setfacl -m "u:${REAL_USER}:rw" "$DEVNODE" || \
      echo "⚠ setfacl 失败（exit $?）；请检查输出"
  else
    echo "⚠ 系统无 setfacl（安装 acl 包）；跳过兜底授权"
  fi
fi

echo "设备节点权限："
getfacl "$DEVNODE" 2>/dev/null || ls -l "$DEVNODE"

if getfacl "$DEVNODE" 2>/dev/null | grep -q "user:${REAL_USER}:rw"; then
  echo "✓ ${REAL_USER} 已有写权限，可以直接运行 scripts/probe.sh"
else
  echo "✗ ACL 未生效，请把上面的 getfacl 输出贴给助手"
fi
