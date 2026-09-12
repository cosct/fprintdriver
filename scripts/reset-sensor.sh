#!/usr/bin/env bash
# 软件复位 EH575 传感器（等价于重拔插），清除 bulk 端点 FIFO 残留/挂死状态。
# 不需要 root（依赖 setup-access.sh 装的 uaccess ACL）。
# 用法：./scripts/reset-sensor.sh

set -euo pipefail

NODE=$(lsusb | grep -i "1c7a:0575" | awk '{print "/dev/bus/usb/" $2 "/" $4}' | tr -d ':' | head -1)

if [[ -z "$NODE" || ! -c "$NODE" ]]; then
  # lsusb 总线/设备号带冒号（如 003 003），格式化路径
  BUS=$(lsusb | grep -i "1c7a:0575" | awk '{print $2}')
  DEV=$(lsusb | grep -i "1c7a:0575" | awk '{print $4}' | tr -d ':')
  NODE="/dev/bus/usb/$BUS/$DEV"
fi

echo "复位 $NODE ..."
python3 - "$NODE" <<'EOF'
import fcntl, sys

USBDEVFS_RESET = 21780  # _IO('U', 20)
node = sys.argv[1]
fd = open(node, "wb")
try:
    fcntl.ioctl(fd, USBDEVFS_RESET)
    print("USBDEVFS_RESET 已发出")
finally:
    fd.close()
EOF

sleep 2
lsusb | grep -i "1c7a:0575" && echo "设备已重新枚举" || echo "⚠ 设备未出现在 lsusb"
echo "提示：重枚举后 uaccess ACL 需要几秒生效；若 probe 报权限错误，重跑 ./scripts/setup-access.sh"
