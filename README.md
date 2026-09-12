# fprintdriver — EgisTec EH575 (1c7a:0575) libfprint 驱动研究

目标：让 EgisTec EH575 指纹传感器（Acer SFX14-41G 等机型）在 Linux 上真正可用
（识别精度达到 KDE 解锁水准），最终产出可提交给
[libfprint 上游](https://gitlab.freedesktop.org/libfprint/libfprint)的驱动。

## 发布状态（2026-09-13）

- **驱动已可用**：press 采集架构 + Windows 引擎 matcher 移植，真机
  （KDE 锁屏 / fprintd / Bitwarden polkit 解锁）验证通过；匹配器验证
  数字见 `docs/comparison.md` §6（离线 FRR/FAR 双 0%，真机阈值余量 ≥20）
- **驱动代码**：[cosct/libfprint-egis0575](https://github.com/cosct/libfprint-egis0575)
  （upstream libfprint + `egis0575` 驱动，分支 `egis0575`，LGPL-2.1+）
- **Arch 用户**：AUR 包 `libfprint-egis0575`（`yay -S libfprint-egis0575`）
- **待办**：调优阈值收集更多机型反馈，整理上游化补丁

## 目录结构

```
docs/     文档索引见 docs/README.md（中英双语）：
          protocol 线协议基准 · comparison 架构对比与匹配器终局 ·
          windows-engine-tables 引擎系数表提取与复刻
scripts/  测试与数据采集工具（见下）
tools/    评测小工具（egis0575-matcher-test / eval_bz3 / hwpoll）
PKGBUILD  本地开发打包（AUR 版本见 AUR 仓库）
```

驱动源码在独立仓库（`libfprint/` 本地目录不随本仓库分发）：

```bash
git clone -b egis0575 https://github.com/cosct/libfprint-egis0575
```

不随仓库分发的内容（体积或隐私原因）：`refs/`（四份第三方参考实现，自行
clone）、`datasets/`（指纹原始帧，生物特征数据）、`acerdrv/`（Acer 官方
Windows 驱动，版权归 EgisTec/Acer）。

## 复现研究流程

```bash
# 1) 一次性：装临时 udev 规则获得设备直连权限（要 sudo 密码）
./scripts/setup-access.sh

# 2) 无手指探测 20s：验证初始化稳定、背景预热完成、空轮询无超时
./scripts/probe.sh

# 3) 采数据集：按脚本提示按压（先空 3 秒做背景预热）
./scripts/collect-dataset.sh press-test 60

# 4) 死区列验证（EH575 的有效宽度是 70 还是 103？）
python3 scripts/analyze-columns.py datasets/press-test-*/
```

驱动可调环境变量：
- `EGIS0575_ACTIVE_WIDTH` — 有效列数（默认 103；已定案无死区，仅供实验）
- `EGIS0575_SKIP_CALIBRATION=1` — 跳过校准上传走 EH577 式初始化（已知会全零帧，仅 A/B 用）
- `EGIS0575_PGM_DEBUG_DIR` / `_LOG` / `_INTERVAL_MS` — PGM 数据集采集
- `EGIS0575_FRAME_DUMP_DIR` — 原始 5356 字节帧转储
- `EGIS0575_LIVE_FRAME_PATH` — 实时帧写单个 PGM（看图用）
- `EGIS0575_DISABLE_STRETCH=1` — 关闭 stretch5 对比度增强

## 关键结论速查

1. EH575 是**图像传感器**（103×52 小图、主机侧匹配，**无死区列**），
   不是 match-on-chip
2. swipe+Bozorth3（topni1 驱动）是精度差的根源；经典匹配方案（NCC/
   Bozorth3/POC/SigFM/方向场）在本传感器原始信噪比下**全部**无法区分
   同人异指（实验数据见 docs/comparison.md §5）
3. 本驱动 = EH577 的 press 采集架构 + topni1 校准初始化（EH575 出图
   必要条件）+ **Windows 引擎 matcher 移植**（11 取向脊线滤波器组 +
   512bit 描述子 + 海明/RANSAC 评分，系数实抽自 vendor DLL；离线
   FRR/FAR 双 0%，真机集成验收通过）
4. `01 01 01 → 重跑 PRE_INIT` 是 EH575 的本义错误处理
5. topni1 源码有个 GCC14+ 致命笔误 `FPI_DEVICE_Egis0575`（已修，值得回报）
