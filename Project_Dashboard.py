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
    if pct >= 85:   bar_color = colors['accent_green']
    elif pct >= 65: bar_color = colors['accent_yellow']
    else:           bar_color = "#f97316"
    return f"""
<div style="
    background:linear-gradient(135deg,rgba(255,255,255,0.05) 0%,rgba(255,255,255,0.02) 100%);
    border:1.5px solid {colors['border_light']};
    border-radius:12px;
    padding:14px 16px;
    margin-bottom:10px;
    font-family:'Inter','Segoe UI',sans-serif;
    transition:all 0.3s ease;
    position:relative;
    overflow:hidden;
">
  <div style="
    position:absolute;top:0;right:0;width:80px;height:80px;
    background:radial-gradient(circle, {bar_color}10 0%, transparent 70%);
    border-radius:50%;transform:translate(40%, -40%);
  "></div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;position:relative;z-index:1;">
    <span style="font-size:1.05rem;font-weight:600;color:{colors['text_primary']};">
      {emoji}&nbsp;&nbsp;{label.title()}
    </span>
    <span style="font-size:0.9rem;font-weight:700;color:{bar_color};">{pct}%</span>
  </div>
  <div style="background:{colors['border_light']};border-radius:8px;height:10px;overflow:hidden;margin-bottom:10px;">
    <div style="width:{pct}%;height:100%;background:linear-gradient(90deg,{bar_color} 0%, {bar_color}dd 100%);
                border-radius:8px;transition:width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
                box-shadow:0 0 12px {bar_color}66;"></div>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;position:relative;z-index:1;">
    <span style="color:{colors['text_muted']};font-weight:500;">📏 {dist_str}</span>
    <span style="color:{dist_color};font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">{zone_label(int(dist_mm))}</span>
  </div>
</div>"""

def sensor_card_html(title: str, value: str, subtitle: str, color: str, icon: str) -> str:
    return f"""
<div style="
    background:linear-gradient(135deg,{color}08 0%,{color}04 100%);
    border:1.5px solid {color}40;
    border-radius:14px;
    padding:20px 22px;
    font-family:'Inter','Segoe UI',sans-serif;
    margin-bottom:8px;
    position:relative;
    overflow:hidden;
    box-shadow:0 4px 16px rgba(0,0,0,0.08);
    transition:all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
">
  <div style="
    position:absolute;top:0;right:0;width:100px;height:100px;
    background:radial-gradient(circle, {color}15 0%, transparent 70%);
    border-radius:50%;transform:translate(30%, -30%);
  "></div>
  <div style="
    font-size:0.7rem;
    text-transform:uppercase;
    letter-spacing:1.4px;
    font-weight:600;
    color:{color};
    opacity:0.9;
    margin-bottom:8px;
    position:relative;
    z-index:1;
  ">{icon}&nbsp;&nbsp;{title}</div>
  <div style="
    font-size:2.2rem;
    font-weight:700;
    color:{colors['text_primary']};
    line-height:1.1;
    margin:8px 0;
    position:relative;
    z-index:1;
  ">{value}</div>
  <div style="
    font-size:0.8rem;
    color:{colors['text_muted']};
    margin-top:8px;
    position:relative;
    z-index:1;
  ">{subtitle}</div>
</div>"""

