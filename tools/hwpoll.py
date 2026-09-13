#!/usr/bin/env python3
"""直接轮询 EH575 的硬件手指状态命令（EGIS 60 01），观察 resp[5] 变化。
用法：python3 tools/hwpoll.py [秒数]   —— 期间按/抬手指
"""
import argparse
import sys
import time

import usb.core


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seconds", type=float, nargs="?", default=20.0,
                    help="轮询时长（秒，默认 20）")
    args = ap.parse_args()

    dev = usb.core.find(idVendor=0x1C7A, idProduct=0x0575)
    if dev is None:
        sys.exit("设备未找到")

    try:
        dev.detach_kernel_driver(0)
    except usb.core.USBError:
        pass
    try:
        dev.set_configuration()
    except usb.core.USBError as e:
        sys.exit(f"无法配置设备（被 fprintd 等占用？先停掉占用进程）: {e}")

    cfg = dev.get_active_configuration()
    intf = cfg[(0, 0)]

    t0 = time.time()
    last = None
    n = 0
    try:
        while time.time() - t0 < args.seconds:
            try:
                dev.write(0x01, bytes([0x45, 0x47, 0x49, 0x53, 0x60, 0x01]), 1000)
                resp = dev.read(0x82, 7, 1000)
                v = resp[5] if len(resp) > 5 else -1
                if v != last:
                    print(f"{time.time()-t0:6.1f}s  resp[5]={v:#04x}  "
                          f"{'手指!' if v > 3 else '无指'}")
                    last = v
                n += 1
            except usb.core.USBError as e:
                print(f"USB错误: {e}")
                time.sleep(0.5)
            time.sleep(0.02)
    finally:
        usb.util.dispose_resources(dev)
        try:
            dev.attach_kernel_driver(0)
        except usb.core.USBError:
            pass

    print(f"共 {n} 次轮询")


if __name__ == "__main__":
    main()
