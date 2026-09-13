#!/usr/bin/env python3
"""EH575 死区列验证（docs/comparison.md §6，原开放问题 1，已定案）。

EH577 固件在 103 列帧的右侧 33 列恒回硬零（有效区 70×52）。EH575 经
本脚本验证为 103 列全活跃、无死区（已定案）。对新机型复核时统计采集
到的原始帧（5356 字节 .bin）每列的非零率与方差，给出有效宽度建议，
供 EGIS0575_ACTIVE_WIDTH 使用。

用法：python3 scripts/analyze-columns.py datasets/<name>-<stamp>[/raw]
"""

import pathlib
import statistics
import sys

STRIDE_X = 103
STRIDE_Y = 52


def load_frames(directory: pathlib.Path):
    frames = []
    for p in sorted (directory.glob ("*.bin")):
        data = p.read_bytes ()
        if len (data) >= STRIDE_X * STRIDE_Y:
            frames.append (data[:STRIDE_X * STRIDE_Y])
    return frames


def column_stats(frames):
    """每列: (非零率, 帧间方差>0 的像素占比代理, 均值)."""
    stats = []
    for x in range (STRIDE_X):
        nz = 0
        values = []
        for f in frames:
            col = [f[y * STRIDE_X + x] for y in range (STRIDE_Y)]
            nz += sum (1 for v in col if v != 0)
            values.extend (col)
        nz_ratio = nz / (len (frames) * STRIDE_Y)
        mean = statistics.fmean (values) if values else 0.0
        stdev = statistics.pstdev (values) if len (values) > 1 else 0.0
        stats.append ((x, nz_ratio, stdev, mean))
    return stats


def main():
    if len (sys.argv) != 2:
        print (__doc__)
        sys.exit (1)

    d = pathlib.Path (sys.argv[1])
    if not d.exists ():
        print (f"目录不存在: {d}")
        sys.exit (1)

    raw = d / "raw"
    frames = load_frames (raw if raw.exists () else d)
    if len (frames) < 5:
        print (f"帧数不足（{len (frames)} < 5），先用 collect-dataset.sh 采集")
        sys.exit (1)

    print (f"分析 {len (frames)} 帧 × {STRIDE_X} 列\n")
    print ("列   非零率   标准差   均值")
    stats = column_stats (frames)
    for x, nz_ratio, stdev, mean in stats:
        flag = ""
        if nz_ratio < 0.01 and stdev < 1.0:
            flag = "  <-- 死区"
        elif nz_ratio < 0.05:
            flag = "  <-- 接近死区"
        print (f"{x:3d}  {nz_ratio:6.1%}  {stdev:7.2f}  {mean:7.2f}{flag}")

    # 建议有效宽度：最后一个"活跃"列 + 1（容忍零星噪声列）
    active = [x for x, nz_ratio, stdev, _ in stats
              if nz_ratio >= 0.05 or stdev >= 2.0]
    if active:
        width = max (active) + 1
        print (f"\n建议 EGIS0575_ACTIVE_WIDTH={width}"
               f"（最右活跃列 {max (active)}，全宽 {STRIDE_X}）")
        if width < STRIDE_X:
            print (f"死区宽度 {STRIDE_X - width} 列 — 与 EH577 的 33 列死区"
                   f"{'一致' if STRIDE_X - width == 33 else '不一致，需进一步确认'}")
    else:
        print ("\n未检测到活跃列，检查采集数据")


if __name__ == "__main__":
    main ()
