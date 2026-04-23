"""
============================================================================
 SMART CANE CLIP-ON  |  MODULE D: MASTER DASHBOARD ("Brain")
============================================================================
 Tech      : Python 3.9+, Streamlit
 Role      : Read USB-Serial data from the ESP32, overlay YOLO text labels
             from Module C, plot live graphs. Has a "Mock Mode" toggle so
             the team can develop UI without the hardware plugged in.

 IP WEBCAM INTEGRATION:
     1. Install "IP Webcam" app on Android phone
     2. Start the app and note the IP address (e.g., 192.168.1.5:8080)
     3. Enter URL in dashboard: http://192.168.1.5:8080/video
     4. Click "▶ Start Vision" to launch object detection

 PACKET FORMAT (from ESP32 over Serial @ 115200 baud):
     "dist_fwd,dist_drop,fall_flag,light_val"   e.g. "045,180,0,550"

 INSTALL:
     pip install streamlit pyserial pandas

 RUN:
     streamlit run Project_Dashboard.py
============================================================================
"""

from __future__ import annotations

import random
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
        parts = line.strip().split(",")
        if len(parts) != 4:
            return None
        try:
            return cls(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
        except ValueError:
            return None


# ---------------------------------------------------------------------------
#  Sources: Serial vs Mock
# ---------------------------------------------------------------------------
class SerialSource:
    def __init__(self, port: str, baud: int = 115200):
        self.ser = serial.Serial(port, baud, timeout=0.2)

    def read(self) -> Packet | None:
        try:
            line = self.ser.readline().decode(errors="ignore")
            return Packet.parse(line) if line else None
        except Exception:
            return None

    def close(self):
        try: self.ser.close()
        except Exception: pass


class MockSource:
    """Random but realistic fake data. Occasionally fires a fall_flag."""
    def __init__(self):
        self._t = 0

    def read(self) -> Packet:
        self._t += 1
        fwd  = max(50, int(400 + 300 * random.random() - (self._t % 30) * 5))
        drop = int(180 + random.randint(-40, 40))
        fall = 1 if random.random() < 0.01 else 0
        light = int(500 + 200 * random.random())
        time.sleep(0.1)
        return Packet(fwd, drop, fall, light)

    def close(self):
        pass


# ---------------------------------------------------------------------------
#  Vision overlay (Module C)
# ---------------------------------------------------------------------------
def read_latest_vision(file: Path) -> str:
    """VIBECODER: Module C can append lines like "VISION|Car:0.82,Person:0.91"
    to vision.log. Dashboard tails the file. Replace with sockets if you want."""
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
#  Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Smart Cane Dashboard", layout="wide")
st.title("🦯 Smart Cane Clip-On — Master Dashboard")

with st.sidebar:
    st.header("Source")
    mock_mode = st.toggle("Mock Mode (no hardware)", value=not HAS_SERIAL)

    port = None
    if not mock_mode:
        if not HAS_SERIAL:
            st.error("pyserial not installed. `pip install pyserial`")
        else:
            ports = [p.device for p in list_ports.comports()]
            port = st.selectbox("Serial Port", ports or ["(none detected)"])
        baud = st.number_input("Baud", value=115200, step=9600)

    st.header("🎥 IP Webcam Vision")
    ip_webcam_url = st.text_input("IP Webcam URL", value="http://192.168.1.100:8080/video",
                                  help="URL from IP Webcam app (e.g., http://192.168.1.5:8080/video)")
    vision_model = st.selectbox("YOLO Model", ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt"],
                                help="Smaller models are faster but less accurate")
    vision_conf = st.slider("Confidence Threshold", 0.1, 0.9, 0.45, 0.05)

    # Vision process control
    if "vision_process" not in st.session_state:
        st.session_state.vision_process = None

    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("▶ Start Vision", type="primary"):
            if st.session_state.vision_process is None:
                try:
                    # Launch Universal_Vision.py as separate process
                    cmd = [sys.executable, "Universal_Vision.py",
                           "--src", ip_webcam_url,
                           "--model", vision_model,
                           "--conf", str(vision_conf)]
                    st.session_state.vision_process = subprocess.Popen(cmd)
                    st.success("Vision module started!")
                    time.sleep(2)  # Give it time to initialize
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to start vision: {e}")
            else:
                st.warning("Vision is already running")

    with col_stop:
        if st.button("⏹ Stop Vision"):
            if st.session_state.vision_process is not None:
                try:
                    st.session_state.vision_process.terminate()
                    st.session_state.vision_process.wait(timeout=5)
                    st.session_state.vision_process = None
                    st.success("Vision module stopped!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to stop vision: {e}")
            else:
                st.info("Vision is not running")

    # Show vision status
    vision_status = "🟢 Running" if st.session_state.vision_process else "🔴 Stopped"
    st.caption(f"Status: {vision_status}")

    st.header("Vision overlay")
    vision_log = st.text_input("Path to Module C log", value="vision.log")

    st.header("Display")
    window = st.slider("History window (samples)", 50, 500, 150)
    start = st.toggle("▶ Start stream", value=True)


# --- Session state for history ---
if "hist" not in st.session_state:
    st.session_state.hist = deque(maxlen=500)

# --- Source ---
src = None
if start:
    if mock_mode:
        src = MockSource()
    elif HAS_SERIAL and port and port != "(none detected)":
        try:
            src = SerialSource(port, int(baud))
        except Exception as e:
            st.error(f"Could not open {port}: {e}")

# --- Layout ---
col1, col2, col3, col4 = st.columns(4)
m_fwd  = col1.empty()
m_drop = col2.empty()
m_fall = col3.empty()
m_lux  = col4.empty()

vision_box = st.empty()
chart_fwd  = st.empty()
chart_drop = st.empty()
chart_lux  = st.empty()

# --- Main loop (Streamlit reruns; we loop for ~150 samples per rerun) ---
if src is not None:
    st.session_state.hist = deque(list(st.session_state.hist)[-window:], maxlen=500)

    for _ in range(150):
        pkt = src.read()
        if pkt is None:
            time.sleep(0.05)
            continue
        st.session_state.hist.append({
            "t": time.time(),
            "fwd": pkt.dist_fwd,
            "drop": pkt.dist_drop,
            "fall": pkt.fall_flag,
            "lux": pkt.light_val,
        })

        df = pd.DataFrame(list(st.session_state.hist)[-window:])

        m_fwd.metric("Front dist (mm)", pkt.dist_fwd)
        m_drop.metric("Drop dist (mm)", pkt.dist_drop)
        m_fall.metric("Fall", "⚠ YES" if pkt.fall_flag else "ok")
        m_lux.metric("Light", pkt.light_val)

        vision_txt = read_latest_vision(Path(vision_log))
        vision_box.info(f"🎥 Vision: {vision_txt or '(no detections yet)'}")

        if not df.empty:
            chart_fwd.line_chart(df.set_index("t")[["fwd"]],  height=180)
            chart_drop.line_chart(df.set_index("t")[["drop"]], height=180)
            chart_lux.line_chart(df.set_index("t")[["lux"]],  height=180)

    src.close()
    # Re-trigger Streamlit to keep streaming
    st.rerun()
else:
    st.warning("Stream paused. Toggle **▶ Start stream** in the sidebar.")

# Cleanup vision process on app exit
import atexit
@atexit.register
def cleanup_vision():
    if "vision_process" in st.session_state and st.session_state.vision_process:
        try:
            st.session_state.vision_process.terminate()
            st.session_state.vision_process.wait(timeout=2)
        except:
            pass
