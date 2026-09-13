#!/usr/bin/env python3
"""SigFM 算法的 Python 移植（精确对齐 refs/sigfm/cpp/match.cpp）。

流程：SIFT → BFMatcher knn(k=2) → Lowe 比率(0.75) → 去重 →
成对向量长度一致性(5%) → 角度 sin/cos 一致性(5%) 投票 → ≥5 票 = 匹配。

用法：python3 scripts/eval_sigfm.py <gallery_dir> <probe_dir> [--invert]
"""
import argparse
import pathlib
import sys

import cv2
import numpy as np

DISTANCE_MATCH = 0.75
LENGTH_MATCH = 0.05
ANGLE_MATCH = 0.05
MIN_MATCH = 5

sift = cv2.SIFT_create()
bf = cv2.BFMatcher_create()


def load_pgm(path):
    """读 8-bit PGM；容忍单行/多行头、'#' 注释与 CRLF，校验像素数。"""
    data = path.read_bytes()
    pos, tokens = 0, []
    while len(tokens) < 4:
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':
            while pos < len(data) and data[pos] != 0x0a:
                pos += 1
            continue
        s = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        tokens.append(data[s:pos])
    if data[pos:pos + 2] == b"\r\n":
        pos += 2  # maxval 后的空白终止符，容忍 CRLF 头
    else:
        pos += 1
    if tokens[0] != b"P5" or int(tokens[3]) != 255:
        raise ValueError(f"不是 8-bit PGM (P5/255): {path}")
    w, h = int(tokens[1]), int(tokens[2])
    raster = data[pos:pos + w * h]
    if w <= 0 or h <= 0 or len(raster) < w * h:
        raise ValueError(f"PGM 尺寸非法或数据不足: {path}")
    img = np.frombuffer(raster, np.uint8, w * h).reshape(h, w)
    return img


def sigfm_score(img1, img2, invert=False):
    a = load_pgm(img1) if isinstance(img1, pathlib.Path) else img1
    b = load_pgm(img2) if isinstance(img2, pathlib.Path) else img2
    if invert:
        a, b = 255 - a, 255 - b

    kp1, d1 = sift.detectAndCompute(a, None)
    kp2, d2 = sift.detectAndCompute(b, None)
    if d1 is None or d2 is None or len(kp1) < MIN_MATCH or len(kp2) < MIN_MATCH:
        return 0, min(len(kp1), len(kp2))

    matches = bf.knnMatch(d1, d2, k=2)
    pts = []
    for m in matches:
        if len(m) == 2 and m[0].distance < DISTANCE_MATCH * m[1].distance:
            pts.append((kp1[m[0].queryIdx].pt, kp2[m[0].trainIdx].pt))
    pts = list(dict.fromkeys(pts))
    if len(pts) < MIN_MATCH:
        return 0, len(pts)

    angles = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            v1 = (pts[i][0][0] - pts[j][0][0], pts[i][0][1] - pts[j][0][1])
            v2 = (pts[i][1][0] - pts[j][1][0], pts[i][1][1] - pts[j][1][1])
            l1 = np.hypot(*v1)
            l2 = np.hypot(*v2)
            if l1 == 0 or l2 == 0:
                continue
            lo, hi = min(l1, l2), max(l1, l2)
            if 1 - lo / hi <= LENGTH_MATCH:
                product = l1 * l2
                dot = v1[0] * v2[0] + v1[1] * v2[1]
                cross = v1[0] * v2[1] - v1[1] * v2[0]
                # match.cpp: sin = pi/2 + asin(dot/product), cos = acos(cross/product)
                s_ = np.pi / 2 + np.arcsin(np.clip(dot / product, -1, 1))
                c_ = np.arccos(np.clip(cross / product, -1, 1))
                angles.append((s_, c_))

    if len(angles) < MIN_MATCH:
        return 0, len(angles)

    count = 0
    for i in range(len(angles)):
        for j in range(i + 1, len(angles)):
            s1, c1 = angles[i]
            s2, c2 = angles[j]
            ms, mc = max(s1, s2), max(c1, c2)
            if ms == 0 or mc == 0:
                continue  # 严格反平行向量对退化出的零角度，无投票意义
            if (1 - min(s1, s2) / ms <= ANGLE_MATCH and
                    1 - min(c1, c2) / mc <= ANGLE_MATCH):
                count += 1
    return count, len(pts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gallery_dir", type=pathlib.Path)
    ap.add_argument("probe_dir", type=pathlib.Path)
    ap.add_argument("--invert", action="store_true", help="反转灰度极性")
    args = ap.parse_args()

    gallery = sorted(args.gallery_dir.glob("gallery-*.pgm"))
    probes = sorted(args.probe_dir.glob("probe-*.pgm"))
    if not gallery or not probes:
        print("需要 gallery-*.pgm 与 probe-*.pgm")
        sys.exit(1)

    for p in probes:
        best, best_kp = 0, 0
        for g in gallery:
            score, kp = sigfm_score(p, g, invert=args.invert)
            if score > best:
                best, best_kp = score, kp
        print(f"{p.name}: votes={best} (matched_pts={best_kp}) "
              f"{'MATCH' if best >= MIN_MATCH else 'no'}")


if __name__ == "__main__":
    main()
