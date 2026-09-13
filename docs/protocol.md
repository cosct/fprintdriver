# EgisTec EH575 (1c7a:0575) USB 线协议

> **状态：已定案。** 本文档是 EH575 驱动开发的协议基准，全部条目经四源交叉验证，
> 其中标"真机验证"的条目在 2026-09-12/13 真机会话中确认。驱动已发布：
> [cosct/libfprint-egis0575](https://github.com/cosct/libfprint-egis0575)（分支
> `egis0575`）· AUR `libfprint-egis0575`。
> [English version](protocol.en.md)

四源交叉验证：topni1 fork（真机验证）、Animeshz 逆向档案（pcap + Ghidra）、
championswimmer EH577 工程（2026-06 最新）、python-egistec-eh575（独立实现）。

## 1. 传输层

| 项目 | 值 |
|---|---|
| 接口 | #0（vendor-specific 0xFF/0xFF/0x00） |
| 命令端点 | bulk OUT `0x01` |
| 响应端点 | bulk IN `0x82` |
| 中断端点 | EH577 有 `0x83`/`0x84`；**Windows 在线会话实测未使用**（§7），忽略 |
| 传输模式 | 一写一读（命令 → 镜像长度响应），无控制传输 |

## 2. 命令与响应格式

- 命令以 ASCII `EGIS`（`45 47 49 53`）开头，后跟"寄存器风格"字节：
  - `60 xx` — 状态/查询类
  - `61 xx vv` — 寄存器写入
  - `62 67 03` / `63 …`（9–18 字节）— 多字节参数块
  - `71 …` — 参数块（出现在 PRE_FIRST_IMAGE / POST_REPEAT）
  - `97 00 00` — 传感器复位（topni1 PRE_RESET 第 3 包）
- 响应以 `SIGE`（`53 49 47 45`）开头，长度与命令相同（例外见下）
- 关键例外命令：
  - `64 14 ec` → 读一帧图像，**5356 字节**（103×52）
  - `72 14 ec` → 读校准块，**5356 字节**
  - `73 14 ec` → 进入校准上传模式（7 字节短响应），随后主机直接写 5356 字节校准数据
- 响应状态位：多数命令的 `resp[5]` 是状态/进度值（见 §4 轮询）
- 已知笔误更正：`63 01 02 0f 03` 的响应是 **9 字节**（topni1 表写 7；读 7 会 overflow）

## 3. 图像几何（已定案）

- 原始帧 5356 字节 = 103 列 × 52 行，行主序、103 字节步长
- **EH575 无死区列**（2026-09-12 数据集分析定案）：600 帧列活跃度统计，
  全部 103 列非零率 100%、跨帧 std 11–20。EH577 存在的 33 列硬零死区
  （其真实有效区 70×52）在 EH575 **不存在**，全宽 103 直接可用
- 像素极性：指纹图像 `FPI_IMAGE_COLORS_INVERTED`
- EH575 空帧特性：满幅低强度内容（全部 5356 像素在 15–150 灰度），
  与 EH577 的"无指帧仅 ~173 活动像素"完全不同——raw-finger-pixels 类
  判据在 EH575 无区分度，**背景扣除后的 coverage 是唯一有效判据**（§6）

## 4. 初始化序列

### A. 校准流程（topni1 流程；EH575 出图的**必要条件**，生产路径）

```
A. 读校准（每次 open 重新读，不持久化）
   1. PHASE_1（16 包，含寄存器配置 + AGC 设置）
   2. 轮询 60 2d 直到 resp[5]==0x05
   3. PHASE_3（2 包：62 67 03 / 63 33 03 73 10 01）
   4. 轮询 60 35 直到 resp[5]==0x00
   5. PHASE_5（4 包）
   6. 72 14 ec → 读 5356 字节校准块
   校准块损坏检测：尾部若出现 ≥100 个相同字节（实测 0x3f）则丢弃重试
B. 复位 + 上传校准
   7. PRE_RESET（3 包，末包 97 00 00 复位）
   8. 轮询 60 00 直到 resp[5]!=0x00（复位完成）
   9. POST_RESET（13 包）
  10. 73 14 ec → 写 5356 字节校准数据 → 读 7 字节确认
  11. POST_CALIBRATION（20 包，末包 64 14 ec 顺便收一帧暖机）
```

### B. PRE_INIT/POST_INIT 流程（EH577 路线；EH575 上**不可用**）

Animeshz/championswimmer 的替代流程：PRE_INIT(29 包) → POST_INIT(17 包+帧)。
EH575 语义：POST_INIT[1]（`60 01 fc`）响应为 `SIGE 01 01 01` 时表示"需要
预初始化"，跳回 PRE_INIT 重跑（这是 EH575 的本义错误处理）。

**2026-09-12 真机验证结论**：EH575 走 B 路线时全部命令正确应答、
`64 14 ec` 稳定回 5356 字节，但**帧内容全零**——校准上传是 EH575 出图的
必要条件。topni1 的校准流程本质上是把 PRE_INIT 的寄存器写入和校准数据
获取拆开、显式化了。另证实 `73 14 ec` 裸发（不跟 5356 字节数据）第一次
得 507ms 全零响应、第二次直接挂死传输。驱动中 B 路线仅保留为
`EGIS0575_SKIP_CALIBRATION=1` 的 A/B 实验路径。python 实现有第三套等价
序列（rearm 8 包）。

## 5. 采集循环

- 取帧：PRE_FIRST_IMAGE(25 包，仅首个循环) → `64 14 ec` 帧 → REPEAT(8 包) +
  `64 14 ec` 帧 ×N → POST_REPEAT(9 包)
- **采集结束必须发关闭序列**（topni1 POST_REPEAT，含 AGC/曝光 `71` 族）：
  防止传感器滞留连续采集模式导致按压失灵（真机两次复现）
- Windows 的帧循环同样用 REPEAT（8 包）而非 POST_CAL（20 包），见 §7

## 6. 指纹在检

- 硬件在检：轮询 `60 01`，topni1 以 `resp[5] > 0x03` 判手指——**不可靠**。
  真机实测对按压无反应（1199 次轮询恒 0x01），Windows 也不依赖它（§7）
- 软件判据（各实现对比）：
  - topni1：相邻像素差平方均值 (100, 1000) 开区间
  - championswimmer（本驱动采用）：暖背景扣除后 coverage ≥18% 且
    intensity ≥10（判存在）；≥25%/≥20（判可用）。EH575 数据集验证：
    无指帧 coverage 最高 17% vs 手指帧最低 19%，边界干净（56 指/450 空帧）
  - python：np.std > 31.0

## 7. Windows 在线行为实证（2026-09-13，vmware-0.pcap 57 秒会话分析）

| 时间段 | 总线行为 | 对驱动的启示 |
|---|---|---|
| 0s | 初始化：校准上传（5356B OUT）+ POST_CAL 头（15 包）| 校准每会话仅一次 |
| 10s | 6 包保活（60 00/01/40 66 + 61 0c/0b/0a = POST_REPEAT 尾族）| 静默期维持 armed 状态 |
| 10–50s | **完全静默（零轮询）** | Windows 不值守传感器，只捕获 UI 会话 |
| 50–56s | 认证会话：REPEAT 轻循环全速（~500 包/秒，8+1 包/帧）| 帧循环用 REPEAT（8 包）而非 POST_CAL（20 包）|

结论：Windows 的传感器不过载是因为**占空比 <0.1%**（只在认证 UI 激活时
全速采集几秒）。fprintd 语义要求持续报手指状态 → 无法照抄"不值守"；
本驱动的适配 = 230ms 慢速帧轮询（~7% 占空比）+ 驱动内传感器健康看门狗
（10 分钟预防性重初始化 + weak-press 失敏检测自动重跑校准链）；硬挂死
场景用手动 `scripts/reset-sensor.sh`。

## 8. 已知陷阱（全部真机验证，2026-09-12/13）

1. **每次 claim 的 5356 字节大读配额**：同 topni1 报告。对策已验证：接口
   release+re-claim 后**重传校准**（POST_RESET→73 14 ec→写 5356B→ack→POST_CAL），
   20 秒 156 次回收零超时；每 claim 配额从 6 帧放宽到 200（更激进的重传
   3.5 分钟 1865 次会导致固件挂死，见 comparison.md §7）
2. **bulk 端点 FIFO 残留会错位后续会话**：进程在半截响应处退出后，下个
   进程 PHASE_1 第一包即超时。对策：`USBDEVFS_RESET` 软复位
   （scripts/reset-sensor.sh，uaccess ACL 即可，无需 root）
3. 校准块读取有损坏案例（尾部 ≥100 相同字节，实测 0x3f）——驱动已有检测
4. 无校准 → 全零帧（§4B）；`73 14 ec` 裸发二次挂死传输
5. `63 01 02 0f 03` 响应 9 字节（§2）
6. **长连续轮询渐进失敏**：>10 分钟级连续轮询使按压 coverage 从 50% 衰减
   到 2–5%——驱动内看门狗已实现自动恢复（10 分钟预防性重初始化 +
   weak-press 检测触发校准链重跑）；硬挂死场景用 `USBDEVFS_RESET` 手动恢复

## 9. 系统级验收（2026-09-13 00:39）

传感器健康态下 fprintd 全链路：`probes=1 best_score=1086/300 => MATCH`，
coverage 51%。早退判定（~2s）+ 多 probe 收集 + 双帧一致判定全部生效
（matcher 细节与阈值标定见 windows-engine-tables.md）。

## 10. 尚未逆向的部分

- `73 14 ec` 在 EH577 PRE_INIT 语境下只回 7 字节短响应的语义
- 校准数据持久化协议（Windows 带 storage 的行为，topni1 注释提及）
- `71 …` / `97 00 00` 的寄存器语义

（中断端点 0x83/0x84 的疑问已由 §7 解答：Windows 未使用。）

## 参考实现索引

| 实现 | 路径 | 备注 |
|---|---|---|
| topni1 (EH575) | `refs/topni1-libfprint/libfprint/drivers/egis0575.{c,h}` | 校准流程完整，swipe 模型 |
| championswimmer (EH577 权威最新 b19955e) | `refs/libfprint-eh577/refs/libfprint/libfprint/drivers/egis0577.{c,h}` | press 架构基座，70×52 |
| Animeshz 原始补丁 (2021) | `refs/EgisTec-EH575/libfprint.patch` | pcap + Ghidra 在同仓库 `findings/` |
| python 独立实现 | `refs/python-egistec-eh575/open-fprintd-eh575/egis_driver/egis_driver.py` | 交叉验证序列等价性 |

参考库不随本仓库分发（见根 README），可按上表路径自行获取。