def fall_banner_html(active: bool) -> str:
    if active:
        return f"""<div style="
            background:linear-gradient(90deg,#ef4444,#dc2626);
            border-radius:14px;
            padding:16px 24px;
            font-family:'Inter','Segoe UI',sans-serif;
            animation:glow-anim 1.5s ease-in-out infinite;
            text-align:center;
            font-size:1.25rem;
            font-weight:700;
            color:#fff;
            letter-spacing:0.8px;
            margin-bottom:14px;
            box-shadow:0 0 30px rgba(239, 68, 68, 0.4);
            position:relative;
            overflow:hidden;
        ">
            <div style="
                position:absolute;top:-50%;left:-50%;width:200%;height:200%;
                background:radial-gradient(circle, rgba(255,255,255,0.2) 0%, transparent 70%);
                animation:pulse-subtle 2s ease-in-out infinite;
            "></div>
            <div style="position:relative;z-index:1;">
                ⚠️&nbsp;&nbsp;FALL DETECTED — ALERT TRIGGERED&nbsp;&nbsp;⚠️
            </div>
        </div>"""
    return f"""<div style="
        background:linear-gradient(135deg,{colors['accent_green']}12 0%,{colors['accent_green']}08 100%);
        border:1.5px solid {colors['accent_green']}50;
        border-radius:14px;
        padding:12px 24px;
        font-family:'Inter','Segoe UI',sans-serif;
        text-align:center;
        font-size:0.9rem;
        color:{colors['accent_green']};
        margin-bottom:14px;
        font-weight:600;
        letter-spacing:0.5px;
    ">
        ✅&nbsp;&nbsp;No fall detected&nbsp;—&nbsp;IMU stable
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

# ---- Global CSS with Theme Support ----
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "dark"  # 'dark' or 'light'

theme = st.session_state.theme_mode

# Color palettes
THEMES = {
    "dark": {
        "bg_primary": "#0f172a",
        "bg_secondary": "#1e293b",
        "bg_tertiary": "#334155",
        "text_primary": "#f1f5f9",
        "text_secondary": "#cbd5e1",
        "text_muted": "#64748b",
        "border_light": "rgba(255,255,255,0.08)",
        "border_medium": "rgba(255,255,255,0.15)",
        "accent_blue": "#0ea5e9",
        "accent_green": "#10b981",
        "accent_red": "#ef4444",
        "accent_yellow": "#f59e0b",
        "accent_purple": "#8b5cf6",
    },
    "light": {
        "bg_primary": "#ffffff",
        "bg_secondary": "#f8fafc",
        "bg_tertiary": "#e2e8f0",
        "text_primary": "#1e293b",
        "text_secondary": "#334155",
        "text_muted": "#94a3b8",
        "border_light": "rgba(0,0,0,0.06)",
        "border_medium": "rgba(0,0,0,0.12)",
        "accent_blue": "#0284c7",
        "accent_green": "#059669",
        "accent_red": "#dc2626",
        "accent_yellow": "#d97706",
        "accent_purple": "#7c3aed",
    }
}

colors = THEMES[theme]

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
  
  :root {{
    --bg-primary: {colors['bg_primary']};
    --bg-secondary: {colors['bg_secondary']};
    --text-primary: {colors['text_primary']};
    --text-secondary: {colors['text_secondary']};
    --text-muted: {colors['text_muted']};
    --border-light: {colors['border_light']};
    --accent-blue: {colors['accent_blue']};
    --accent-green: {colors['accent_green']};
  }}
  
  html, body, [class*="css"] {{ 
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background-color: {colors['bg_primary']} !important;
    color: {colors['text_primary']} !important;
  }}
  
  .block-container {{ 
    padding-top: 2rem; 
    max-width: 1400px;
  }}
  
  h1 {{ 
    font-size: 2rem !important; 
    font-weight: 700 !important;
    letter-spacing: -0.02em;
    line-height: 1.2 !important;
  }}
  
  h2, h3 {{
    font-weight: 600 !important;
    letter-spacing: -0.01em;
  }}
  
  .section-label {{
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 1.6px;
    font-weight: 600;
    color: {colors['text_muted']};
    margin-bottom: 12px;
    margin-top: 24px;
    display: block;
  }}
  
  .divider {{ 
    border: none;
    border-top: 1px solid {colors['border_light']};
    margin: 20px 0;
  }}
  
  /* Animations */
  @keyframes pulse-subtle {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.7; }}
  }}
  
  @keyframes slide-in {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
  
  @keyframes glow {{
    0%, 100% {{ box-shadow: 0 0 15px rgba(34, 197, 94, 0.3); }}
    50% {{ box-shadow: 0 0 25px rgba(34, 197, 94, 0.5); }}
  }}
  
  .pulse-anim {{ animation: pulse-subtle 2s ease-in-out infinite; }}
  .slide-in {{ animation: slide-in 0.4s ease-out; }}
  .glow-anim {{ animation: glow 2s ease-in-out infinite; }}
  
  /* Smooth transitions */
  * {{
    transition: background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
  }}
  
  button, [role="button"] {{
    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
  }}
</style>
""", unsafe_allow_html=True)

