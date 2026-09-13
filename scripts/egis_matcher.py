#!/usr/bin/env python3
"""Windows EgisTec 引擎的 Python 复刻（第一阶段：结构忠实、参数近似）。

依据（docs/windows-engine-tables.md + comparison.md §7）：
  1. 平场归一化（背景除法近似：减局部均值）
  2. 梯度张量 → 兴趣点（3×3 极大值 + NMS）
  3. 每点方向（梯度角）+ 11×11 金字塔权重方向直方图描述子 → 二值化
  4. 海明 NN + Lowe 比率 + 中值平移几何一致性投票（Windows 参数：≥5 票）

用法：
  python3 scripts/egis_matcher.py <gallery_dir> <probe_dir>
"""
import argparse
import pathlib
import sys

import numpy as np

MIN_FEATURES = 11
MIN_MATCHED = 5
HAMMING_BUDGET = 115        # 512bit 顶档描述子（Windows 原值 115/512）
ANGLE_TOL_DEG = 12
POS_TOL_PX = 8
NBINS = 32                  # 方向 bin 数（11.25°/bin，atan2 LUT 级精度）

W11 = None                  # 11x11 金字塔权重（从 DLL 提取的 11 抽头核外积）

# DLL RVA 0x3ffd0 提取的 11 个对称核（全部正系数，和=32768）= 取向脊线模板
# 取向4 在 DLL 中是 7 抽头（早前提取误补成 9 抽头，2026-09-13 更正）
FIR_BANK = [
    (1785, 8003, 13193, 8002, 1785),
    (2319, 8011, 12109, 8010, 2319),
    (2806, 7951, 11253, 7952, 2806),
    (706, 3097, 7524, 10114, 7524, 3097, 706),
    (950, 3402, 7313, 9438, 7313, 3402, 950),
    (1200, 3646, 7104, 8870, 7102, 3646, 1200),
    (361, 1415, 3757, 6748, 8205, 6749, 3757, 1415, 361),
    (486, 1632, 3877, 6517, 7746, 6515, 3877, 1632, 486),
    (622, 1832, 3962, 6295, 7346, 6295, 3962, 1832, 622),
    (216, 753, 1985, 3967, 6011, 6904, 6011, 3967, 1985, 753, 216),
    (289, 889, 2134, 3986, 5800, 6572, 5800, 3986, 2134, 889, 289),
]

