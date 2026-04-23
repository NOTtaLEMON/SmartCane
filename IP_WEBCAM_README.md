# Smart Cane Clip-On - IP Webcam Integration

## Overview
This project integrates IP Webcam functionality into the Smart Cane system, allowing the vision module to run as a separate app that can be controlled from the main dashboard.

## IP Webcam Setup

### 1. Install IP Webcam App
- Download and install "IP Webcam" from Google Play Store on your Android phone
- Alternative: "CameraFi" or similar IP camera apps

### 2. Configure IP Webcam
- Open the IP Webcam app
- Go to settings and configure:
  - Video resolution: 720p or 1080p
  - Video quality: 80-90%
  - Port: 8080 (default)
- Start the server in the app

### 3. Get the Video URL
- The app will show your IP address (e.g., 192.168.1.5:8080)
- Video URL: `http://192.168.1.5:8080/video`
- Alternative URLs:
  - `http://192.168.1.5:8080/videofeed` (some apps)
  - RTSP: `rtsp://192.168.1.5:8080/h264_ulaw.sdp`

### 4. Start the Dashboard
```bash
cd /path/to/SmartCane
source .venv/bin/activate
streamlit run Project_Dashboard.py
```

### 5. Configure Vision in Dashboard
- In the sidebar, enter your IP Webcam URL
- Select YOLO model (yolov8n.pt for speed, yolov8s.pt for accuracy)
- Adjust confidence threshold (0.45 default)
- Click "▶ Start Vision" to launch the vision module

## Features

### Dashboard Controls
- **IP Webcam URL**: Enter the URL from your phone's IP Webcam app
- **YOLO Model**: Choose between nano, small, or medium models
- **Confidence Threshold**: Adjust detection sensitivity
- **Start/Stop Vision**: Launch or terminate the vision process
- **Status Indicator**: Shows if vision module is running

### Vision Module (Separate App)
- Runs as independent process
- Processes IP Webcam stream in real-time
- Detects: Person, Vehicle, Bicycle, Dog, Furniture, Traffic Signs
- Logs detections to `vision.log`
- Can display annotated video window (optional)

## Troubleshooting

### Connection Issues
- Ensure phone and computer are on the same WiFi network
- Check firewall settings allow port 8080
- Try different video URLs from the IP Webcam app
- Restart the IP Webcam app

### Performance Issues
- Use yolov8n.pt for faster processing
- Lower video resolution in IP Webcam app
- Increase confidence threshold to reduce false detections

### macOS Issues
- Grant camera permissions in System Preferences
- Use smaller buffer size for better performance

## Architecture

```
┌─────────────────┐    ┌──────────────────┐
│   Android Phone │───▶│   IP Webcam App  │
│                 │    │   (HTTP/RTSP)    │
└─────────────────┘    └──────────────────┘
                                 │
                                 ▼
┌─────────────────┐    ┌──────────────────┐
│ Streamlit       │───▶│ Universal_Vision │
│ Dashboard       │    │ (Separate Process)│
│ (Controls)      │    └──────────────────┘
└─────────────────┘             │
                               ▼
                       ┌──────────────────┐
                       │   vision.log     │
                       │   (Detections)   │
                       └──────────────────┘
```</content>
<parameter name="filePath">/Users/shreya/Desktop/Memory Game/SmartCane/IP_WEBCAM_README.md