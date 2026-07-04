# llm_bridge.py
# -*- coding: utf-8 -*-

import copy
import queue
import threading
import time

from config import LLM_BRIDGE_ENABLED

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
except Exception:
    rclpy = None
    Node = None
    String = None


ALLOWED_EVENT_TYPES = {"auto_capture"}
EVENT_COOLDOWN_SECONDS = 20.0


class DisabledLLMBridge:
    """No-op bridge used unless the optional ROS integration is enabled."""

    def submit_event(self, log_id, event):
        try:
            from state import update_event_log

            update_event_log(
                log_id,
                {"ai_status": "disabled", "ai_explanation": ""},
            )
        except Exception:
            pass
        return False

    def stop(self):
        return None


def build_llm_prompt(event):
    event_type = str(event.get("type", "event")).strip().lower()
    zone_name = str(event.get("zone_name") or "unknown_zone").strip()
    risk_level = str(event.get("risk_level") or "high").strip().lower()
    message = str(event.get("message") or "").strip()

    danger_duration = event.get("danger_duration", None)
    if danger_duration is None:
        danger_duration_text = "none"
    else:
        try:
            danger_duration_text = f"{float(danger_duration):.1f}s"
        except Exception:
            danger_duration_text = str(danger_duration)

    missing_helmet_count = int(event.get("missing_helmet_count", 0) or 0)
    missing_vest_count = int(event.get("missing_vest_count", 0) or 0)
    violation_person_count = int(event.get("violation_person_count", 0) or 0)

    reason_parts = []
    if missing_helmet_count > 0:
        reason_parts.append("no helmet")
    if missing_vest_count > 0:
        reason_parts.append("no reflective vest")
    if violation_person_count > 0 and not reason_parts:
        reason_parts.append("ppe violation")
    if event_type == "auto_capture" and not reason_parts:
        reason_parts.append("danger lasted too long")
    if not reason_parts:
        reason_parts.append("danger event")

    reason_text = ", ".join(reason_parts)

    prompt = f"""
Generate ONE short Chinese sentence for an industrial safety event.

Rules:
- Output Chinese only
- One sentence only
- Prefer <= 24 Chinese characters
- No bullet points
- No quotes
- Do not mention AI

Event: {event_type}
Zone: {zone_name}
Risk: {risk_level}
Duration: {danger_duration_text}
Reason: {reason_text}
Log: {message}

Output one final Chinese sentence only.
""".strip()

    return prompt


def _compact_result(text):
    if not text:
        return "event triggered."

    text = " ".join(str(text).split())

    for sep in ["。", "！", "？", ".", "!", "?", "\n"]:
        if sep in text:
            left = text.split(sep)[0].strip()
            if left:
                if sep in ["。", "！", "？"]:
                    text = left + sep
                else:
                    text = left
            break

    if len(text) > 36:
        text = text[:36].rstrip("，,;；、 ") + "。"

    return text or "event triggered."


