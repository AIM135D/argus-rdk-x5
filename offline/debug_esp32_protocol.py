#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""协议 A 独立测试。运行前先停止 app.py，避免串口占用。"""

import argparse
import time
import serial


def read_all(ser, dur=0.45):
    end = time.time() + dur
    while time.time() < end:
        while ser.in_waiting:
            print("RX:", ser.readline().decode("utf-8", errors="ignore").strip())
        time.sleep(0.02)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=0.1)
    time.sleep(2.0)
    cmds = [
        "C",
        "A,1,1,120,75,0.920,1,3",
        "A,2,2,60,90,0.720,1,2",
        "A,3,0,90,90,0.300,1,1",
        "L,4",
        "C",
    ]
    for cmd in cmds:
        print("TX:", cmd)
        ser.write((cmd + "\n").encode("utf-8"))
        ser.flush()
        read_all(ser)
    ser.close()


if __name__ == "__main__":
    main()
