# monitor.py
# -*- coding: utf-8 -*-

import re
import subprocess
import time

import psutil

from state import state


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def read_temp_c(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return round(float(text) / 1000.0, 1)
    except Exception:
        return None


def parse_power_w(text):
    if not text:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*W", text, re.I)
    if m:
        try:
            return round(float(m.group(1)), 2)
        except Exception:
            return None
    return None


def parse_bpu_ratio(output):
    """
    适配你当前 hrut_somstatus 输出格式，例如：
    bpu status information---->
            min(M)   cur(M)   max(M)   ratio
     bpu0:  500      1000     1000     19
    """
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("bpu0:"):
            # 取最后一个数字作为 ratio
            nums = re.findall(r"\d+(?:\.\d+)?", line)
            if nums:
                try:
                    return round(float(nums[-1]), 1)
                except Exception:
                    return None
    return None


def get_x5_metrics():
    cpu_usage = None
    mem_usage = None
    cpu_temp = None
    bpu_temp = None
    bpu_usage = None
    power_w = None

    # CPU / Memory
    try:
        cpu_usage = round(psutil.cpu_percent(interval=None), 1)
    except Exception:
        pass

    try:
        mem = psutil.virtual_memory()
        mem_usage = round(mem.percent, 1)
    except Exception:
        pass

    # 温度
    bpu_temp = read_temp_c("/sys/class/hwmon/hwmon0/temp2_input")
    cpu_temp = read_temp_c("/sys/class/hwmon/hwmon0/temp3_input")

    # 解析 hrut_somstatus
    try:
        result = subprocess.run(
            ["hrut_somstatus"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=1.5
        )
        output = result.stdout or ""

        # 解析 BPU ratio
        bpu_usage = parse_bpu_ratio(output)

        # 尝试解析功耗（如果未来某个版本输出里有）
        for line in output.splitlines():
            low = line.lower()
            if ("power" in low or "pwr" in low) and "w" in low:
                value = parse_power_w(line)
                if value is not None:
                    power_w = value
                    break

    except Exception:
        pass

    return {
        "cpu_usage": cpu_usage,
        "mem_usage": mem_usage,
        "cpu_temp": cpu_temp,
        "bpu_temp": bpu_temp,
        "bpu_usage": bpu_usage,
        "power_w": power_w,
    }


def monitor_loop():
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass

    while state.running:
        try:
            metrics = get_x5_metrics()
            with state.lock:
                state.latest_info.update(metrics)
        except Exception as e:
            print("monitor_loop error:", e)

        time.sleep(1.0)
