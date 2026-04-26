# -*- coding: utf-8 -*-
"""
Smart Cane Clip-On  |  Live Dashboard
Reads ESP32 serial data, shows sensor readings + YOLO detections.
Run: streamlit run Project_Dashboard.py
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import serial
    from serial.tools import list_ports
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def mm_to_readable(mm: int) -> str:
    if mm >= 1000:
        return f"{mm/1000:.2f} m"
    return f"{mm} mm"

def zone_label(mm: int) -> str:
    if mm < 300:   return "CRITICAL"
    if mm < 800:   return "WARNING"
    if mm < 1500:  return "CAUTION"
    return "CLEAR"

def lux_label(val: int) -> str:
    if val < 200: return "Very Dark"
    if val < 500: return "Dim"
    if val < 800: return "Moderate"
    return "Bright"

def parse_vision_line(raw: str) -> list[tuple[str, float]]:
    results = []
    for token in raw.split(","):
        token = token.strip()
        if ":" in token:
            parts = token.split(":")
            label = parts[0].strip()
            try:
                conf = float(parts[1].strip())
                results.append((label, conf))
            except (ValueError, IndexError):
                pass
    return results

def read_latest_vision(file: Path) -> str:
    if not file.exists():
        return ""
    try:
        with file.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 2048))
            tail = f.read().decode(errors="ignore").splitlines()
        for line in reversed(tail):
            if line.startswith("VISION|"):
                return line[len("VISION|"):]
    except Exception:
        pass
    return ""

# ---------------------------------------------------------------------------
#  Data model
# ---------------------------------------------------------------------------

@dataclass
class Packet:
    dist_fwd: int
    dist_drop: int
    fall_flag: int
    light_val: int

    @classmethod
    def parse(cls, line: str) -> "Packet | None":
        raw = line.strip()
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) == 4:
            try:
                return cls(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                pass
        dist_match = re.search(r"Dist[:\s]*([0-9]+)", raw, re.IGNORECASE)
        ldr_match  = re.search(r"LDR[:\s]*([0-9]+)", raw, re.IGNORECASE)
        fall_match = re.search(r"\bFALL\b", raw, re.IGNORECASE)
        if dist_match and ldr_match:
            dist = int(dist_match.group(1))
            ldr  = int(ldr_match.group(1))
            fall = 1 if fall_match else 0
            return cls(dist, dist, fall, ldr)
        nums = re.findall(r"([0-9]+)", raw)
        if len(nums) >= 2:
            try:
                return cls(int(nums[0]), int(nums[0]), 0, int(nums[1]))
            except ValueError:
                pass
        return None

# ---------------------------------------------------------------------------
#  Sources
# ---------------------------------------------------------------------------

class SerialSource:
    def __init__(self, port: str, baud: int = 115200):
        # timeout=1.5s -- firmware buzzer delay() can hold up packets ~400ms
        self.ser = serial.Serial(port, baud, timeout=1.5)
        self.last_raw = ""

    def read(self) -> "Packet | None":
        try:
            line = self.ser.readline().decode(errors="ignore")
            stripped = line.strip()
            if stripped:
                pkt = Packet.parse(stripped)
                self.last_raw = stripped if pkt else f"[PARSE FAIL] {stripped}"
                return pkt
            return None
        except Exception as exc:
            self.last_raw = f"[READ ERROR] {exc}"
            return None

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


class MockSource:
    def __init__(self):
        self._t = 0

    def read(self) -> Packet:
        self._t += 1
        fwd   = max(50, int(400 + 300 * random.random() - (self._t % 30) * 5))
        drop  = int(180 + random.randint(-40, 40))
        fall  = 1 if random.random() < 0.01 else 0
        light = int(500 + 200 * random.random())
        time.sleep(0.1)
        return Packet(fwd, drop, fall, light)

    def close(self):
        pass

# ---------------------------------------------------------------------------
#  Page setup
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Smart Cane Dashboard", layout="wide", page_icon="🦯")

st.title("🦯 Smart Cane Clip-On")
st.caption("Real-time obstacle detection & fall monitoring dashboard")
conn_status_ph = st.empty()
st.divider()

# ---------------------------------------------------------------------------
#  Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Configuration")

    detected_ports = [p.device for p in list_ports.comports()] if HAS_SERIAL else []
    auto_mock = not bool(detected_ports)

    if "mock_mode_set" not in st.session_state:
        st.session_state["mock_mode_set"] = True
        st.session_state["mock_mode_val"] = auto_mock

    mock_mode = st.toggle(
        "Mock Mode (no hardware)",
        value=st.session_state["mock_mode_val"],
        key="mock_mode_toggle",
    )
    st.session_state["mock_mode_val"] = mock_mode

    start = st.toggle("Start stream", value=True, key="start_stream")

    port = None
    baud = 115200
    if not mock_mode:
        if not HAS_SERIAL:
            st.error("pyserial not installed. Run: pip install pyserial")
        else:
            port = st.selectbox("Serial Port", detected_ports or ["(none detected)"])
        baud = st.number_input("Baud Rate", value=115200, step=9600)

    st.divider()
    st.subheader("Vision Module")
    ip_webcam_url = st.text_input("IP Webcam URL", value="http://192.168.1.100:8080/video")
    vision_model  = st.selectbox("YOLO Model", ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt"])
    vision_conf   = st.slider("Confidence Threshold", 0.1, 0.9, 0.45, 0.05)

    if "vision_process" not in st.session_state:
        st.session_state.vision_process = None

    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("Start Vision", type="primary", use_container_width=True):
            if st.session_state.vision_process is None:
                try:
                    vision_script = Path(__file__).resolve().parent / "Universal_Vision.py"
                    log_path      = Path(__file__).resolve().parent / "vision_process.log"
                    log_handle    = open(log_path, "a", buffering=1)
                    url = ip_webcam_url.strip() or "0"
                    cmd = [sys.executable, str(vision_script),
                           "--src", url, "--model", vision_model,
                           "--conf", str(vision_conf)]
                    st.session_state.vision_process = subprocess.Popen(
                        cmd,
                        cwd=str(Path(__file__).resolve().parent),
                        stdout=log_handle, stderr=log_handle,
                    )
                    st.session_state.vision_log_path = str(log_path)
                    st.success("Vision started")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to start vision: {e}")
            else:
                st.warning("Already running")
    with col_stop:
        if st.button("Stop Vision", use_container_width=True):
            if st.session_state.vision_process is not None:
                try:
                    st.session_state.vision_process.terminate()
                    st.session_state.vision_process.wait(timeout=5)
                    st.session_state.vision_process = None
                    st.success("Stopped")
                    st.rerun()
                except Exception as e:
                    st.error(f"Stop failed: {e}")
            else:
                st.info("Not running")

    vis_running = st.session_state.vision_process is not None
    st.write("Vision:", "🟢 Active" if vis_running else "🔴 Offline")

    st.divider()
    st.subheader("Display")
    vision_log = st.text_input("Vision log path", value="vision.log")
    window     = st.slider("History window (samples)", 50, 500, 150)

    st.divider()
    st.subheader("Alert Thresholds")
    thr_fwd    = st.slider("Forward obstacle — warn below (mm)", 100, 1500, 300, 50)
    thr_drop   = st.slider("Drop / ledge — warn below (mm)", 100, 800, 300, 50)
    thr_dark   = st.slider("Light: very dark below (raw)", 50, 600, 200, 25)
    thr_dim    = st.slider("Light: dim below (raw)", 100, 800, 500, 25)
    alert_cool = st.slider("Alert cooldown (s)", 1, 30, 5, 1)

    st.divider()
    with st.expander("Raw Serial Monitor"):
        if "serial_raw" not in st.session_state:
            st.session_state.serial_raw = []
        raw_lines = st.session_state.get("serial_raw", [])
        if raw_lines:
            st.code("\n".join(raw_lines[-15:]))
        else:
            st.caption("No data yet. Make sure Mock Mode is OFF and correct COM port is selected.")
        if st.button("Clear log"):
            st.session_state.serial_raw = []

# ---------------------------------------------------------------------------
#  Status banner
# ---------------------------------------------------------------------------

if mock_mode:
    st.info("MOCK MODE -- simulated data only. Turn off Mock Mode in the sidebar for real sensor data.")
else:
    st.success(f"LIVE -- Reading from {port} @ {baud} baud")

# ---------------------------------------------------------------------------
#  Session state
# ---------------------------------------------------------------------------

if "hist" not in st.session_state:
    st.session_state.hist = deque(maxlen=500)
if "serial_raw" not in st.session_state:
    st.session_state.serial_raw = []
if "alert_times" not in st.session_state:
    st.session_state.alert_times = {}
if "alert_log" not in st.session_state:
    st.session_state.alert_log = []
if "vision_last_seen" not in st.session_state:
    st.session_state.vision_last_seen = 0.0

# ---------------------------------------------------------------------------
#  Connection status (drawn once before loop, updated inside loop)
# ---------------------------------------------------------------------------

def _render_conn_status(serial_ok: bool, serial_label: str,
                        vision_ok: bool, vision_label: str) -> None:
    s_dot = "🟢" if serial_ok else "🔴"
    v_dot = "🟢" if vision_ok else "🔴"
    conn_status_ph.markdown(
        f"{s_dot} **ESP32 Serial** &nbsp; {serial_label} &emsp;&emsp;"
        f"{v_dot} **Vision Module** &nbsp; {vision_label}",
        unsafe_allow_html=True,
    )

# Initial static render (before stream starts)
_serial_init_label = "Mock (simulated)" if mock_mode else (f"{port} @ {baud}" if port else "No port selected")
_vision_init_ok    = st.session_state.vision_process is not None
_render_conn_status(
    serial_ok=mock_mode or bool(st.session_state.get("serial_src")),
    serial_label=_serial_init_label,
    vision_ok=_vision_init_ok,
    vision_label="Active" if _vision_init_ok else "Offline",
)

# ---------------------------------------------------------------------------
#  Open source (cached so the port stays open across reruns)
# ---------------------------------------------------------------------------

src = None
if start:
    if mock_mode:
        src = MockSource()
    elif HAS_SERIAL and port and port != "(none detected)":
        cached    = st.session_state.get("serial_src")
        cached_ok = (
            cached is not None
            and getattr(cached, "_port", None) == port
            and getattr(getattr(cached, "ser", None), "is_open", False)
        )
        if cached_ok:
            src = cached
        else:
            if cached is not None:
                try:
                    cached.close()
                except Exception:
                    pass
            st.session_state.pop("serial_src", None)
            try:
                new_src = SerialSource(port, int(baud))
                new_src._port = port
                st.session_state["serial_src"] = new_src
                src = new_src
            except PermissionError:
                st.error(
                    f"Access denied on {port}. Another program is using this port.\n\n"
                    "Fix: Close Arduino IDE Serial Monitor, then refresh this page."
                )
            except Exception as e:
                st.error(f"Could not open {port}: {e}")

# ---------------------------------------------------------------------------
#  Layout placeholders
# ---------------------------------------------------------------------------

fall_ph = st.empty()

st.subheader("Sensor Readings")
c1, c2, c3, c4 = st.columns(4)
card_fwd  = c1.empty()
card_drop = c2.empty()
card_fall = c3.empty()
card_lux  = c4.empty()

st.divider()

det_col, prox_col = st.columns([3, 2])
with det_col:
    st.subheader("Object Detection")
    detection_ph = st.empty()
with prox_col:
    st.subheader("Proximity")
    proximity_ph = st.empty()

st.divider()
st.subheader("Sensor History")
ch1, ch2, ch3 = st.columns(3)
with ch1:
    st.caption("Forward Distance (mm)")
    chart_fwd  = st.empty()
with ch2:
    st.caption("Drop Distance (mm)")
    chart_drop = st.empty()
with ch3:
    st.caption("Ambient Light")
    chart_lux  = st.empty()

st.divider()
st.subheader("Alert Log")
alert_log_ph = st.empty()

# ---------------------------------------------------------------------------
#  Main loop
# ---------------------------------------------------------------------------

if src is not None:
    st.session_state.hist = deque(list(st.session_state.hist)[-window:], maxlen=500)

    for _ in range(5000):
        pkt = src.read()

        if hasattr(src, "last_raw") and src.last_raw:
            st.session_state.serial_raw.append(src.last_raw)
            st.session_state.serial_raw = st.session_state.serial_raw[-50:]

        if pkt is None:
            time.sleep(0.05)
            continue

        st.session_state.hist.append({
            "t":    time.time(),
            "fwd":  pkt.dist_fwd,
            "drop": pkt.dist_drop,
            "fall": pkt.fall_flag,
            "lux":  pkt.light_val,
        })
        df = pd.DataFrame(list(st.session_state.hist)[-window:])

        # ---------------------------------------------------------------
        #  Threshold alerts (toast popups + log)
        # ---------------------------------------------------------------
        _now = time.time()

        def _alert(key: str, msg: str, icon: str, cool: float = float(alert_cool)) -> None:
            last = st.session_state.alert_times.get(key, 0.0)
            if _now - last >= cool:
                st.toast(msg, icon=icon)
                st.session_state.alert_times[key] = _now
                st.session_state.alert_log.insert(
                    0, {"Time": time.strftime("%H:%M:%S"), "Alert": f"{icon} {msg}"}
                )
                st.session_state.alert_log = st.session_state.alert_log[:50]

        if pkt.fall_flag:
            _alert("fall", "FALL DETECTED — cane user may need help!", "🚨", cool=3)
        if pkt.dist_fwd < thr_fwd:
            _alert("fwd", f"Obstacle very close: {pkt.dist_fwd} mm ahead", "⚠️")
        if pkt.dist_drop < thr_drop:
            _alert("drop", f"Drop / ledge: {pkt.dist_drop} mm", "⚠️")
        if pkt.light_val < thr_dark:
            _alert("dark", f"Very dark environment (light={pkt.light_val})", "🌑")
        elif pkt.light_val < thr_dim:
            _alert("dim", f"Dim lighting (light={pkt.light_val})", "🌙")

        # Fall banner
        if pkt.fall_flag:
            fall_ph.error("🚨 FALL DETECTED — ALERT TRIGGERED")
        else:
            fall_ph.success("No fall detected — IMU stable")

        # Sensor cards
        card_fwd.metric(
            label="Front Obstacle",
            value=mm_to_readable(pkt.dist_fwd),
            delta=zone_label(pkt.dist_fwd),
        )
        card_drop.metric(
            label="Drop / Ledge",
            value=mm_to_readable(pkt.dist_drop),
            delta=zone_label(pkt.dist_drop),
        )
        card_fall.metric(
            label="Fall Status",
            value="FALL!" if pkt.fall_flag else "Stable",
        )
        card_lux.metric(
            label="Ambient Light",
            value=lux_label(pkt.light_val),
            delta=str(pkt.light_val),
        )

        # Vision detections
        vision_raw = read_latest_vision(Path(vision_log))
        detections = parse_vision_line(vision_raw) if vision_raw else []

        # Update vision_last_seen timestamp
        if vision_raw:
            st.session_state.vision_last_seen = time.time()

        # ---------------------------------------------------------------
        #  Connection status update
        # ---------------------------------------------------------------
        _vis_process_alive = (
            st.session_state.vision_process is not None
            and st.session_state.vision_process.poll() is None
        )
        _secs_ago = int(time.time() - st.session_state.vision_last_seen)
        if not _vis_process_alive:
            _vis_label = "Offline"
        elif st.session_state.vision_last_seen == 0.0:
            _vis_label = "Running — no data yet"
        elif _secs_ago < 5:
            _vis_label = f"Active ({_secs_ago}s ago)"
        else:
            _vis_label = f"Stale ({_secs_ago}s ago)"
        _vis_ok = _vis_process_alive and st.session_state.vision_last_seen > 0 and _secs_ago < 5

        _serial_ok    = mock_mode or (
            hasattr(src, "ser") and getattr(src.ser, "is_open", False)
        )
        _serial_label = "Mock (simulated)" if mock_mode else f"{port} @ {baud}"
        _render_conn_status(_serial_ok, _serial_label, _vis_ok, _vis_label)

        # Filter detections by confidence threshold (>50%)
        valid_detections = [(lbl, conf) for lbl, conf in detections if conf * 100 > 50]

        if valid_detections:
            det_text = "\n\n".join(
                f"**{lbl.title()}** -- {int(conf * 100)}% confidence"
                for lbl, conf in valid_detections[:6]
            )
            detection_ph.markdown(det_text)
        else:
            detection_ph.info("NO OBJECT DETECTED")

        # Proximity
        prox_pct = max(0, min(100, int((1 - pkt.dist_fwd / 2000) * 100)))
        zone     = zone_label(pkt.dist_fwd)
        with proximity_ph.container():
            st.metric(label=f"Nearest obstacle -- {zone}", value=mm_to_readable(pkt.dist_fwd))
            st.progress(prox_pct)

        # Charts
        if not df.empty:
            chart_fwd.line_chart(df.set_index("t")[["fwd"]],   height=160)
            chart_drop.line_chart(df.set_index("t")[["drop"]], height=160)
            chart_lux.line_chart(df.set_index("t")[["lux"]],   height=160)

        # Alert log
        if st.session_state.alert_log:
            alert_log_ph.dataframe(
                pd.DataFrame(st.session_state.alert_log),
                use_container_width=True,
                hide_index=True,
            )
        else:
            alert_log_ph.caption("No alerts yet.")

    # Keep serial port alive between reruns -- only close mock source
    if mock_mode:
        src.close()
    st.rerun()

else:
    cached = st.session_state.pop("serial_src", None)
    if cached is not None:
        try:
            cached.close()
        except Exception:
            pass
    st.warning("Stream paused. Toggle 'Start stream' in the sidebar to resume.")

# Cleanup vision on exit
import atexit

@atexit.register
def _cleanup_vision():
    proc = st.session_state.get("vision_process")
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            pass