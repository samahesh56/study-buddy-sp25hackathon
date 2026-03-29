# 🎯 Real-Time Attention Classifier

> **HackPSU 2026 — Computer Vision Module**

A real-time attention monitoring system that uses your webcam to classify your focus state while studying or working. Built with **MediaPipe**, **OpenCV**, **YOLOv8**, and **Matplotlib**.

---

## 🧠 What It Does

The system watches you through your webcam and classifies your attention into **three states**:

| State | Description |
|---|---|
| 🟢 **Focused** | Face forward, eyes on screen, engaged |
| 🟡 **Semi-Focused** | Face visible but not perfectly aligned (slight head tilt, gaze drift) |
| 🔴 **Away** | No face detected, or head turned completely away |

It also detects **phone usage** (via YOLOv8 object detection + head pitch analysis) and tracks a variety of behavioral signals to compute a **focus score** every 5 seconds.

---

## 🔍 How It Works

### Detection Pipeline

1. **Face Landmark Detection** — MediaPipe Face Landmarker (468+ landmarks) tracks full face mesh in real time.
2. **Head Pose Estimation** — `cv2.solvePnP` computes yaw/pitch/roll from 3D landmark mapping, supplemented by raw landmark geometry for robust downward-tilt detection.
3. **Iris Tracking** — Iris offset relative to eye corners determines gaze direction (left/right/down).
4. **Blink Detection** — Eye Aspect Ratio (EAR) algorithm counts blinks and detects prolonged eye closures.
5. **Phone Detection** — YOLOv8n detects phones in the frame; head pitch + gaze patterns infer phone use even without a visible phone.
6. **Hand Gesture Recognition** — MediaPipe Hand Landmarker detects a **double thumbs-up** gesture to gracefully end a session.
7. **Focus Scoring** — A weighted composite score (0–100) is computed every 5-second window, factoring in face presence, forward gaze duration, blink rate, head motion, and more.

### Focus Score Components

| Signal | Weight |
|---|---|
| Face presence | 20% |
| Forward gaze percentage | 35% |
| Longest forward streak | 15% |
| Eye-open consistency | 10% |
| Head stability (low motion) | 10% |
| Few look-away events | 10% |
| No long eye closures | 5% |
| Phone candidate penalty | −5% |

---

## 📁 Project Structure

```
HackPSU2026(ComputerVision)/
├── ComputerVision/
│   ├── attention_classifier.py   # Main application (~1700 lines)
│   ├── face_landmarker.task      # MediaPipe face landmark model
│   ├── hand_landmarker.task      # MediaPipe hand landmark model
│   ├── yolov8n.pt                # YOLOv8 nano model for phone detection
│   └── Data/                     # Session output (JSON, CSV, PNG)
│       └── <session_id>/
│           ├── <session_id>_transitions.json
│           ├── <session_id>_snapshots.json
│           ├── <session_id>_windows.csv
│           ├── <session_id>_summary.png
│           └── distracted/       # Auto-captured distraction screenshots
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.9+**
- A working **webcam**

### Installation

```bash
# Clone the repository
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install opencv-python mediapipe ultralytics numpy matplotlib
```

> **Optional:** Install `playsound` for audio alerts when you've been away too long:
> ```bash
> pip install playsound
> ```

### Running

```bash
python ComputerVision/attention_classifier.py
```

A window will open showing your webcam feed with:
- 🎨 **Color-coded banner** showing your current state
- 📊 **Live stats** (FPS, blink count, focus score)
- 🧩 **Face mesh overlay** drawn on your face
- 📈 **Timeline bar** at the bottom showing state history
- ⏱️ **Dwell timers** for each state

### Ending a Session

- Press **`q`** or **`Esc`** to quit
- Or show **two thumbs up** 👍👍 to the camera for ~1 second

---

## 📊 Session Output

After each session, the system saves detailed data to `ComputerVision/Data/`:

| File | Description |
|---|---|
| `*_transitions.json` | State changes with timestamps and durations |
| `*_snapshots.json` | Periodic snapshots of all metrics (every 5s) |
| `*_windows.csv` | One row per 5-second focus window with all computed signals |
| `*_summary.png` | Visual summary: pie chart, timeline, and EAR chart |
| `distracted/*.png` | Auto-captured annotated screenshots during distraction events |

---

## ⚙️ Configuration

Key thresholds can be tuned at the top of `attention_classifier.py`:

| Parameter | Default | Description |
|---|---|---|
| `YAW_AWAY_BASE` | 35° | Yaw threshold to classify as AWAY |
| `PITCH_DOWN_PHONE` | 12° | Pitch threshold for phone detection |
| `EAR_BLINK_THRESH` | 0.21 | Eye Aspect Ratio threshold for blinks |
| `PHONE_CONF_THRESH` | 0.30 | YOLO confidence threshold for phone |
| `WINDOW_SECONDS` | 5.0s | Focus scoring window duration |
| `ALERT_AWAY_SEC` | 10.0s | Seconds away before alert fires |
| `FOCUS_DISTRACTED_THRESHOLD` | 50.0 | Score below which = DISTRACTED |

---

## 🛠️ Tech Stack

- **[MediaPipe](https://mediapipe.dev/)** — Face & hand landmark detection
- **[OpenCV](https://opencv.org/)** — Video capture, image processing, head pose estimation
- **[YOLOv8](https://docs.ultralytics.com/)** (Ultralytics) — Real-time phone object detection
- **[NumPy](https://numpy.org/)** — Numerical computations
- **[Matplotlib](https://matplotlib.org/)** — Session summary chart generation

---

## 👥 Team

Built for **HackPSU 2026**.

---

## 📄 License

This project was built for a hackathon. Feel free to use and modify for educational purposes.
