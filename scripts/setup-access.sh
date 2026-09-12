#!/usr/bin/env bash
# 一次性安装临时 udev 规则，让当前用户直连 EH575 传感器做实验。
# 需要你自己跑一次（要 sudo 密码）：
#   ./scripts/setup-access.sh
# 撤销：
#   sudo rm /etc/udev/rules.d/99-eh575-test.rules && sudo udevadm control --reload

set -euo pipefail

RULE_PATH=/etc/udev/rules.d/99-eh575-test.rules
DEVNODE=/dev/bus/usb/003/003

if [[ $EUID -ne 0 ]]; then
  exec sudo "$0" "$@"
fi

# 触发脚本时记住真实用户（sudo 下 SUDO_USER）
REAL_USER=${SUDO_USER:-wjk}

cat > "$RULE_PATH" <<'EOF'
# fprintdriver 实验项目：允许本地用户直连 EgisTec EH575 (1c7a:0575)
# TAG+=uaccess 给当前活动会话用户 ACL 写权限，不影响 fprintd（root 始终可用）
SUBSYSTEM=="usb", ATTRS{idVendor}=="1c7a", ATTRS{idProduct}=="0575", TAG+="uaccess", MODE="0660"
EOF

udevadm control --reload

# uaccess 的 ACL 由 systemd-logind 响应 add 动作投放；默认 trigger 动作不够，
# 这里对目标设备显式重放 add 事件
SYSPATH="/sys$(udevadm info -q path -n "$DEVNODE" 2>/dev/null || true)"
if [[ -n "$SYSPATH" && "$SYSPATH" != "/sys" && -d "$SYSPATH" ]]; then
  udevadm trigger --action=add "$SYSPATH" 2>/dev/null || \
    udevadm trigger --action=add --subsystem-match=usb
else
  udevadm trigger --action=add --subsystem-match=usb
fi

sleep 2

# 若 logind 仍未投放 ACL（无座席会话/触发时序问题），直接 setfacl 兜底。
# 注意：setfacl 的 ACL 在设备重插后消失（届时重跑本脚本），udev 规则仍在。
if ! getfacl "$DEVNODE" 2>/dev/null | grep -q "user:${REAL_USER}:rwx"; then
  setfacl -m "u:${REAL_USER}:rw" "$DEVNODE" 2>/dev/null || true
fi

echo "规则已安装：$RULE_PATH"
echo "设备节点权限："
getfacl "$DEVNODE" 2>/dev/null || ls -la /dev/bus/usb/003/

if getfacl "$DEVNODE" 2>/dev/null | grep -q "user:${REAL_USER}:rw"; then
  echo "✓ ${REAL_USER} 已有写权限，可以直接运行 scripts/probe.sh"
else
  echo "✗ ACL 未生效，请把上面的 getfacl 输出贴给助手"
fi
