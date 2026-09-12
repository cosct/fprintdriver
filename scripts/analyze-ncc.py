#!/usr/bin/env python3
"""离线 NCC 矩阵分析：判定 FRR 问题的根源。

读取 EGIS0575_VERIFY_DUMP_DIR 导出的 gallery-*.pgm 与 probe-*.pgm，
计算：
  1. 画廊内部两两 NCC（录入一致性）
  2. 每个 probe 对画廊的最佳 NCC（匹配分布）
  3. 分组统计（真手指/冒充手指的分数分离度）

用法：python3 scripts/analyze-ncc.py <dump目录> [--window 30]
"""

import argparse
import pathlib
import sys

import numpy as np

STRIDE = 103


def load_pgm(path):
    data = path.read_bytes()
    if not data.startswith(b"P5"):
        raise ValueError(f"not P5: {path}")
    # 驱动写出的头是单行 "P5 W H 255\n"
    nl = data.index(b"\n")
    tokens = data[:nl].split()
    w, h = int(tokens[1]), int(tokens[2])
    return np.frombuffer(data[nl + 1:], dtype=np.uint8, count=w * h).reshape(h, w).astype(np.float64)


def ncc_at(a, b, dx, dy):
    ha, wa = a.shape
    hb, wb = b.shape
    y0a, y0b = max(0, dy), max(0, -dy)
    x0a, x0b = max(0, dx), max(0, -dx)
    yend = min(ha, hb + dy)
    xend = min(wa, wb + dx)
    if yend <= y0a or xend <= x0a:
        return -1.0
    A = a[y0a:yend, x0a:xend]
    B = b[y0b:y0b + (yend - y0a), x0b:x0b + (xend - x0a)]
    if A.size < 200:
        return -1.0
    A = A - A.mean()
    B = B - B.mean()
    den = A.std() * B.std()
    if den < 1e-9:
        return -1.0
    return float((A * B).mean() / den)


def peak_ncc(a, b, window, stride=1):
    best = -1.0
    for dy in range(-window, window + 1, stride):
        for dx in range(-window, window + 1, stride):
            best = max(best, ncc_at(a, b, dx, dy))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=pathlib.Path)
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--stride", type=int, default=2)
    args = ap.parse_args()

    gallery = sorted(args.dir.glob("gallery-*.pgm"))
    probes = sorted(args.dir.glob("probe-*.pgm"))
    if not gallery or not probes:
        print(f"需要 gallery-*.pgm 和 probe-*.pgm（先设 EGIS0575_VERIFY_DUMP_DIR 跑一次验证）")
        sys.exit(1)

    G = [load_pgm(p) for p in gallery]
    P = [load_pgm(p) for p in probes]
    print(f"画廊 {len(G)} 帧 ({G[0].shape[1]}x{G[0].shape[0]}), probe {len(P)} 帧, 窗口 ±{args.window} (stride {args.stride})\n")

    print("== 画廊内部两两 NCC（录入一致性）==")
    in_gal = []
    for i in range(len(G)):
        for j in range(i + 1, len(G)):
            s = peak_ncc(G[i], G[j], args.window, args.stride)
            in_gal.append(s)
    if in_gal:
        arr = np.array(in_gal)
        print(f"  n={len(arr)} min={arr.min():.3f} p50={np.median(arr):.3f} max={arr.max():.3f} mean={arr.mean():.3f}")

    print("\n== probe × 画廊 最佳 NCC ==")
    best_per_probe = []
    for k, p in enumerate(P):
        scores = [peak_ncc(p, g, args.window, args.stride) for g in G]
        best = max(scores)
        hits = sum(1 for s in scores if s >= 0.50)
        best_per_probe.append(best)
        print(f"  probe-{k:03d}: best={best:.3f} hits(≥0.50)={hits}/{len(G)}")

    arr = np.array(best_per_probe)
    print(f"\n  probe 分布: min={arr.min():.3f} p50={np.median(arr):.3f} max={arr.max():.3f}")
    print("  （真手指应集中在 >0.5，冒充手指应 <0.4；据此定阈值）")


if __name__ == "__main__":
    main ()
