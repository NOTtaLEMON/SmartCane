# -*- coding: utf-8 -*-
"""
Smart Cane Clip-On  |  Live Dashboard
Reads ESP32 serial data, shows sensor readings + YOLO detections.
Run: streamlit run Project_Dashboard.py
"""

from __future__ import annotations

import io
import random
import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
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

_OBJECT_EMOJI: dict[str, str] = {
    "person": "🚶", "human": "🚶", "pedestrian": "🚶",
    "car": "🚗", "truck": "🚚", "bus": "🚌", "motorcycle": "🏍️", "bicycle": "🚲",
    "dog": "🐶", "cat": "🐱", "bird": "🐦",
    "chair": "🪑", "bench": "🪨", "couch": "🛋️", "sofa": "🛋️",
    "table": "🪵", "desk": "🪵",
    "bottle": "🍾", "cup": "☕", "bowl": "🍜",
    "stairs": "🚶", "step": "📍", "door": "🚪", "wall": "🧱",
    "pole": "🧽", "tree": "🌳", "plant": "🌱",
    "backpack": "🎒", "handbag": "👜", "suitcase": "🗃️",
    "laptop": "💻", "phone": "📱", "tv": "📺",
    "fire hydrant": "🚧", "stop sign": "🛑", "traffic light": "🚦",
}

def object_emoji(label: str) -> str:
    key = label.lower().strip()
    return _OBJECT_EMOJI.get(key, "📌")

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
        self.ser = serial.Serial(port, baud, timeout=0.3)
        self.last_raw = ""

    def read(self) -> "Packet | None":
        try:
            # Drain all stale buffered packets, keep only the freshest
            last_pkt = None
            while self.ser.in_waiting:
                line = self.ser.readline().decode(errors="ignore").strip()
                if line:
                    pkt = Packet.parse(line)
                    if pkt:
                        last_pkt = pkt
                        self.last_raw = line
                    else:
                        self.last_raw = f"[PARSE FAIL] {line}"
            if last_pkt:
                return last_pkt
            # Buffer empty -- wait for the next fresh packet
            line = self.ser.readline().decode(errors="ignore").strip()
            if line:
                pkt = Packet.parse(line)
                self.last_raw = line if pkt else f"[PARSE FAIL] {line}"
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
        self.preset_mode = None
        self.preset_duration = 0

    def set_preset(self, mode: str, duration: int = 50):
        """Set a preset simulation mode (fall, close_obstacle, or normal)"""
        self.preset_mode = mode
        self.preset_duration = duration

    def read(self) -> Packet:
        self._t += 1
        
        # Handle preset modes
        if self.preset_mode and self.preset_duration > 0:
            self.preset_duration -= 1
            
            if self.preset_mode == "fall":
                # Simulate a fall event
                fwd = int(400 + 50 * random.random())
                drop = int(100 + 30 * random.random())  # Very close drop detection
                fall = 1  # Fall detected
                light = int(500 + 200 * random.random())
            elif self.preset_mode == "close_obstacle":
                # Simulate a close obstacle (critical zone)
                fwd = int(100 + 50 * random.random())  # Very close: 100-150mm
                drop = int(180 + random.randint(-40, 40))
                fall = 0
                light = int(500 + 200 * random.random())
            else:
                # Normal mode
                fwd = max(50, int(400 + 300 * random.random() - (self._t % 30) * 5))
                drop = int(180 + random.randint(-40, 40))
                fall = 0
                light = int(500 + 200 * random.random())
        else:
            if self.preset_mode:
                self.preset_mode = None
            # Normal operation
            fwd = max(50, int(400 + 300 * random.random() - (self._t % 30) * 5))
            drop = int(180 + random.randint(-40, 40))
            fall = 1 if random.random() < 0.01 else 0
            light = int(500 + 200 * random.random())
        
        time.sleep(0.1)
        return Packet(fwd, drop, fall, light)

    def close(self):
        pass

# ---------------------------------------------------------------------------
#  Page setup
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Smart Cane Dashboard", layout="wide", page_icon="🦯")

