# EgisTec EH575 (1c7a:0575) USB 线协议

> 四源交叉验证：topni1 fork（真机验证）、Animeshz 逆向档案（pcap + Ghidra）、
> championswimmer EH577 工程（2026-06 最新）、python-egistec-eh575（独立实现）。
> 本文档是 EH575 驱动开发的协议基准。

## 1. 传输层

| 项目 | 值 |
|---|---|
| 接口 | #0（vendor-specific 0xFF/0xFF/0x00） |
| 命令端点 | bulk OUT `0x01` |
| 响应端点 | bulk IN `0x82` |
| 中断端点 | EH577 有 `0x83`/`0x84`，全部实现均未使用 |
| 传输模式 | 一写一读（命令 → 镜像长度响应），无控制传输 |

## 2. 帧格式

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
- 响应状态位：多数命令的 `resp[5]` 是状态/进度值（见轮询协议）

## 3. 图像几何（EH577 实测，EH575 待验证）

- 原始帧 5356 字节 = 103 列 × 52 行，行主序、103 字节步长
- **EH577 上右侧 33 列（src_x 70..102）恒为硬零**（固件填充非传感器像素），
  真实有效区 **70×52**；输出前必须裁掉死区，否则污染 NCC 匹配
- ⚠️ EH575 是否同样存在 33 列死区**未验证**——topni1 按全宽 103 处理（行裁到 45），
  Animeshz 按条带 103×24 处理。**Phase 3 首个实验：用真机帧统计每列非零率。**
- 像素极性：指纹图像 `FPI_IMAGE_COLORS_INVERTED`

## 4. 完整初始化序列（topni1 流程，EH575 真机验证可靠）

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

Animeshz/championswimmer 的替代流程（EH577 在用）：PRE_INIT(29) → POST_INIT(17+帧)。
EH575 语义：POST_INIT[1]（`60 01 fc`）响应为 `SIGE 01 01 01` 时表示"需要预初始化"，
跳回 PRE_INIT。topni1 的校准流程本质上就是把 PRE_INIT 的寄存器写入和校准数据
获取拆开、显式化了。python 实现有第三套等价序列（rearm 8 包）。

## 5. 采集循环

- 硬件指纹在检：轮询 `60 01`，`resp[5] > 0x03` 表示有手指（topni1；不总可靠，
  所有实现都叠加了软件判据）
- 取帧：PRE_FIRST_IMAGE(25 包，仅首个循环) → `64 14 ec` 帧 → REPEAT(8 包) +
  `64 14 ec` 帧 ×N → POST_REPEAT(9 包)
- 软件在检判据对比：
  - topni1：相邻像素差平方均值 (100, 1000) 开区间
  - championswimmer：暖背景扣除后 coverage ≥18% 且 intensity ≥10（判存在）；
    ≥25%/≥20（判可用）；idle 帧非零像素 ~111@190（热像素），真手指 1305–1594@1–105
  - python：np.std > 31.0

## 6. 已知陷阱（真机验证 2026-09-12，探测日志三轮迭代）

1. **每次 claim 的 5356 字节大读配额**：EH575 同样存在。对策已验证：接口
   release+re-claim 后**重传校准**（POST_RESET→73 14 ec→写 5356B→ack→POST_CAL），
   20 秒 156 次回收零超时
2. **`63 01 02 0f 03` 的响应是 9 字节**（topni1 表写 7 是笔误；读 7 会 overflow）
3. **bulk 端点 FIFO 残留会错位后续会话**：进程在半截响应处退出后，下个进程
   PHASE_1 第一包即超时。对策：`USBDEVFS_RESET` 软复位（scripts/reset-sensor.sh，
   uaccess ACL 即可，无需 root）
4. 校准块读取有损坏案例（尾部 ≥100 相同字节，实测 0x3f）——驱动已有检测
5. 无校准 → 全零帧；`73 14 ec` 裸发（不跟数据）第二次直接挂死传输
6. **EH575 空帧特性**：满幅低强度内容（raw_finger_pixels=5356，全部像素在
   15–150 灰度），与 EH577 的"无指帧仅 ~173 活动像素"完全不同——
   raw-finger-pixels 判据在 EH575 无区分度，coverage（背景扣除后）才是主判据

## 8. Windows 在线行为实证（2026-09-13，vmware-0.pcap 57 秒会话分析）

| 时间段 | 总线行为 | 对我们的启示 |
|---|---|---|
| 0s | 初始化：校准上传（5356B OUT）+ POST_CAL 头（15 包）| 校准每会话仅一次 |
| 10s | 6 包保活（60 00/01/40 66 + 61 0c/0b/0a = POST_REPEAT 尾族）| 静默期维持 armed 状态 |
| 10–50s | **完全静默（零轮询）** | Windows 不值守传感器，只捕获 UI 会话 |
| 50–56s | 认证会话：REPEAT 轻循环全速（~500 包/秒，8+1 包/帧）| 帧循环用 REPEAT（8 包）而非 POST_CAL（20 包）|

结论：Windows 的传感器永不过载是因为**占空比 <0.1%**（只在认证 UI 激活时全速采集几秒）。
fprintd 语义要求持续报手指状态 → 无法照抄"不值守"；我们的适配 = 230ms 慢速帧轮询
（~7% 占空比）+ 长会话退化的 USB 复位恢复（scripts/reset-sensor.sh；驱动内自动化
看门狗为待办）。`60 01` 硬件指态命令实测对按压无反应（1199 次轮询恒 0x01），
Windows 也不依赖它。

## 9. 系统级验收（2026-09-13 00:39）

传感器健康态下 fprintd 全链路：`probes=1 best_score=1086/300 => MATCH`，
coverage 51%。早退判定 + 多 probe 收集 + 双帧一致判定全部生效。
已知问题：长连续轮询（>10 分钟级）会使传感器渐进失敏（按压 coverage 从
50% 衰减到 2-5%）——USBDEVFS_RESET 立即恢复；驱动内自动检测+恢复待实现。

## 7. 尚未逆向的部分（VM 抓包候选目标；中断端点问题已由 §8 解答：Windows 未用）

- `73 14 ec` 在 EH577 的 PRE_INIT 语境下只回 7 字节短响应（非 5356 帧）的语义
- 中断端点 0x83/0x84 的用途（Windows 驱动是否使用？）
- 校准数据持久化协议（Windows 带 storage 的行为，topni1 注释提及）
- `71 …` / `97 00 00` 的寄存器语义

## 参考实现索引

| 实现 | 路径 | 备注 |
|---|---|---|
| topni1 (EH575) | `refs/topni1-libfprint/libfprint/drivers/egis0575.{c,h}` | 校准流程完整，swipe 模型 |
| championswimmer (EH577 权威最新 b19955e) | `refs/libfprint-eh577/refs/libfprint/libfprint/drivers/egis0577.{c,h}` | press+NCC，70×52，中值降噪 |
| Animeshz 原始补丁 (2021) | `refs/EgisTec-EH575/libfprint.patch` | pcap + Ghidra 在同仓库 `findings/` |
| python 独立实现 | `refs/python-egistec-eh575/open-fprintd-eh575/egis_driver/egis_driver.py` | 交叉验证序列等价性 |
