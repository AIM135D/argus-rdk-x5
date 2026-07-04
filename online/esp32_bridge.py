# esp32_bridge.py
# -*- coding: utf-8 -*-
"""
RDK X5 -> ESP32 串口桥接。

协议：
    C                                      # 回中
    L,seq                                  # 目标丢失
    A,seq,zone_id,pan,tilt,score,light,beep # 推荐：直接发送舵机角度
    T,seq,zone_id,cx,cy,img_w,img_h,score,light,beep # 兼容：发送图像坐标

也支持旧协议：
    @T,seq,valid,xn,yn,danger,alarm
"""

import time

try:
    import serial
except Exception:
    serial = None


class ESP32Bridge:
    def __init__(
        self,
        port="/dev/ttyUSB0",
        baudrate=115200,
        protocol="A",
        timeout=0.02,
        write_timeout=0.05,
    ):
        self.port = port
        self.baudrate = int(baudrate)
        self.protocol = str(protocol or "A").upper()
        self.timeout = float(timeout)
        self.write_timeout = float(write_timeout)

        self.ser = None
        self.connected = False
        self.seq = 0

        self.last_cmd = ""
        self.last_ack = ""
        self.last_error = ""

    def connect(self):
        if serial is None:
            self.connected = False
            self.last_error = "pyserial not installed"
            return False

        try:
            if self.ser is not None and self.ser.is_open:
                self.connected = True
                return True
        except Exception:
            pass

        try:
            self.ser = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
                write_timeout=self.write_timeout,
            )

            # ESP32 打开串口通常会复位
            time.sleep(1.5)

            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except Exception:
                pass

            self.connected = True
            self.last_error = ""
            return True

        except Exception as e:
            self.ser = None
            self.connected = False
            self.last_error = str(e)
            return False

    def close(self):
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass

        self.ser = None
        self.connected = False

    def _next_seq(self):
        self.seq += 1
        if self.seq > 999999:
            self.seq = 1
        return self.seq

    def _read_ack(self):
        if self.ser is None:
            return ""

        lines = []
        try:
            start = time.time()
            while time.time() - start < 0.02:
                if self.ser.in_waiting <= 0:
                    time.sleep(0.002)
                    continue
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    lines.append(line)
        except Exception:
            pass

        if lines:
            self.last_ack = " | ".join(lines)

        return self.last_ack

    def send_raw(self, cmd):
        if not self.connect():
            return False

        if not cmd.endswith("\n"):
            cmd += "\n"

        try:
            self.ser.write(cmd.encode("utf-8"))
            self.ser.flush()

            self.last_cmd = cmd.strip()
            self.last_error = ""
            self.connected = True

            self._read_ack()
            return True

        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            self.close()
            return False

    def send_center(self):
        return self.send_raw("C")

    def send_lost(self):
        seq = self._next_seq()
        if self.protocol == "AT":
            return self.send_raw(f"@T,{seq},0,500,500,0,0")
        return self.send_raw(f"L,{seq}")

    def send_aim(self, zone_id, pan, tilt, score, beep, light=None):
        """推荐新协议：直接发送声光/指向模块舵机角度。"""
        seq = self._next_seq()

        try:
            zone_id = int(zone_id) if zone_id is not None else 0
        except Exception:
            zone_id = 0

        try:
            pan = int(max(0, min(180, round(float(pan)))))
            tilt = int(max(0, min(180, round(float(tilt)))))
            score = float(score or 0.0)
            beep = int(max(0, min(3, int(beep))))
            light = (
                1 if beep > 0 else 0
            ) if light is None else int(bool(light))
        except Exception:
            pan, tilt, score, beep, light = 90, 90, 0.0, 0, 0

        cmd = f"A,{seq},{zone_id},{pan},{tilt},{score:.3f},{light},{beep}"
        return self.send_raw(cmd)

    def send_target(
        self, zone_id, cx, cy, img_w, img_h, score, beep, light=None
    ):
        seq = self._next_seq()

        try:
            zone_id = int(zone_id) if zone_id is not None else 0
        except Exception:
            zone_id = 0

        try:
            img_w = int(max(1, round(float(img_w))))
            img_h = int(max(1, round(float(img_h))))
            cx = int(max(0, min(img_w - 1, round(float(cx)))))
            cy = int(max(0, min(img_h - 1, round(float(cy)))))
            score = float(score or 0.0)
            beep = int(max(0, min(3, int(beep))))
            light = (
                1 if beep > 0 else 0
            ) if light is None else int(bool(light))
        except Exception:
            img_w, img_h, cx, cy, score, beep, light = (
                640, 360, 320, 180, 0.0, 0, 0
            )

        if self.protocol == "AT":
            xn = int(round(cx / max(1, img_w - 1) * 1000.0))
            yn = int(round(cy / max(1, img_h - 1) * 1000.0))
            danger = 1 if beep > 0 else 0
            cmd = f"@T,{seq},1,{xn},{yn},{danger},{beep}"
        else:
            cmd = f"T,{seq},{zone_id},{cx},{cy},{img_w},{img_h},{score:.3f},{light},{beep}"

        return self.send_raw(cmd)

    def snapshot(self):
        return {
            "connected": bool(self.connected),
            "port": self.port,
            "protocol": self.protocol,
            "seq": int(self.seq),
            "last_cmd": self.last_cmd,
            "last_ack": self.last_ack,
            "last_error": self.last_error,
        }
