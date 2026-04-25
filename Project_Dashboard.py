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

import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd
import streamlit as st

try:
    import serial
    from serial.tools import list_ports
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False

# ---------------------------------------------------------------------------
#  Visual helpers
# ---------------------------------------------------------------------------
OBJECT_EMOJI: dict[str, str] = {
    "person": "🧑", "car": "🚗", "truck": "🚚", "bus": "🚌",
    "bicycle": "🚲", "motorcycle": "🏍️", "dog": "🐕", "cat": "🐈",
    "chair": "🪑", "bench": "🪑", "bottle": "🍾", "cup": "☕",
    "traffic light": "🚦", "stop sign": "🛑", "fire hydrant": "🚒",
    "backpack": "🎒", "umbrella": "☂️", "handbag": "👜", "cell phone": "📱",
}

def obj_emoji(label: str) -> str:
    return OBJECT_EMOJI.get(label.lower(), "📦")


def normalize_ip_webcam_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""

    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        parsed = urllib.parse.urlparse("http://" + url)

    if parsed.scheme in {"http", "https"} and parsed.path in {"", "/"}:
        parsed = parsed._replace(path="/video")

    return urllib.parse.urlunparse(parsed)


def check_ip_webcam_url(url: str, timeout: int = 5) -> tuple[bool, str, str]:
    if not url:
        return False, "URL is empty", url

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return True, "Only HTTP URLs are validated automatically", url

    candidates = [url]
    base = urllib.parse.urlunparse(parsed._replace(path="", params="", query="", fragment=""))
    fallback_paths = ["/video", "/shot.jpg", "/videofeed", "/h264", "/h264_ulaw.sdp"]
    if parsed.path in {"", "/", "/video"}:
        for path in fallback_paths:
            candidate = urllib.parse.urljoin(base, path)
            if candidate not in candidates:
                candidates.append(candidate)
    else:
        for path in fallback_paths:
            candidate = urllib.parse.urljoin(base, path)
            if candidate not in candidates:
                candidates.append(candidate)

    last_error = "Connection failed"
    for candidate in candidates:
        try:
            req = urllib.request.Request(candidate, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read(64)
                content_type = resp.headers.get("Content-Type", "unknown")
            return True, f"Connected to webcam stream ({candidate} / {content_type})", candidate
        except HTTPError as e:
            last_error = f"HTTP error {e.code}: {e.reason} on {candidate}"
        except URLError as e:
            last_error = f"URL error: {e.reason} on {candidate}"
        except Exception as e:
            last_error = f"Connection failed: {e} on {candidate}"

    return False, last_error, url


def mm_to_readable(mm: int) -> tuple[str, str]:
    """Return (human-readable string, zone colour)."""
    cm = mm / 10
    if cm < 30:
        return f"{cm:.0f} cm", "#ff4b4b"      # critical – red
    elif cm < 80:
        return f"{cm:.0f} cm", "#ffa733"      # warning – orange
    elif cm < 150:
        return f"{cm:.1f} cm", "#f6c000"      # caution – yellow
    else:
        m = mm / 1000
        return f"{m:.2f} m", "#21c55d"        # safe – green

def zone_label(mm: int) -> str:
    cm = mm / 10
    if cm < 30:   return "CRITICAL"
    if cm < 80:   return "WARNING"
    if cm < 150:  return "CAUTION"
    return "CLEAR"

def lux_label(val: int) -> tuple[str, str]:
    if val < 200:   return "Very Dark 🌑", "#6366f1"
    if val < 500:   return "Dim 🌘",        "#a78bfa"
    if val < 800:   return "Moderate 🌤️",  "#38bdf8"
    return "Bright ☀️",                     "#facc15"

def parse_vision_line(raw: str) -> list[tuple[str, float, float]]:
    """Parse 'Person:0.91:800,Car:0.82:1200' → [('Person', 0.91, 800), ('Car', 0.82, 1200)]"""
    results = []
    for token in raw.split(","):
        token = token.strip()
        if ":" in token:
            parts = token.split(":")
            if len(parts) == 3:
                label, conf_str, dist_str = parts
                try:
                    results.append((label.strip(), float(conf_str.strip()), float(dist_str.strip())))
                except ValueError:
                    pass
            elif len(parts) == 2:  # Fallback for old format without distance
                label, conf_str = parts
                try:
                    results.append((label.strip(), float(conf_str.strip()), 1000.0))  # Default distance
                except ValueError:
                    pass
    return sorted(results, key=lambda x: x[2])  # Sort by distance (closest first)

def confidence_bar_html(label: str, conf: float, dist_mm: float) -> str:
    pct = int(conf * 100)
    emoji = obj_emoji(label)
    dist_str, dist_color = mm_to_readable(int(dist_mm))
    if pct >= 85:   bar_color = "#21c55d"
    elif pct >= 65: bar_color = "#f6c000"
    else:           bar_color = "#ffa733"
    return f"""
<div style="
    background:rgba(255,255,255,0.04);
    border:1px solid rgba(255,255,255,0.10);
    border-radius:10px;
    padding:10px 14px;
    margin-bottom:8px;
    font-family:'Segoe UI',sans-serif;
">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
    <span style="font-size:1.1rem;font-weight:600;color:#e2e8f0;">
      {emoji}&nbsp;&nbsp;{label.title()}
    </span>
    <span style="font-size:0.9rem;font-weight:700;color:{bar_color};">{pct}% conf.</span>
  </div>
  <div style="background:rgba(255,255,255,0.10);border-radius:6px;height:8px;overflow:hidden;">
    <div style="width:{pct}%;height:100%;background:{bar_color};
                border-radius:6px;transition:width 0.4s ease;"></div>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
    <span style="font-size:0.8rem;color:#94a3b8;">Distance: {dist_str}</span>
    <span style="font-size:0.7rem;color:{dist_color};font-weight:600;">{zone_label(int(dist_mm))}</span>
  </div>
</div>"""

def sensor_card_html(title: str, value: str, subtitle: str, color: str, icon: str) -> str:
    return f"""
<div style="
    background:linear-gradient(135deg,rgba(255,255,255,0.06) 0%,rgba(255,255,255,0.02) 100%);
    border:1px solid {color}55;
    border-left:4px solid {color};
    border-radius:12px;
    padding:16px 18px;
    font-family:'Segoe UI',sans-serif;
    margin-bottom:4px;
">
  <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:1.2px;
              color:{color};opacity:0.85;margin-bottom:4px;">{icon}&nbsp;{title}</div>
  <div style="font-size:2rem;font-weight:700;color:#f1f5f9;line-height:1.1;">{value}</div>
  <div style="font-size:0.78rem;color:#94a3b8;margin-top:4px;">{subtitle}</div>
</div>"""

def fall_banner_html(active: bool) -> str:
    if active:
        return """<div style="
            background:linear-gradient(90deg,#dc2626,#b91c1c);
            border-radius:12px;padding:14px 20px;
            font-family:'Segoe UI',sans-serif;
            animation:pulse 1s infinite;
            text-align:center;
            font-size:1.3rem;font-weight:700;color:#fff;
            letter-spacing:1px;margin-bottom:10px;
            box-shadow:0 0 20px #dc262688;">
            ⚠️&nbsp;&nbsp;FALL DETECTED — ALERT TRIGGERED&nbsp;&nbsp;⚠️
        </div>"""
    return """<div style="
        background:rgba(34,197,94,0.08);
        border:1px solid rgba(34,197,94,0.25);
        border-radius:12px;padding:10px 20px;
        font-family:'Segoe UI',sans-serif;
        text-align:center;font-size:0.9rem;color:#86efac;
        margin-bottom:10px;">
        ✅&nbsp;&nbsp;No fall detected &nbsp;—&nbsp; IMU stable
    </div>"""


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

        # Accept the original comma-separated packet format.
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) == 4:
            try:
                return cls(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                pass

        # Accept debug output from the Arduino firmware.
        # Example: "Dist:123 LDR:456 Acc:789 OK DARK"
        dist_match = re.search(r"Dist[:\s]*([0-9]+)", raw, re.IGNORECASE)
        ldr_match = re.search(r"LDR[:\s]*([0-9]+)", raw, re.IGNORECASE)
        fall_match = re.search(r"\bFALL\b", raw, re.IGNORECASE)

        if dist_match and ldr_match:
            dist = int(dist_match.group(1))
            ldr = int(ldr_match.group(1))
            fall = 1 if fall_match else 0
            # No dedicated drop sensor in this firmware, so use the forward distance as a fallback.
            drop = dist
            return cls(dist, drop, fall, ldr)

        # Still try a numeric fallback if the string contains three integers.
        nums = re.findall(r"([0-9]+)", raw)
        if len(nums) >= 3:
            try:
                dist = int(nums[0])
                ldr = int(nums[1])
                fall = 1 if fall_match else 0
                return cls(dist, dist, fall, ldr)
            except ValueError:
                pass

        return None


# ---------------------------------------------------------------------------
#  Sources: Serial vs Mock
# ---------------------------------------------------------------------------
class SerialSource:
    def __init__(self, port: str, baud: int = 115200):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.last_raw = ""

    def read(self) -> Packet | None:
        try:
            line = self.ser.readline().decode(errors="ignore")
            if line:
                self.last_raw = line.strip()
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
st.set_page_config(page_title="Smart Cane Dashboard", layout="wide", page_icon="🦯")

# ---- Global CSS ----
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }
  .block-container { padding-top: 1.5rem; }
  h1 { font-size: 1.65rem !important; font-weight: 700 !important; }
  .section-label {
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1.4px;
    color: #64748b; margin-bottom: 6px; margin-top: 18px;
  }
  .divider { border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 14px 0; }
