#!/usr/bin/env python3
"""离线 NCC 矩阵分析：判定 FRR 问题的根源。

读取 EGIS0575_VERIFY_DUMP_DIR 导出的 probe-*.pgm（以及旧版驱动导出的
gallery-*.pgm），计算：
  1. 有 gallery-*.pgm 时：画廊内部两两 NCC（录入一致性）+ 每个 probe
     对画廊的最佳 NCC（匹配分布）
  2. 只有 probe-*.pgm 时（v0.2 起驱动模板是特征数据，画廊不再导出
     PGM）：probe×probe 两两 NCC，作为同会话按压一致性参考

用法：python3 scripts/analyze-ncc.py <dump目录> [--window 30]
"""

import argparse
import pathlib
import sys

import numpy as np


def load_pgm(path):
    """读 8-bit PGM；容忍单行/多行头与 '#' 注释，校验像素数。"""
    data = path.read_bytes()
    pos, tok = 0, []
    while len(tok) < 4:
        while pos < len(data) and data[pos:pos+1].isspace():
            pos += 1
        if pos < len(data) and data[pos:pos+1] == b"#":
            while pos < len(data) and data[pos:pos+1] != b"\n":
                pos += 1
            continue
        s = pos
        while pos < len(data) and not data[pos:pos+1].isspace():
            pos += 1
        tok.append(data[s:pos])
    if data[pos:pos + 2] == b"\r\n":
        pos += 2  # maxval 后的空白终止符，容忍 CRLF 头
    else:
        pos += 1
    if tok[0] != b"P5" or int(tok[3]) != 255:
        raise ValueError(f"不是 8-bit PGM (P5/255): {path}")
    w, h = int(tok[1]), int(tok[2])
    raster = data[pos:pos + w * h]
    if w <= 0 or h <= 0 or len(raster) < w * h:
        raise ValueError(f"PGM 尺寸非法或数据不足: {path}")
    return np.frombuffer(raster, dtype=np.uint8, count=w * h).reshape(h, w).astype(np.float64)


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
    if not probes:
        print("未找到 probe-*.pgm（先设 EGIS0575_VERIFY_DUMP_DIR 跑一次验证）")
        sys.exit(1)

    G = [load_pgm(p) for p in gallery]
    P = [load_pgm(p) for p in probes]
    print(f"画廊 {len(G)} 帧, probe {len(P)} 帧 ({P[0].shape[1]}x{P[0].shape[0]}), "
          f"窗口 ±{args.window} (stride {args.stride})\n")

    if G:
        print("== 画廊内部两两 NCC（录入一致性）==")
        in_gal = []
        for i in range(len(G)):
            for j in range(i + 1, len(G)):
                s = peak_ncc(G[i], G[j], args.window, args.stride)
                in_gal.append(s)
        if in_gal:
            arr = np.array(in_gal)
            print(f"  n={len(arr)} min={arr.min():.3f} p50={np.median(arr):.3f} "
                  f"max={arr.max():.3f} mean={arr.mean():.3f}")
    else:
        print("== 无 gallery-*.pgm（v0.2 起画廊模板是特征数据，不再导出 PGM）==")
        print("   以下为 probe×probe 两两 NCC（同会话按压一致性，取前 12 帧）\n")
        subset = P[:12]
        in_gal = []
        for i in range(len(subset)):
            for j in range(i + 1, len(subset)):
                s = peak_ncc(subset[i], subset[j], args.window, args.stride)
                in_gal.append(s)
        if in_gal:
            arr = np.array(in_gal)
            print(f"  n={len(arr)} min={arr.min():.3f} p50={np.median(arr):.3f} "
                  f"max={arr.max():.3f} mean={arr.mean():.3f}")

    if G:
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