def oriented_filter_bank(img):
    """11 取向脊线匹配滤波。返回 (增强图, 每像素取向角)。

    每 θ：旋转图像 → 沿行方向与核相关（模板为单脊线截面凸起）→
    旋转回原坐标；逐像素取 |response| 最大者。
    """
    import cv2
    H, W = img.shape
    best = np.full((H, W), -1e18)
    best_ang = np.zeros((H, W))
    for i, taps in enumerate(FIR_BANK):
        theta = 180.0 * i / len(FIR_BANK)
        k = np.array(taps, np.float64) / sum(taps)
        M = cv2.getRotationMatrix2D((W / 2, H / 2), theta, 1.0)
        rot = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)
        # 行方向相关（沿旋转后的水平 = 沿原取向 θ）
        r = len(taps) // 2
        from numpy.lib.stride_tricks import sliding_window_view
        pad = np.pad(rot, ((0, 0), (r, r)), mode="edge")
        corr = sliding_window_view(pad, len(taps), axis=1) @ k
        # 旋转回原坐标（相关后宽度缩短，居中放置）
        resp = np.zeros_like(img)
        x0 = (W - corr.shape[1]) // 2
        resp[:, x0:x0 + corr.shape[1]] = corr
        Minv = cv2.getRotationMatrix2D((W / 2, H / 2), -theta, 1.0)
        resp = cv2.warpAffine(resp, Minv, (W, H), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
        upd = np.abs(resp) > best
        best = np.where(upd, np.abs(resp), best)
        best_ang = np.where(upd, theta, best_ang)
    return best, best_ang

def build_weights():
    """DLL 0x40130 起的 11 抽头金字塔核（峰值425那条）外积成 11x11。"""
    k425 = np.array([57, 118, 207, 308, 392, 425, 392, 308, 207, 118, 57], np.float64)
    k392 = np.array([53, 109, 191, 285, 362, 392, 362, 285, 191, 109, 53], np.float64)
    return np.outer(k425, k392) / 425.0

def load_pgm(p):
    d = p.read_bytes()
    pos, tok = 0, []
    # 头：4 个 token（P5 w h maxval），支持 '#' 注释行
    while len(tok) < 4:
        while pos < len(d) and d[pos:pos+1].isspace():
            pos += 1
        if pos < len(d) and d[pos:pos+1] == b"#":
            while pos < len(d) and d[pos:pos+1] != b"\n":
                pos += 1
            continue
        s = pos
        while pos < len(d) and not d[pos:pos+1].isspace():
            pos += 1
        tok.append(d[s:pos])
    if d[pos:pos + 2] == b"\r\n":
        pos += 2  # maxval 后的空白终止符，容忍 CRLF 头
    else:
        pos += 1
    if tok[0] != b"P5" or int(tok[3]) != 255:
        raise ValueError(f"{p}: 不是 8-bit PGM (P5/255)")
    w, h = int(tok[1]), int(tok[2])
    if w <= 0 or h <= 0:
        raise ValueError(f"{p}: 非法尺寸 {w}x{h}")
    raster = d[pos:pos + w * h]
    if len(raster) < w * h:
        raise ValueError(f"{p}: 像素数据不足（期望 {w*h}，实得 {len(raster)}）")
    return np.frombuffer(raster, np.uint8, w * h).reshape(h, w).astype(np.float64)

def preprocess(img):
    """平场归一化（减 15x15 局部均值，边缘 replicate）。"""
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.pad(img, 7, mode="edge")
    win = sliding_window_view(pad, (15, 15))
    flat = img - win.mean(axis=(2, 3))
    s = flat.std()
    return flat / (s + 1e-9)

def extract_features(img):
    """取向滤波器组版本：兴趣点取滤波响应极大值，方向取获胜取向。"""
    flat = preprocess(img)
    enhanced, orient_map = oriented_filter_bank(flat)

    # 兴趣点：增强响应 3x3 极大值 + 密度 NMS
    e = enhanced
    pts = []
    H, W = e.shape
    for y in range(6, H - 6):
        for x in range(6, W - 6):
            v = e[y, x]
            patch = e[y-1:y+2, x-1:x+2]
            if v < patch.max() or (v == patch.max() and patch.argmax() != 4):
                continue
            pts.append((x, y))
    pts.sort(key=lambda p: -e[p[1], p[0]])
    kept = []
    for x, y in pts:
        if all((x-kx)**2 + (y-ky)**2 >= 36 for kx, ky in kept):
            kept.append((x, y))
        if len(kept) >= 120:
            break

    # 梯度（用于描述子直方图）
    gy, gx = np.gradient(enhanced)
    global W11
    W11 = W11 if W11 is not None else build_weights()
    binw = 360.0 / NBINS
    feats = []
    for x, y in kept:
        ang = np.degrees(np.arctan2(gy[y-5:y+6, x-5:x+6],
                                    gx[y-5:y+6, x-5:x+6])) % 360
        mag = np.sqrt(gx[y-5:y+6, x-5:x+6]**2 + gy[y-5:y+6, x-5:x+6]**2)
        w = W11 * mag
        dom = orient_map[y, x]                 # 获胜滤波取向（法向）
        rel = ((ang - dom) / binw).astype(int) % NBINS
        # 顶档描述子: 4x4 区域 x 32 方向bin = 512bit（64 字节）
        vals = np.zeros(512)
        for dy in range(4):
            for dx in range(4):
                sub_w = w[2*dy+(dy>1):2*dy+5+(dy>1), 2*dx+(dx>1):2*dx+5+(dx>1)]
                sub_r = rel[2*dy+(dy>1):2*dy+5+(dy>1), 2*dx+(dx>1):2*dx+5+(dx>1)]
                for b in range(NBINS):
                    vals[dy*128 + dx*32 + b] = sub_w[sub_r == b].sum()
        bits = vals > vals.sum() / 512.0
        feats.append((x, y, dom, bits))
    return feats

def popcount_hamming(a, b):
    return np.count_nonzero(a != b)

def match_score(f1, f2):
    """Windows 风格评分：Σ(128−h) 簇内贡献 − 未解释特征惩罚(−h/2)。"""
    if len(f1) < MIN_MATCHED or len(f2) < MIN_MATCHED:
        return 0, 0
    nn = []
    for x1, y1, a1, d1 in f1:
        best, bj = 512, -1
        for j, (x2, y2, a2, d2) in enumerate(f2):
            h = popcount_hamming(d1, d2)
            if h < best:
                best, bj = h, j
        if bj < 0:
            continue  # 全部描述子等距（如全同）：无可信 NN
        nn.append(((x1, y1, a1), f2[bj], best))
    if len(nn) < MIN_MATCHED:
        return 0, 0

    from collections import Counter
    votes2 = Counter()
    for p, f2f, h in nn:
        votes2[((p[0] - f2f[0]) // 8, (p[1] - f2f[1]) // 8)] += 1
    (cbx, cby), _ = votes2.most_common(1)[0]
    cx, cy = cbx * 8 + 4, cby * 8 + 4
    inl = [(p, f2f, h) for p, f2f, h in nn
           if h <= HAMMING_BUDGET
           and abs((p[0] - f2f[0]) - cx) <= POS_TOL_PX
           and abs((p[1] - f2f[1]) - cy) <= POS_TOL_PX]
    if len(inl) < MIN_MATCHED:
        return 0, 0
    dangs = Counter()
    for p, f2f, h in inl:
        dangs[(p[2] - f2f[2]) % 360] += 1
    mode_ang = dangs.most_common(1)[0][0]
    good = [(p, f2f, h) for p, f2f, h in inl
            if min((p[2] - f2f[2] - mode_ang) % 360,
                   360 - (p[2] - f2f[2] - mode_ang) % 360) <= ANGLE_TOL_DEG]
    if len(good) < MIN_MATCHED:
        return 0, 0
    score = sum(128 - h for _, _, h in good)
    # 二次机会惩罚：NN 海明 > 256 的 probe 特征未被画廊解释
    for p, f2f, h in nn:
        if h > 256:
            score -= h // 2
    return len(good), score

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gallery_dir", type=pathlib.Path)
    ap.add_argument("probe_dir", type=pathlib.Path)
    ap.add_argument("--threshold", type=int, default=244,
                    help="单帧画廊分数阈值（实测：真min254/假max438→配合双帧一致；"
                         "注意与 C 引擎刻度不同，驱动阈值为 300）")
    ap.add_argument("--agree", type=int, default=150,
                    help="一致判定的单帧分数下限")
    args = ap.parse_args()

    gallery = [extract_features(load_pgm(p)) for p in sorted(args.gallery_dir.glob("gallery-*.pgm"))]
    gallery = [g for g in gallery if len(g) >= MIN_FEATURES]
    print(f"画廊: {len(gallery)} 帧有足够特征")

    verdict = "NO-MATCH"
    for p in sorted(args.probe_dir.glob("probe-*.pgm")):
        f = extract_features(load_pgm(p))
        scores = [match_score(f, g)[1] for g in gallery]
        best = max(scores) if scores else 0
        agree = sum(1 for s in scores if s >= args.agree)
        ok = best >= args.threshold and agree >= 2
        print(f"{p.name}: best={best} 一致帧={agree} {'✓' if ok else '✗'}")
        if ok:
            verdict = "MATCH"
    print(f"\n判定: {verdict}")

if __name__ == "__main__":
    main()
