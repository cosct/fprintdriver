#!/usr/bin/env python3
"""从 EgisTouchFPEngine0575.dll 提取 Windows 匹配引擎的系数表。

地址是定案 RVA（对默认 Acer DLL v3.7.1.1 按签名扫描定位，
见 docs/windows-engine-tables.md §2；Animeshz 反编译版的地址
不可复用）：
  0x3eac0  sin 表（360 × int32，Q16 定点）
  0x3f060  cos 表（360 × int32，Q16 定点，与 sin 相距恰 1440 字节）
  0x3ffd0  11 取向脊线模板核（i32 紧凑排列，长度 5,5,5,7,7,7,9,9,9,11,11，
           每核对称、归一化和 32768）
  0x40130  描述子权重核（金字塔，121 × i32 ↔ 11×11）
  0x40320  atan2 LUT（u16 严格单调）
  0x47794  传感器配置表（含 88/52/103）

用法：python3 scripts/extract_egis_tables.py [dll路径]
"""
import math
import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TABLES = {
    "sin":    0x3eac0,
    "cos":    0x3f060,
    "fir11":  0x3ffd0,
    "w121":   0x40130,
    "atan2":  0x40320,
    "sensor": 0x47794,
}

FIR_LENS = [5, 5, 5, 7, 7, 7, 9, 9, 9, 11, 11]


def resolve_dll_path(arg):
    """规范化路径并限制在项目目录内，拒绝 ../ 越界访问。"""
    # 注意：驱动包解压后文件名带字面反斜杠（"x64\EgisTouchFPEngine0575.dll"
    # 是单个文件名，不是路径分隔）
    p = (Path(arg) if arg else PROJECT_ROOT /
         "acerdrv" / "Fingerprint_EGISTEC_3.7.1.1_W10x64" / "x64" /
         "x64\\EgisTouchFPEngine0575.dll").resolve()
    if not p.is_relative_to(PROJECT_ROOT):
        raise SystemExit(f"拒绝项目外路径: {p}（本工具仅允许访问 {PROJECT_ROOT} 内的文件）")
    if not p.is_file():
        raise SystemExit(f"文件不存在: {p}")
    return p


def parse_pe(data):
    """返回 [(name, vaddr, vsize, rawptr, rawsize)] 节映射。"""
    try:
        if data[:2] != b"MZ":
            raise ValueError("not a PE")
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
            raise ValueError("bad PE sig")
        machine, nsec = struct.unpack_from("<HH", data, e_lfanew + 4)[0:2]
        opt_size = struct.unpack_from("<H", data, e_lfanew + 20)[0]
        sec_off = e_lfanew + 24 + opt_size
        sections = []
        for i in range(nsec):
            off = sec_off + i * 40
            name = data[off:off + 8].rstrip(b"\x00").decode(errors="replace")
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, off + 8)
            sections.append((name, vaddr, vsize, rawptr, rawsize))
    except struct.error as e:
        raise ValueError(f"malformed PE: {e}") from e
    return sections


def rva_to_off(sections, rva):
    for name, vaddr, vsize, rawptr, rawsize in sections:
        if vaddr <= rva < vaddr + max(vsize, rawsize):
            return rawptr + (rva - vaddr)
    raise ValueError(f"RVA {rva:#x} not in any section")


def read_rva(data, sections, rva, size):
    off = rva_to_off(sections, rva)
    blob = data[off:off + size]
    if len(blob) < size:
        raise ValueError(f"RVA {rva:#x}: 文件内数据不足（期望 {size}，实得 {len(blob)}）")
    return blob


def main():
    dll = resolve_dll_path(sys.argv[1] if len(sys.argv) > 1 else None)
    data = dll.read_bytes()
    sections = parse_pe(data)
    print(f"PE 节: {[(n, hex(v), hex(s)) for n, v, s, _, _ in sections]}")

    # 1) sin/cos 表 360 × i32 Q16：逐点对照 sin(i°)×65536（文档容差 8）
    for name in ("sin", "cos"):
        blob = read_rva(data, sections, TABLES[name], 360 * 4)
        vals = struct.unpack("<360i", blob)
        trig = math.sin if name == "sin" else math.cos
        worst = max(abs(vals[i] - round(trig(math.radians(i)) * 65536))
                    for i in range(360))
        ok = "✓" if worst <= 8 else "✗ 不符"
        print(f"\n{name}表[360]@{TABLES[name]:#x}: 前6={vals[:6]} "
              f"min={min(vals)} max={max(vals)} 与Q16三角值最大偏差={worst} {ok}")

    # 2) 11 取向脊线模板核：i32 紧凑排列，长度 5,5,5,7,7,7,9,9,9,11,11；
    #    每核应对称且归一化和为 32768
    blob = read_rva(data, sections, TABLES["fir11"], sum(FIR_LENS) * 4)
    print(f"\n11取向核@{TABLES['fir11']:#x}（紧凑 i32，和应=32768、应左右对称）:")
    pos = 0
    for o, ln in enumerate(FIR_LENS):
        row = struct.unpack_from(f"<{ln}i", blob, pos)
        pos += ln * 4
        sym = all(abs(row[i] - row[ln - 1 - i]) <= 2 for i in range(ln // 2))  # DLL 原表有 ±2 舍入
        ok = sum(row) == 32768 and sym
        print(f"  取向{o:2d}[{ln:2d}抽头]: 和={sum(row):6d} 对称={'✓' if sym else '✗'} "
              f"{'✓' if ok else '✗ 不符'} {list(row)}")

    # 3) 描述子权重核 121 × i32（11×11 金字塔，峰值 425）
    blob = read_rva(data, sections, TABLES["w121"], 121 * 4)
    w32 = struct.unpack("<121i", blob)
    print(f"\n描述子权重[121]@{TABLES['w121']:#x} i32: "
          f"前12={w32[:12]} min={min(w32)} max={max(w32)}")

    # 4) atan2 LUT u16：应严格单调
    blob = read_rva(data, sections, TABLES["atan2"], 128 * 2)
    lut = struct.unpack("<128H", blob)
    mono = all(lut[i] < lut[i + 1] for i in range(len(lut) - 1))
    print(f"\natan2 LUT[128]@{TABLES['atan2']:#x}: 范围 {lut[0]}→{lut[-1]} "
          f"严格单调={'✓' if mono else '✗'}")

    # 5) 传感器配置表：应含 88/52/103（归一化高/传感器高/宽）
    blob = read_rva(data, sections, TABLES["sensor"], 16 * 4)
    cfg = struct.unpack("<16i", blob)
    hits = sorted(set(cfg) & {88, 52, 103})
    print(f"\n传感器配置[16]@{TABLES['sensor']:#x}: {cfg}  命中={hits}")


if __name__ == "__main__":
    main()