</style>
""", unsafe_allow_html=True)

# ---- Header ----
st.markdown("""
<div style="display:flex;align-items:center;gap:14px;margin-bottom:6px;">
  <span style="font-size:2.4rem;">🦯</span>
  <div>
    <div style="font-size:1.5rem;font-weight:700;color:#f1f5f9;line-height:1.1;">
      Smart Cane Clip-On
    </div>
    <div style="font-size:0.82rem;color:#64748b;letter-spacing:0.5px;">
      Real-time obstacle detection &amp; fall monitoring dashboard
    </div>
  </div>
</div>
<hr class="divider">
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;">⚙️ Configuration</div>', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    st.markdown('<div class="section-label">Data source</div>', unsafe_allow_html=True)

    # Auto-detect: if serial ports are present and the user hasn't explicitly
    # chosen mock mode yet, default to real-hardware mode.
    detected_ports = [p.device for p in list_ports.comports()] if HAS_SERIAL else []
    auto_mock = not bool(detected_ports)
    if "mock_mode_set" not in st.session_state:
        st.session_state["mock_mode_set"] = True
        st.session_state["mock_mode_val"] = auto_mock

    mock_mode = st.toggle("Mock Mode (no hardware)",
                          value=st.session_state["mock_mode_val"],
                          key="mock_mode_toggle")
    st.session_state["mock_mode_val"] = mock_mode

    port = None
    if not mock_mode:
        if not HAS_SERIAL:
            st.error("pyserial not installed. `pip install pyserial`")
        else:
            port = st.selectbox("Serial Port", detected_ports or ["(none detected)"])
        baud = st.number_input("Baud", value=115200, step=9600)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">🎥 Vision module</div>', unsafe_allow_html=True)
    ip_webcam_url = st.text_input("IP Webcam URL", value="http://192.168.1.100:8080/video",
                                  help="URL from IP Webcam app (e.g., http://192.168.1.5:8080/video)")
    vision_model = st.selectbox("YOLO Model", ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt"],
                                help="Smaller models are faster but less accurate")
    vision_conf = st.slider("Confidence Threshold", 0.1, 0.9, 0.45, 0.05)

    if "vision_process" not in st.session_state:
        st.session_state.vision_process = None

    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("▶ Start", type="primary", use_container_width=True):
            if st.session_state.vision_process is None:
                try:
                    resolved_src = normalize_ip_webcam_url(ip_webcam_url)
                    
                    # Skip URL validation for now - let vision module handle it
                    if resolved_src.startswith(("http://", "https://")):
                        st.info(f"Attempting to connect to: {resolved_src}")
                    else:
                        st.info(f"Using local camera: {resolved_src}")

                    vision_script = Path(__file__).resolve().parent / "Universal_Vision.py"
                    log_path = Path(__file__).resolve().parent / "vision_process.log"
                    log_handle = open(log_path, "a", buffering=1)
                    cmd = [sys.executable, str(vision_script),
                           "--src", resolved_src,
                           "--model", vision_model,
                           "--conf", str(vision_conf)]
                    st.session_state.vision_process = subprocess.Popen(
                        cmd,
                        cwd=str(Path(__file__).resolve().parent),
                        stdout=log_handle,
                        stderr=log_handle,
                    )
                    st.session_state.vision_log_path = str(log_path)
                    st.success(f"Vision started using {resolved_src}")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
            else:
                st.warning("Already running")
    with col_stop:
        if st.button("⏹ Stop", use_container_width=True):
            if st.session_state.vision_process is not None:
                try:
                    st.session_state.vision_process.terminate()
                    st.session_state.vision_process.wait(timeout=5)
                    st.session_state.vision_process = None
                    st.success("Stopped!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
            else:
                st.info("Not running")

    vis_running = st.session_state.vision_process is not None
    st.markdown(
        f'<div style="text-align:center;font-size:0.8rem;color:{"#21c55d" if vis_running else "#ef4444"};">'
        f'{"🟢 Vision active" if vis_running else "🔴 Vision offline"}</div>',
        unsafe_allow_html=True)

    if "vision_log_path" in st.session_state:
        try:
            log_path = Path(st.session_state.vision_log_path)
            if log_path.exists():
                with log_path.open("r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-15:]
                st.text_area("Vision process log", value="".join(lines), height=220)
        except Exception:
            pass

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Display</div>', unsafe_allow_html=True)
    vision_log = st.text_input("Vision log path", value="vision.log")
    window = st.slider("History window (samples)", 50, 500, 150)
    start = st.toggle("▶ Start stream", value=True)

    # ---- Raw serial debug monitor ----
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    with st.expander("🔬 Raw Serial Monitor", expanded=False):
        if "serial_raw" not in st.session_state:
            st.session_state.serial_raw = []
        raw_lines = st.session_state.get("serial_raw", [])
        if raw_lines:
            st.code("\n".join(raw_lines[-15:]), language=None)
        else:
            st.caption("No data received yet. Make sure Mock Mode is OFF and the correct COM port is selected.")
        if st.button("Clear", key="clear_serial"):
            st.session_state.serial_raw = []


# --- Live / Mock banner ---
if mock_mode:
    st.markdown("""
<div style="background:rgba(99,102,241,0.12);border:1px solid #6366f166;
  border-radius:10px;padding:8px 16px;margin-bottom:10px;
  font-size:0.85rem;color:#a5b4fc;font-family:'Segoe UI',sans-serif;">
  🎭 <strong>MOCK MODE</strong> — simulated data only.
  Turn off <em>Mock Mode</em> in the sidebar and select your COM port for real sensor data.
</div>""", unsafe_allow_html=True)
else:
    status_col1, status_col2 = st.columns([1, 4])
    with status_col1:
        st.markdown("""
<div style="background:rgba(34,197,94,0.12);border:1px solid #21c55d66;
  border-radius:10px;padding:8px 16px;
  font-size:0.85rem;color:#86efac;font-family:'Segoe UI',sans-serif;text-align:center;">
  ⚡ <strong>LIVE</strong>
</div>""", unsafe_allow_html=True)
    with status_col2:
        st.markdown(
            f'<div style="padding:9px 0;font-size:0.82rem;color:#64748b;">'
            f'Reading from <code>{port}</code> @ {baud if "baud" in dir() else 115200} baud'
            f'</div>', unsafe_allow_html=True)

# --- Session state for history ---
if "hist" not in st.session_state:
    st.session_state.hist = deque(maxlen=500)
if "serial_raw" not in st.session_state:
    st.session_state.serial_raw = []

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

# ---------------------------------------------------------------------------
#  Layout placeholders
# ---------------------------------------------------------------------------
fall_banner_ph = st.empty()

# Row 1: sensor cards
st.markdown('<div class="section-label">📡 Sensor Readings</div>', unsafe_allow_html=True)
sensor_cols = st.columns(4)
card_fwd   = sensor_cols[0].empty()
card_drop  = sensor_cols[1].empty()
card_fall  = sensor_cols[2].empty()
card_lux   = sensor_cols[3].empty()

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# Row 2: detections (left) + proximity gauge (right)
det_col, prox_col = st.columns([3, 2])

with det_col:
    st.markdown('<div class="section-label">🎥 Object Detection</div>', unsafe_allow_html=True)
    detection_ph = st.empty()

with prox_col:
    st.markdown('<div class="section-label">📏 Proximity Assessment</div>', unsafe_allow_html=True)
    proximity_ph = st.empty()

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# Row 3: charts
st.markdown('<div class="section-label">📈 Sensor History</div>', unsafe_allow_html=True)
ch_col1, ch_col2, ch_col3 = st.columns(3)
with ch_col1:
    st.caption("Forward Distance (mm)")
    chart_fwd  = st.empty()
with ch_col2:
    st.caption("Drop Distance (mm)")
    chart_drop = st.empty()
with ch_col3:
    st.caption("Ambient Light")
    chart_lux  = st.empty()

# ---------------------------------------------------------------------------
#  Main update loop
# ---------------------------------------------------------------------------
if src is not None:
    st.session_state.hist = deque(list(st.session_state.hist)[-window:], maxlen=500)

    for _ in range(150):
        pkt = src.read()
        # Capture raw lines for the serial monitor (SerialSource only)
        if hasattr(src, "last_raw") and src.last_raw:
            st.session_state.serial_raw.append(src.last_raw)
            st.session_state.serial_raw = st.session_state.serial_raw[-50:]
        if pkt is None:
            time.sleep(0.05)
            continue

        st.session_state.hist.append({
            "t": time.time(),
            "fwd":  pkt.dist_fwd,
            "drop": pkt.dist_drop,
            "fall": pkt.fall_flag,
            "lux":  pkt.light_val,
        })
        df = pd.DataFrame(list(st.session_state.hist)[-window:])

        # ---- Fall banner ----
        fall_banner_ph.markdown(fall_banner_html(bool(pkt.fall_flag)), unsafe_allow_html=True)

        # ---- Sensor cards ----
        fwd_str,  fwd_color  = mm_to_readable(pkt.dist_fwd)
        drop_str, drop_color = mm_to_readable(pkt.dist_drop)
        lux_str,  lux_color  = lux_label(pkt.light_val)

        card_fwd.markdown(sensor_card_html(
            "Front Obstacle", fwd_str,
            f"Zone: {zone_label(pkt.dist_fwd)}",
            fwd_color, "↔️"), unsafe_allow_html=True)

        card_drop.markdown(sensor_card_html(
            "Drop / Ledge", drop_str,
            f"Zone: {zone_label(pkt.dist_drop)}",
            drop_color, "⬇️"), unsafe_allow_html=True)

        fall_color = "#ff4b4b" if pkt.fall_flag else "#21c55d"
        card_fall.markdown(sensor_card_html(
            "Fall Status",
            "⚠️ FALL" if pkt.fall_flag else "Stable",
            "IMU / accelerometer",
            fall_color, "🏃"), unsafe_allow_html=True)

        card_lux.markdown(sensor_card_html(
            "Ambient Light", lux_str,
            f"Raw ADC: {pkt.light_val}",
            lux_color, "💡"), unsafe_allow_html=True)

        # ---- Vision detections ----
        vision_raw = read_latest_vision(Path(vision_log))
        detections = parse_vision_line(vision_raw) if vision_raw else []

        if detections:
            bars_html = "".join(confidence_bar_html(lbl, conf, dist) for lbl, conf, dist in detections[:6])
            detection_ph.markdown(f"""
<div style="padding:4px 0;">{bars_html}</div>
<div style="font-size:0.72rem;color:#475569;margin-top:6px;">
  Last update: {time.strftime('%H:%M:%S')} &nbsp;·&nbsp; {len(detections)} object(s) in frame
</div>
""", unsafe_allow_html=True)
        else:
            detection_ph.markdown("""
<div style="
  background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.10);
  border-radius:12px;padding:28px;text-align:center;color:#475569;font-size:0.9rem;">
  No objects currently detected<br>
  <span style="font-size:0.75rem;">Waiting for vision module output…</span>
</div>""", unsafe_allow_html=True)

        # ---- Proximity assessment panel ----
        # Use closest detected object distance if available, otherwise fall back to ultrasonic sensor
        if detections:
            closest_obj, closest_conf, closest_dist = detections[0]  # Already sorted by distance
            top_obj = closest_obj.title()
            top_emoji = obj_emoji(closest_obj)
            fwd_pct = max(0, min(100, int((1 - closest_dist / 2000) * 100)))  # 0mm=100%, 2000mm+=0%
            zone = zone_label(int(closest_dist))
            fwd_c, _ = mm_to_readable(int(closest_dist))
            zone_colors = {"CRITICAL": "#ff4b4b", "WARNING": "#ffa733", "CAUTION": "#f6c000", "CLEAR": "#21c55d"}
            zc = zone_colors.get(zone, "#21c55d")
        else:
            # Fall back to ultrasonic sensor data when no vision detections
            top_obj = "Unknown"
            top_emoji = "📦"
            fwd_pct = max(0, min(100, int((1 - pkt.dist_fwd / 2000) * 100)))  # 0mm=100%, 2000mm+=0%
            zone = zone_label(pkt.dist_fwd)
            fwd_c, _ = mm_to_readable(pkt.dist_fwd)
            zone_colors = {"CRITICAL": "#ff4b4b", "WARNING": "#ffa733", "CAUTION": "#f6c000", "CLEAR": "#21c55d"}
            zc = zone_colors.get(zone, "#21c55d")

        zone_colors = {"CRITICAL": "#ff4b4b", "WARNING": "#ffa733", "CAUTION": "#f6c000", "CLEAR": "#21c55d"}
        zc = zone_colors.get(zone, "#21c55d")

        proximity_ph.markdown(f"""
<div style="
  background:linear-gradient(135deg,rgba(255,255,255,0.05),rgba(255,255,255,0.01));
  border:1px solid {zc}44;border-radius:14px;padding:20px 18px;
  font-family:'Segoe UI',sans-serif;
">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:1px;color:#64748b;">
        Nearest Obstacle
      </div>
      <div style="font-size:2.2rem;font-weight:700;color:#f1f5f9;margin:4px 0;">{fwd_c}</div>
      <div style="font-size:0.85rem;color:#94a3b8;">straight ahead</div>
    </div>
    <div style="
      background:{zc}22;border:2px solid {zc};
      border-radius:10px;padding:6px 14px;
      font-size:0.8rem;font-weight:700;color:{zc};letter-spacing:1px;">
      {zone}
    </div>
  </div>
  <div style="margin-top:16px;">
    <div style="font-size:0.7rem;color:#64748b;margin-bottom:5px;">PROXIMITY LEVEL</div>
    <div style="background:rgba(255,255,255,0.08);border-radius:8px;height:12px;overflow:hidden;">
      <div style="width:{fwd_pct}%;height:100%;
        background:linear-gradient(90deg,#21c55d,{zc});
        border-radius:8px;transition:width 0.4s ease;"></div>
    </div>
    <div style="display:flex;justify-content:space-between;
      font-size:0.65rem;color:#475569;margin-top:4px;">
      <span>Far</span><span>Close</span>
    </div>
  </div>
  {"" if not detections else f'''
  <div style="margin-top:14px;border-top:1px solid rgba(255,255,255,0.07);padding-top:12px;">
    <div style="font-size:0.7rem;color:#64748b;margin-bottom:4px;">MOST LIKELY OBJECT</div>
    <div style="font-size:1.05rem;font-weight:600;color:#e2e8f0;">
      {top_emoji}&nbsp;&nbsp;{top_obj}
    </div>
  </div>'''}
</div>
""", unsafe_allow_html=True)

        # ---- Charts ----
        if not df.empty:
            chart_fwd.line_chart(df.set_index("t")[["fwd"]],   height=160, color=["#38bdf8"])
            chart_drop.line_chart(df.set_index("t")[["drop"]],  height=160, color=["#a78bfa"])
            chart_lux.line_chart(df.set_index("t")[["lux"]],   height=160, color=["#facc15"])

    src.close()
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