# ---- Header with Theme Toggle ----
header_col1, header_col2 = st.columns([1, 0.15])

with header_col1:
    st.markdown(f"""
<div style="display:flex;align-items:center;gap:16px;margin-bottom:8px;animation:slide-in 0.6s ease-out;">
  <div style="
    font-size:3rem;
    filter: drop-shadow(0 4px 12px rgba(59, 130, 246, 0.2));
  ">🦯</div>
  <div>
    <div style="
      font-size:2rem;
      font-weight:700;
      color:{colors['text_primary']};
      line-height:1.2;
      letter-spacing:-0.02em;
    ">
      Smart Cane Clip-On
    </div>
    <div style="
      font-size:0.85rem;
      color:{colors['text_muted']};
      letter-spacing:0.3px;
      margin-top:4px;
    ">
      Real-time obstacle detection &amp; fall monitoring dashboard
    </div>
  </div>
</div>
<hr class="divider">
    """, unsafe_allow_html=True)

with header_col2:
    new_theme = "light" if theme == "dark" else "dark"
    theme_icon = "☀️" if theme == "dark" else "🌙"
    if st.button(theme_icon, key="theme_toggle", help="Toggle theme"):
        st.session_state.theme_mode = new_theme
        st.rerun()

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
    st.markdown(f"""
<div style="
  background:linear-gradient(135deg,{colors['accent_purple']}12 0%,{colors['accent_purple']}08 100%);
  border:1.5px solid {colors['accent_purple']}50;
  border-radius:14px;
  padding:12px 18px;
  margin-bottom:14px;
  font-size:0.85rem;
  color:{colors['accent_purple']};
  font-family:'Inter','Segoe UI',sans-serif;
  font-weight:600;
  letter-spacing:0.3px;
>
  🎭 <strong>MOCK MODE</strong> — simulated data only.
  Turn off <em>Mock Mode</em> in the sidebar and select your COM port for real sensor data.
</div>""", unsafe_allow_html=True)
else:
    status_col1, status_col2 = st.columns([1, 4])
    with status_col1:
        st.markdown(f"""
<div style="
  background:linear-gradient(135deg,{colors['accent_green']}20 0%,{colors['accent_green']}12 100%);
  border:1.5px solid {colors['accent_green']}60;
  border-radius:14px;
  padding:10px 16px;
  font-size:0.85rem;
  color:{colors['accent_green']};
  font-family:'Inter','Segoe UI',sans-serif;
  text-align:center;
  font-weight:700;
  letter-spacing:0.5px;
>
  ⚡ <strong>LIVE</strong>
</div>""", unsafe_allow_html=True)
    with status_col2:
        st.markdown(
            f'<div style="padding:11px 0;font-size:0.82rem;color:{colors["text_muted"]};font-weight:500;">' 
            f'Reading from <code style="background:{colors["bg_secondary"]};padding:2px 6px;border-radius:4px;">{port}</code> @ {baud if "baud" in dir() else 115200} baud'
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
st.markdown(f'<div class="section-label" style="margin-top:0;">📡 Sensor Readings</div>', unsafe_allow_html=True)
sensor_cols = st.columns(4, gap="medium")
card_fwd   = sensor_cols[0].empty()
card_drop  = sensor_cols[1].empty()
card_fall  = sensor_cols[2].empty()
card_lux   = sensor_cols[3].empty()

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# Row 2: detections (left) + proximity gauge (right)
det_col, prox_col = st.columns([3, 2], gap="medium")

with det_col:
    st.markdown('<div class="section-label">🎥 Object Detection</div>', unsafe_allow_html=True)
    detection_ph = st.empty()

with prox_col:
    st.markdown('<div class="section-label">📏 Proximity Assessment</div>', unsafe_allow_html=True)
    proximity_ph = st.empty()

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# Row 3: charts
st.markdown('<div class="section-label">📈 Sensor History</div>', unsafe_allow_html=True)
ch_col1, ch_col2, ch_col3 = st.columns(3, gap="medium")
with ch_col1:
    st.caption("📏 Forward Distance (mm)")
    chart_fwd  = st.empty()
with ch_col2:
    st.caption("⬇️ Drop Distance (mm)")
    chart_drop = st.empty()
with ch_col3:
    st.caption("💡 Ambient Light (lux)")
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

        fall_color = colors['accent_red'] if pkt.fall_flag else colors['accent_green']
        card_fall.markdown(sensor_card_html(
            "Fall Status",
            "⚠️ FALL" if pkt.fall_flag else "✓ Stable",
            "IMU / accelerometer",
            fall_color, "🚨"), unsafe_allow_html=True)

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
<div style="font-size:0.7rem;color:{colors['text_muted']};margin-top:10px;font-weight:500;">
  ⏱️ Last update: {time.strftime('%H:%M:%S')} &nbsp;·&nbsp; {len(detections)} object(s) detected
</div>
""", unsafe_allow_html=True)
        else:
            detection_ph.markdown(f"""
<div style="
  background:linear-gradient(135deg,rgba(255,255,255,0.02) 0%,rgba(255,255,255,0.01) 100%);\n  border:2px dashed {colors['border_light']};\n  border-radius:14px;padding:36px 24px;text-align:center;color:{colors['text_muted']};font-size:0.9rem;font-family:'Inter','Segoe UI',sans-serif;\">\n  📭 No objects currently detected<br>\n  <span style=\"font-size:0.8rem;color:{colors['text_muted']};opacity:0.7;\">Waiting for vision module output…</span>\n</div>""", unsafe_allow_html=True)

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

        zone_colors = {"CRITICAL": colors['accent_red'], "WARNING": "#f97316", "CAUTION": colors['accent_yellow'], "CLEAR": colors['accent_green']}
        zc = zone_colors.get(zone, colors['accent_green'])

        proximity_ph.markdown(f"""
<div style="
  background:linear-gradient(135deg,{zc}10 0%,{zc}05 100%);
  border:1.5px solid {zc}50;
  border-radius:16px;
  padding:24px 20px;
  font-family:'Inter','Segoe UI',sans-serif;
  position:relative;
  overflow:hidden;
  box-shadow:0 8px 24px {zc}15;
  animation:slide-in 0.5s ease-out;
">
  <div style="
    position:absolute;top:-60%;right:-60%;width:200%;height:200%;
    background:radial-gradient(circle, {zc}20 0%, transparent 70%);
    border-radius:50%;pointer-events:none;
  "></div>
  <div style="display:flex;justify-content:space-between;align-items:flex-start;position:relative;z-index:1;">
    <div>
      <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.4px;color:{zc};font-weight:700;opacity:0.9;">
        📍 Nearest Obstacle
      </div>
      <div style="font-size:2.4rem;font-weight:700;color:{colors['text_primary']};margin:8px 0;line-height:1.1;">{fwd_c}</div>
      <div style="font-size:0.85rem;color:{colors['text_muted']};font-weight:500;">straight ahead</div>
    </div>
    <div style="
      background:{zc}20;border:2px solid {zc};
      border-radius:12px;padding:8px 16px;
      font-size:0.75rem;font-weight:700;color:{zc};letter-spacing:1px;text-transform:uppercase;">
      {zone}
    </div>
  </div>
  <div style="margin-top:22px;position:relative;z-index:1;">
    <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.4px;color:{colors['text_muted']};font-weight:700;margin-bottom:8px;">Proximity Level</div>
    <div style="background:{colors['border_light']};border-radius:10px;height:14px;overflow:hidden;box-shadow:inset 0 2px 4px rgba(0,0,0,0.2);">
      <div style="width:{fwd_pct}%;height:100%;
        background:linear-gradient(90deg,{colors['accent_green']} 0%, {zc} 100%);
        border-radius:10px;
        transition:width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
        box-shadow:0 0 16px {zc}50;"></div>
    </div>
    <div style="display:flex;justify-content:space-between;
      font-size:0.7rem;color:{colors['text_muted']};margin-top:6px;font-weight:500;">
      <span>🟢 Far</span><span>🔴 Close</span>
    </div>
  </div>
  {"" if not detections else f'''
  <div style="margin-top:18px;border-top:1px solid {colors['border_light']};padding-top:16px;position:relative;z-index:1;">
    <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.4px;color:{colors['text_muted']};font-weight:700;margin-bottom:6px;">Most Likely Object</div>
    <div style="font-size:1.15rem;font-weight:700;color:{colors['text_primary']};">
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
