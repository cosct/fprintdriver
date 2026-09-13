#!/usr/bin/env bash
# 系统级替换：打包并安装 libfprint-egis0575-experimental（含 EH575 驱动）。
# 会在安装步骤要 sudo 密码。回退方法见脚本尾注释。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 打包并安装 libfprint-egis0575（本地开发树版本）=="
makepkg -f -i

echo
echo "== 重启 fprintd =="
sudo systemctl restart fprintd 2>/dev/null || true

echo
echo "完成。系统级录入："
echo "  fprintd-enroll            # 录入默认手指（右食指按提示按 12 次）"
echo "  fprintd-verify            # 验证"
echo
echo "回退到官方 libfprint 或其他 AUR 包："
echo "  yay -S libfprint            # 官方包（conflicts 自动处理）"