# Custom CSS for better aesthetics
st.markdown("""
    <style>
        /* Main container styling */
        .main {
            padding: 0.5rem 1rem;
        }
        
        /* Title styling */
        h1 {
            color: #1f77b4;
            text-align: center;
            padding-bottom: 0.5rem;
        }
        
        /* Subheader styling */
        h2 {
            color: #2e86de;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 0.5rem;
            margin-top: 1.5rem;
        }
        
        /* Metric cards styling */
        [data-testid="metric-container"] {
            background-color: #f8f9fa;
            border-radius: 8px;
            padding: 1rem;
            border-left: 4px solid #2e86de;
        }
        
        /* Info boxes */
        [data-testid="stAlert"] {
            border-radius: 8px;
            margin: 0.5rem 0;
        }
        
        /* Better spacing */
        hr {
            margin: 1.5rem 0;
        }
    </style>
""", unsafe_allow_html=True)

st.title("🦯 Smart Cane Clip-On")
st.caption("Real-time obstacle detection & fall monitoring dashboard")
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
    start      = st.toggle("Start stream", value=True)
    
    # Mock presets section
    if mock_mode:
        st.divider()
        st.subheader("Demo Presets")
        st.caption("Simulate scenarios for testing (5 seconds)")
        
        if "mock_src" in st.session_state and isinstance(st.session_state.get("mock_src"), MockSource):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🚨 Simulate Fall", use_container_width=True, help="Trigger fall detection demo"):
                    st.session_state.mock_src.set_preset("fall", duration=50)
                    st.info("Fall scenario activated!")
            with col2:
                if st.button("🚪 Close Obstacle", use_container_width=True, help="Detect obstacle <150mm away"):
                    st.session_state.mock_src.set_preset("close_obstacle", duration=50)
                    st.info("Close obstacle scenario activated!")

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
if "mock_src" not in st.session_state:
    st.session_state.mock_src = None

# ---------------------------------------------------------------------------
#  Open source (cached so the port stays open across reruns)
# ---------------------------------------------------------------------------

src = None
if start:
    if mock_mode:
        src = MockSource()
        st.session_state.mock_src = src  # Store reference for preset buttons
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

# Export/Download section
st.markdown("### 📊 Data Management")
exp_col1, exp_col2 = st.columns([2, 1])
with exp_col1:
    if st.session_state.hist:
        # Create DataFrame from history
        hist_data = pd.DataFrame(list(st.session_state.hist))
        if not hist_data.empty:
            hist_data["timestamp"] = pd.to_datetime(hist_data["t"], unit="s")
            hist_data = hist_data[["timestamp", "fwd", "drop", "fall", "lux"]]
            hist_data.columns = ["Timestamp", "Forward Distance (mm)", "Drop Distance (mm)", "Fall Detected", "Light Level"]
            
            # Create CSV
            csv_buffer = io.StringIO()
            hist_data.to_csv(csv_buffer, index=False)
            csv_data = csv_buffer.getvalue()
            
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv_data,
                file_name=f"smartcane_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.caption("No data collected yet. Start the stream to record sensor data.")

with exp_col2:
    if st.session_state.hist:
        st.metric("Records", len(st.session_state.hist))

st.divider()

fall_ph = st.empty()

st.subheader("🔍 Sensor Readings")
c1, c2, c3, c4 = st.columns(4)
card_fwd  = c1.empty()
card_drop = c2.empty()
card_fall = c3.empty()
card_lux  = c4.empty()

st.divider()

with st.container():
    st.subheader("Camera-Based Object Detection")
    detection_ph = st.empty()

st.divider()
st.subheader("📈 Sensor History")
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

        # Fall banner
        if pkt.fall_flag:
            fall_ph.error("FALL DETECTED -- ALERT TRIGGERED")
        else:
            fall_ph.success("No fall detected -- IMU stable")

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

        # Filter detections by confidence threshold (>50%)
        valid_detections = [(lbl, conf) for lbl, conf in detections if conf * 100 > 50]

        detection_ph.empty()
        if valid_detections:
            lines = ["**Object detected**\n"]
            for lbl, conf in valid_detections[:6]:
                pct = int(conf * 100)
                emoji = object_emoji(lbl)
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                lines.append(f"{emoji} **{lbl.title()}**  \n`{bar}` {pct}%\n")
            detection_ph.success("\n".join(lines))
        else:
            detection_ph.info("No object detected")

        # Charts
        if not df.empty:
            chart_fwd.line_chart(df.set_index("t")[["fwd"]],   height=160)
            chart_drop.line_chart(df.set_index("t")[["drop"]], height=160)
            chart_lux.line_chart(df.set_index("t")[["lux"]],   height=160)

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