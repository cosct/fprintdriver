# libfprint-eh575 — EgisTec EH575 (1c7a:0575) Linux 指纹驱动

> [English version](README.en.md)

目标：让 EgisTec EH575 指纹传感器（Acer SFX14-41G 等机型）在 Linux 上真正可用
（识别精度达到 KDE 解锁水准），最终产出可提交给
[libfprint 上游](https://gitlab.freedesktop.org/libfprint/libfprint)的驱动。

## 发布状态（2026-09-13）

- **驱动已可用**：press 采集架构 + Windows 引擎 matcher 移植，真机
  （KDE 锁屏 / fprintd / Bitwarden polkit 解锁）验证通过；匹配器验证
  数字见 `docs/comparison.md` §6（小样本单机验证：离线 6 同人/12 异人
  FRR/FAR 0%，离线阈值余量 ≥20，真机冒充分离余量 15——证据强度说明
  见该节末尾）
- **驱动代码**：随本仓库分发（`libfprint/`，git subtree 保留上游
  libfprint 完整历史 + egis0575 驱动提交；原独立 fork 仓库
  cosct/libfprint-egis0575 已由本仓库取代）
- **Arch 用户**：AUR 包 `libfprint-egis0575`（`yay -S libfprint-egis0575`）
- **待办**：调优阈值收集更多机型反馈，整理上游化补丁
- **2026-09-13 优化**：录入同点重复拒绝（Windows HIGHLY_SIMILARITY 移植，
  阈值 650 实测拦截精准）、校准块跨 close 主机缓存（Windows 同型）、
  两档空闲轮询（230/500ms）——详见 docs/optimization-plan.md
- **升级注意**：v0.2.0 的模板序列化丢失取向字段（打分必需），该版本
  录入的指纹在新驱动下无法通过验证——升级后请 `fprintd-delete` 删除
  旧指纹并重新录入

## 目录结构

```
docs/     文档索引见 docs/README.md（中英双语）：
          protocol 线协议基准 · comparison 架构对比与匹配器终局 ·
          windows-engine-tables 引擎系数表提取与复刻 ·
          windows-enrollment Windows 端录入机制 · optimization-plan 优化计划
libfprint/ 驱动源码（git subtree：upstream libfprint 完整历史 + egis0575
          驱动，LGPL-2.1+）；构建目录 builddir/ 不入库
scripts/  测试与数据采集工具（见下）
tools/    评测小工具（egis0575-matcher-test / eval_bz3 / hwpoll）
packaging/ 发布打包配方：aur/PKGBUILD（AUR 正本）· deb/build-deb.sh ·
          rpm/libfprint-egis0575.spec —— 由本仓库的 release workflow 在打
          egis0575-v* 标签时调用，产物挂 GitHub Release 并自动更新 AUR
PKGBUILD  本地开发打包（从工作树构建；AUR 版本见 AUR 仓库）
```

不随仓库分发的内容（体积或隐私原因）：`refs/`（四份第三方参考实现，自行
clone）、`datasets/`（指纹原始帧，生物特征数据）、`acerdrv/`（Acer 官方
Windows 驱动，版权归 EgisTec/Acer）。

## 复现研究流程

```bash
# 0) 一次性：clone 本仓库并构建（驱动源码已在树内 libfprint/）
#    （需要 meson≥0.62 + ninja，以及 glib2/libusb/libgusb/pixman/openssl/
#     libgudev 的开发包；Arch 上再加 gobject-introspection 和 gtk-doc）
git clone https://github.com/cosct/libfprint-eh575 && cd libfprint-eh575
meson setup libfprint/builddir libfprint
meson compile -C libfprint/builddir

# 1) 一次性：装临时 udev 规则获得设备直连权限（要 sudo 密码）
./scripts/setup-access.sh

# 2) 无手指探测 20s：验证初始化稳定、背景预热完成、空轮询无超时
./scripts/probe.sh

# 3) 采数据集：按脚本提示按压（先空 3 秒做背景预热）
./scripts/collect-dataset.sh press-test 60

# 4) 列活跃度分析（已定案：103 列全活跃、无死区；脚本供新机型复核）
python3 scripts/analyze-columns.py datasets/press-test-*/
```

驱动可调环境变量：
- `EGIS0575_ACTIVE_WIDTH` — 有效列数（默认 103；已定案无死区，仅供实验）
- `EGIS0575_SKIP_CALIBRATION=1` — 跳过校准上传走 EH577 式初始化（已知会全零帧，仅 A/B 用）
- `EGIS0575_PGM_DEBUG_DIR` / `_LOG` / `_INTERVAL_MS` / `_CONTROL` — PGM 数据集采集
  （采集模式下驱动持续转储处理帧，enroll/verify 等动作不会完成——仅供
  无状态探测采集，配合 `_CONTROL` 指向的门控文件可暂停/恢复）
- `EGIS0575_FRAME_DUMP_DIR` — 原始 5356 字节帧转储
- `EGIS0575_LIVE_FRAME_PATH` — 实时帧写单个 PGM（看图用）
- `EGIS0575_VERIFY_DUMP_DIR` — 验证时转储 probe 与画廊特征数日志（离线匹配分析）
- `EGIS0575_DISABLE_STRETCH=1` — 关闭 stretch5 对比度增强
- `EGIS0575_ENROLL_SIM_THRESHOLD` — 录入同点重复拒绝阈值（默认 650；
  0 关闭。标定见 docs/enroll-sim-calibration.txt 与
  scripts/calibrate-enroll-sim.py）
- `EGIS0575_DEBUG_MAX_FILES` — PGM/原始帧转储的文件数上限（默认 5000，
  约 26 MB 原始帧；所有调试转储均为 0600 权限、目录 0700，因其含
  生物特征数据）

Python 脚本依赖见 `requirements.txt`（Python ≥ 3.9 + numpy；eval_sigfm
另需 OpenCV，hwpoll 另需 pyusb）。本仓库（文档/脚本/工具）与驱动同样
按 LGPL-2.1-or-later 授权（见 `LICENSE`）。

## 深入阅读地图（问题 → 章节）

| 想了解 | 去处 |
|---|---|
| 线协议与命令语义（CET300 命令集、初始化序列、未解项） | [protocol §2 命令与响应格式](docs/protocol.md#2-命令与响应格式) · [§4 初始化序列](docs/protocol.md#4-初始化序列) · [§10 尚未逆向的部分](docs/protocol.md#10-尚未逆向的部分) |
| 为什么 swipe/NCC/Bozorth3/SigFM 全不行 | [comparison §5 匹配器实验史：七个方案为何全败](docs/comparison.md#5-匹配器实验史七个方案为何全败2026-09-12) |
| 匹配器从哪来、系数提取与验证数字 | [windows-engine-tables](docs/windows-engine-tables.md) · [comparison §6 Windows 引擎移植：终局方案](docs/comparison.md#6-windows-引擎移植终局方案) |
| Windows 怎么做录入（同点拒绝的出处） | [windows-enrollment](docs/windows-enrollment.md) |
| Windows 实际怎么用传感器（校准缓存、占空比） | protocol §4C 会话实序 · §7 在线行为实证（[docs/protocol.md](docs/protocol.md)） |
| 稳定性：陷阱清单、看门狗、挂死恢复 | [protocol §8 已知陷阱](docs/protocol.md#8-已知陷阱全部真机验证2026-09-1213) · [comparison §7 稳定性工程](docs/comparison.md#7-稳定性工程成果全部真机验证) |
| 录入相似阈值怎么标定 | [enroll-sim-calibration.txt](docs/enroll-sim-calibration.txt) · [calibrate-enroll-sim.py](scripts/calibrate-enroll-sim.py) |
| 优化路线与已完成项 | [optimization-plan.md](docs/optimization-plan.md) |

文档索引（双语对照）见 [docs/README.md](docs/README.md)。

## 关键结论速查

1. EH575 是**图像传感器**（103×52 小图、主机侧匹配，**无死区列**），
   不是 match-on-chip（几何定案见 [protocol §3](docs/protocol.md#3-图像几何已定案)）
2. swipe+Bozorth3（topni1 驱动）是精度差的根源；经典匹配方案（NCC/
   Bozorth3/POC/SigFM/方向场）在本传感器原始信噪比下**全部**无法区分
   同人异指（[comparison §5](docs/comparison.md#5-匹配器实验史七个方案为何全败2026-09-12)）
3. 本驱动 = EH577 的 press 采集架构 + topni1 校准初始化（EH575 出图
   必要条件）+ **Windows 引擎 matcher 移植**（11 取向脊线滤波器组 +
   512bit 描述子 + 海明/平移簇评分，系数实抽自 vendor DLL；小样本
   离线 FRR/FAR 0%，真机集成验收通过，见
   [comparison §6](docs/comparison.md#6-windows-引擎移植终局方案)）
4. `01 01 01 → 重跑 PRE_INIT` 是 EH575 的本义错误处理
   （[protocol §4B](docs/protocol.md#4-初始化序列)）
5. 早前记录的 topni1 `FPI_DEVICE_Egis0575` 笔误经全历史复核**不存在**
   （[comparison §8](docs/comparison.md#8-已发现的上游问题)），无需回报
