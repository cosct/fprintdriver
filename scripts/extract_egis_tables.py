#!/usr/bin/env python3
"""从 EgisTouchFPEngine0575.dll 提取 Windows 匹配引擎的系数表。

Ghidra 反编译地址（image base 0x180000000）→ PE RVA → 文件偏移。
表（见 docs/comparison.md §7）：
  UNK_180043070  滤波器组 tap 指针/偏移表
  DAT_180041b50  每个滤波器的 tap 长度
  DAT_1800433c0  128 项 atan2 查找表
  DAT_1800431d0  11x11 描述子权重（121 项）
  DAT_180041b60  sin 表（360 项）
  DAT_180042100  cos 表（360 项）
用法：python3 scripts/extract_egis_tables.py <dll路径>
"""
import struct
import sys
from pathlib import Path

IMAGE_BASE = 0x180000000
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_dll_path(arg):
    """规范化路径并限制在项目目录内，拒绝 ../ 越界访问。"""
    p = (Path(arg) if arg else PROJECT_ROOT /
         "acerdrv" / "Fingerprint_EGISTEC_3.7.1.1_W10x64" / "x64" /
         "EgisTouchFPEngine0575.dll").resolve()
    if not p.is_relative_to(PROJECT_ROOT):
        raise SystemExit(f"拒绝项目外路径: {p}（本工具仅允许访问 {PROJECT_ROOT} 内的文件）")
    if not p.is_file():
        raise SystemExit(f"文件不存在: {p}")
    return p


def parse_pe(data):
    """返回 [(vaddr, file_off, size)] 节映射。"""
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
    return sections


def rva_to_off(sections, rva):
    for name, vaddr, vsize, rawptr, rawsize in sections:
        if vaddr <= rva < vaddr + max(vsize, rawsize):
            return rawptr + (rva - vaddr)
    raise ValueError(f"RVA {rva:#x} not in any section")


def read_at(data, sections, ghidra_addr, size):
    off = rva_to_off(sections, ghidra_addr - IMAGE_BASE)
    return data[off:off + size], off


def main():
    dll = resolve_dll_path(sys.argv[1] if len(sys.argv) > 1 else None)
    data = dll.read_bytes()
    sections = parse_pe(data)
    print(f"PE 节: {[(n, hex(v), hex(s)) for n, v, s, _, _ in sections]}")

    # 1) atan2 表 128 项（验证用：应为角度类数值）
    blob, _ = read_at(data, sections, 0x1800433c0, 128 * 4)
    vals = struct.unpack(f"<{len(blob)//4}i", blob)
    print(f"\natan2表[128]: 前8={vals[:8]}  后4={vals[-4:]}")

    # 2) sin/cos 表 360 项（定点，应在合理幅值内）
    for name, addr in (("sin", 0x180041b60), ("cos", 0x180042100)):
        blob, _ = read_at(data, sections, addr, 360 * 4)
        vals = struct.unpack(f"<{len(blob)//4}i", blob)
        print(f"{name}表[360]: 前6={vals[:6]} min={min(vals)} max={max(vals)}")

    # 3) tap 长度表（从 0x180041b50 起读 32 项）
    blob, _ = read_at(data, sections, 0x180041b50, 32 * 4)
    lens = struct.unpack(f"<{len(blob)//4}i", blob)
    print(f"\ntap长度表[前32]: {lens}")

    # 4) 滤波器指针表 0x180043070（先按 32bit 偏移读，再按 64bit 指针读对比）
    blob, _ = read_at(data, sections, 0x180043070, 16 * 4)
    dwords = struct.unpack(f"<{len(blob)//4}I", blob)
    print(f"滤波表@43070 按 u32: {[hex(x) for x in dwords[:8]]}")
    blob8, _ = read_at(data, sections, 0x180043070, 8 * 8)
    qwords = struct.unpack("<8Q", blob8)
    print(f"滤波表@43070 按 u64: {[hex(x) for x in qwords]}")

    # 5) 描述子权重 121 项
    blob, _ = read_at(data, sections, 0x1800431d0, 121 * 2)
    w16 = struct.unpack(f"<{len(blob)//2}h", blob)
    print(f"\n描述子权重[121]u16: 前12={w16[:12]} min={min(w16)} max={max(w16)}")
    blob, _ = read_at(data, sections, 0x1800431d0, 121 * 4)
    w32 = struct.unpack(f"<{len(blob)//4}i", blob)
    print(f"描述子权重[121]u32: 前6={w32[:6]}")


if __name__ == "__main__":
    main()
