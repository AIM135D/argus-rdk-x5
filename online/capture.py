# capture.py
# -*- coding: utf-8 -*-

import time

import cv2

from config import CAMERA_INDEX, STREAM_HEIGHT, STREAM_WIDTH
from state import state


def capture_loop():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)

    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    if not cap.isOpened():
        print("❌ 摄像头打开失败")
        return

    print("✅ 摄像头已打开")

    while state.running:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.002)
            continue

        with state.frame_lock:
            state.latest_frame = frame
            state.latest_frame_seq += 1

    cap.release()
    print("摄像头已释放")