class LocalLLMBridge:
    def __init__(
        self,
        prompt_topic="/prompt_text",
        response_topic="/tts_text",
        default_timeout=6.0,
        queue_size=1,
    ):
        self.prompt_topic = prompt_topic
        self.response_topic = response_topic
        self.default_timeout = float(default_timeout)

        self._started = False
        self._running = False

        self._node = None
        self._publisher = None
        self._subscription = None

        self._spin_thread = None
        self._worker_thread = None

        self._call_lock = threading.Lock()
        self._response_cond = threading.Condition()
        self._waiting_response = False
        self._response_done = False
        self._response_chunks = []

        self._task_queue = queue.Queue(maxsize=queue_size)

        self._last_submit_time = {}
        self._meta_lock = threading.Lock()

    def start(self):
        if self._started:
            return
        if rclpy is None or Node is None or String is None:
            raise RuntimeError(
                "ROS 2 Python packages are unavailable; keep llm_bridge_enabled=false "
                "or source the RDK/TROS environment."
            )

        if not rclpy.ok():
            rclpy.init(args=None)

        self._node = Node("danger_event_llm_bridge")
        self._publisher = self._node.create_publisher(String, self.prompt_topic, 10)
        self._subscription = self._node.create_subscription(
            String, self.response_topic, self._on_response, 10
        )

        self._running = True
        self._spin_thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)

        self._spin_thread.start()
        self._worker_thread.start()

        self._started = True
        print("[LLM] bridge started")

    def stop(self):
        self._running = False

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)

        if self._spin_thread and self._spin_thread.is_alive():
            self._spin_thread.join(timeout=1.0)

        if self._node is not None:
            try:
                self._node.destroy_node()
            except Exception:
                pass
            self._node = None

        if rclpy.ok():
            try:
                rclpy.shutdown()
            except Exception:
                pass

        self._started = False
        print("[LLM] bridge stopped")

    def _spin_loop(self):
        while self._running and self._node is not None:
            try:
                rclpy.spin_once(self._node, timeout_sec=0.1)
            except Exception:
                time.sleep(0.05)

    def _on_response(self, msg):
        text = (msg.data or "").strip()
        if not text:
            return

        with self._response_cond:
            if not self._waiting_response:
                return

            if text == "end":
                self._response_done = True
                self._response_cond.notify_all()
                return

            self._response_chunks.append(text)
            self._response_cond.notify_all()

    def explain_event(self, event, timeout=None):
        self.start()

        prompt = build_llm_prompt(event)
        timeout = float(timeout or self.default_timeout)

        with self._call_lock:
            with self._response_cond:
                self._response_chunks = []
                self._response_done = False
                self._waiting_response = True

            ros_msg = String()
            ros_msg.data = prompt
            self._publisher.publish(ros_msg)

            deadline = time.time() + timeout

            with self._response_cond:
                while (not self._response_done) and (time.time() < deadline):
                    remain = deadline - time.time()
                    self._response_cond.wait(timeout=max(0.05, remain))

                result = "".join(self._response_chunks).strip()
                self._waiting_response = False

            if not result and not self._response_done:
                raise TimeoutError(
                    f"timeout waiting for {self.response_topic} ({timeout:.1f}s)"
                )

            return _compact_result(result)

    def _event_key(self, event):
        event_type = str(event.get("type", "event")).strip().lower()
        zone_id = str(event.get("zone_id", "0")).strip()
        return f"{event_type}:{zone_id}"

    def submit_event(self, log_id, event):
        from state import update_event_log

        payload = copy.deepcopy(event or {})
        payload.setdefault("type", "event")

        event_type = str(payload.get("type", "event")).strip().lower()

        if event_type not in ALLOWED_EVENT_TYPES:
            update_event_log(
                log_id,
                {
                    "ai_status": "skipped",
                    "ai_explanation": "",
                },
            )
            return False

        key = self._event_key(payload)
        now = time.time()

        with self._meta_lock:
            last_ts = self._last_submit_time.get(key, 0.0)
            if now - last_ts < EVENT_COOLDOWN_SECONDS:
                update_event_log(
                    log_id,
                    {
                        "ai_status": "skipped_cooldown",
                        "ai_explanation": "",
                    },
                )
                return False
            self._last_submit_time[key] = now

        try:
            self.start()
        except Exception as e:
            update_event_log(
                log_id,
                {
                    "ai_status": "error",
                    "ai_explanation": f"LLM bridge start failed: {e}",
                },
            )
            return False

        update_event_log(log_id, {"ai_status": "queued"})

        try:
            self._task_queue.put_nowait((int(log_id), payload))
            return True
        except queue.Full:
            update_event_log(
                log_id,
                {
                    "ai_status": "skipped_busy",
                    "ai_explanation": "",
                },
            )
            return False

    def _worker_loop(self):
        from state import update_event_log

        while self._running:
            try:
                log_id, event = self._task_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                update_event_log(log_id, {"ai_status": "generating"})
                text = self.explain_event(event, timeout=self.default_timeout)
                update_event_log(
                    log_id,
                    {
                        "ai_status": "done",
                        "ai_explanation": text,
                    },
                )
            except Exception as e:
                update_event_log(
                    log_id,
                    {
                        "ai_status": "error",
                        "ai_explanation": f"LLM explain failed: {e}",
                    },
                )
            finally:
                self._task_queue.task_done()


_bridge_singleton = None
_bridge_lock = threading.Lock()


def get_llm_bridge():
    global _bridge_singleton
    with _bridge_lock:
        if _bridge_singleton is None:
            _bridge_singleton = (
                LocalLLMBridge()
                if LLM_BRIDGE_ENABLED and rclpy is not None
                else DisabledLLMBridge()
            )
        return _bridge_singleton
