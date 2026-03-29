"""
attention_classifier.py  v3.0
==============================
Merged attention classifier + camera focus tracker.

Attention States
----------------
  AWAY             (no face / looking off-screen)
  ON_PHONE        (phone (YOLO) + head pitched down)
  USING_COMPUTER  (face present, looking at screen)
  DISTRACTED      face present but focus score < 50 (new))

Focus scoring (every WINDOW_SECONDS) is inherited from camera_focus_tracker:
  • face presence / forward-gaze fraction
  • blink rate / long eye closures
  • head-motion bursts
  • look-away event count
  • phone-candidate & writing-candidate heuristics
  • desk-ROI and near-face-ROI frame-diff motion

Output  (written to ./Data/ on exit)
  <timestamp>.json          (full session + per-snapshot data)
  <timestamp>_windows.csv   (one row per 5-second focus window)
  <timestamp>_summary.png   (pie / timeline / EAR chart)

Dependencies
------------
  pip install opencv-python mediapipe ultralytics numpy matplotlib
"""

# ---------------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------------
import collections
import csv
import json
import math
import os
import re
import signal
import time
import threading
import urllib.request
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path

# ---------------------------------------------------------------------------
# Third-party
# ---------------------------------------------------------------------------
import cv2
import mediapipe as mp
import numpy as np
from ultralytics import YOLO

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

try:
    from playsound import playsound as _playsound
    _HAS_SOUND = True
except ImportError:
    _HAS_SOUND = False

# ===========================================================================
# Configuration
# ===========================================================================

# ── Head-pose thresholds (degrees) ─────────────────────────────────────────
YAW_AWAY_BASE        = 35.0
PITCH_DOWN_PHONE     = 12.0
PITCH_UP_AWAY        = 25.0

# ── Gaze (iris) ────────────────────────────────────────────────────────────
GAZE_SIDE_THRESH     = 0.20
GAZE_DOWN_THRESH     = 0.18
GAZE_CONFIRM_FRAMES  = 5

# ── Blink (EAR-based) ──────────────────────────────────────────────────────
EAR_BLINK_THRESH     = 0.21
EAR_CONSEC_FRAMES    = 2

# ── YOLO ───────────────────────────────────────────────────────────────────
YOLO_MODEL_NAME      = "yolov8n.pt"
PHONE_CLASS_ID       = 67
PHONE_CONF_THRESH    = 0.30
YOLO_SKIP_FRAMES     = 2
PHONE_PERSIST_FRAMES = 15        # keep ON_PHONE for N frames after last YOLO hit
PHONE_PITCH_THRESH   = -15.0     # head pitched down this much → phone candidate
PHONE_PITCH_STRONG   = -25.0     # strongly pitched down → very likely phone
PHONE_GAZE_DOWN_MS   = 1.5       # seconds of gaze-down before triggering phone

# ── Smoothing ──────────────────────────────────────────────────────────────
BUFFER_SIZE          = 1

# ── Alert ──────────────────────────────────────────────────────────────────
ALERT_AWAY_SEC       = 10.0
ALERT_COOLDOWN_SEC   = 15.0
ALERT_SOUND_PATH     = Path(__file__).parent / "alert.wav"

# ── Focus-window (from camera_focus_tracker) ───────────────────────────────
WINDOW_SECONDS                  = 5.0
CENTER_X_MIN                    = 0.30
CENTER_X_MAX                    = 0.70
CENTER_Y_MIN                    = 0.25
CENTER_Y_MAX                    = 0.78
MIN_FACE_AREA_RATIO             = 0.03
LOOKAWAY_MIN_DURATION           = 0.35
BLINK_MIN_DURATION              = 0.05
BLINK_MAX_DURATION              = 0.45
LONG_EYE_CLOSURE_MIN            = 0.25
LONG_EYE_CLOSURE_MAX            = 1.50
MOTION_BURST_THRESHOLD          = 0.020
LOOKING_DOWN_CENTER_Y_MIN       = 0.58
LOOKING_DOWN_NO_EYES_CENTER_Y_MIN = 0.48
MOTION_DIFF_THRESHOLD           = 25
NEAR_FACE_MOTION_ACTIVE_THRESH  = 0.018
DESK_MOTION_ACTIVE_THRESH       = 0.010
PHONE_STREAK_MIN_SECONDS        = 1.00
WRITING_STREAK_MIN_SECONDS      = 1.00

# Focus label → attention state override
FOCUS_DISTRACTED_THRESHOLD      = 50.0   # score below this → DISTRACTED state
DISTRACT_SNAP_COOLDOWN_SEC      = 10.0   # min seconds between distraction screenshots

# ── Output ─────────────────────────────────────────────────────────────────
DATA_DIR              = Path(__file__).parent / "Data"
SNAPSHOT_INTERVAL_SEC = 5.0
STOP_REQUESTED        = False
READY_FILE_PATH       = os.environ.get("STUDYCLAW_CV_READY_FILE")

# ── Display ────────────────────────────────────────────────────────────────
WINDOW_NAME   = "Attention Classifier  [q / Esc to quit]"
OVERLAY_ALPHA = 0.50
TIMELINE_HEIGHT = 14

STATE_STYLE = {
    "AWAY"           : {"bgr": (30,  30, 210), "label": "AWAY",           "hex": "#e01e1e"},
    "SEMI_FOCUSED"   : {"bgr": (20, 200, 240), "label": "SEMI-FOCUSED",   "hex": "#f0c800"},
    "FOCUSED"        : {"bgr": (40, 185,  60), "label": "FOCUSED",        "hex": "#28b940"},
}

# Face mesh landmark connections for drawing
_FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
              397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
              172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10]
_LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387,
             386, 385, 384, 398, 362]
_RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158,
              159, 160, 161, 246, 33]
_LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270,
         269, 267, 0, 37, 39, 40, 185, 61]
_LEFT_BROW = [276, 283, 282, 295, 285, 300, 293, 334, 296, 336]
_RIGHT_BROW = [46, 53, 52, 65, 55, 70, 63, 105, 66, 107]
_NOSE_BRIDGE = [6, 197, 195, 5, 4, 1]

CSV_HEADERS = [
    "timestamp", "window_length_sec",
    "face_present", "face_present_percent", "face_missing_seconds",
    "longest_face_missing_seconds", "looking_forward_percent",
    "longest_forward_streak_seconds", "lookaway_events", "blink_count",
    "avg_blink_duration_sec", "long_eye_closure_count", "eye_closed_percent",
    "head_motion_score", "motion_burst_count", "avg_face_area_percent",
    "looking_down_percent", "near_face_motion_percent", "desk_motion_percent",
    "phone_candidate_percent", "writing_candidate_percent",
    "longest_phone_streak_seconds", "longest_writing_streak_seconds",
    "likely_phone_use", "likely_writing",
    "camera_focus_score", "camera_focus_label",
    "attention_state",
]

_LANDMARKER_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
_LANDMARKER_PATH = Path(__file__).parent / "face_landmarker.task"

_HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
_HAND_LANDMARKER_PATH = Path(__file__).parent / "hand_landmarker.task"

# ===========================================================================
# Attention state
# ===========================================================================

class AttentionState(Enum):
    AWAY            = auto()
    SEMI_FOCUSED    = auto()
    FOCUSED         = auto()

# ===========================================================================
# Helpers (from camera_focus_tracker)
# ===========================================================================

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _clip_rect(x0, y0, x1, y1, fw, fh):
    x0, x1 = max(0, min(fw, int(x0))), max(0, min(fw, int(x1)))
    y0, y1 = max(0, min(fh, int(y0))), max(0, min(fh, int(y1)))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None

def _motion_fraction(mask, roi):
    if mask is None or roi is None:
        return 0.0
    x0, y0, x1, y1 = roi
    patch = mask[y0:y1, x0:x1]
    return cv2.countNonZero(patch) / float(patch.size) if patch.size else 0.0

def _reset_focus_window():
    return dict(
        frames=0, face_present_frames=0, forward_frames=0,
        face_present_time_sec=0.0, forward_time_sec=0.0,
        face_missing_time_sec=0.0, eyes_closed_time_sec=0.0,
        lookaway_events=0, current_lookaway_duration=0.0,
        lookaway_counted_for_current_streak=False,
        blink_count=0, blink_durations=[], long_eye_closure_count=0,
        motion_sum=0.0, motion_samples=0, motion_burst_count=0,
        current_absence_streak_sec=0.0, max_absence_streak_sec=0.0,
        current_forward_streak_sec=0.0, max_forward_streak_sec=0.0,
        face_area_ratio_sum=0.0, face_area_samples=0,
        looking_down_frames=0, near_face_motion_frames=0,
        desk_motion_frames=0, phone_candidate_frames=0,
        writing_candidate_frames=0,
        phone_time_sec=0.0, writing_time_sec=0.0,
        current_phone_streak_sec=0.0, current_writing_streak_sec=0.0,
        max_phone_streak_sec=0.0, max_writing_streak_sec=0.0,
    )

def _compute_focus_score(s: dict):
    score = (
        s["face_present_percent"]              * 0.20
        + s["looking_forward_percent"]         * 0.35
        + (s["longest_forward_streak_seconds"] / WINDOW_SECONDS) * 15.0
        + max(0.0, 100.0 - s["eye_closed_percent"]  * 2.0) * 0.10
        + max(0.0, 100.0 - min(s["head_motion_score"] * 8.0, 100.0)) * 0.10
        + max(0.0, 100.0 - s["lookaway_events"]      * 20.0) * 0.10
        + max(0.0, 100.0 - s["long_eye_closure_count"] * 25.0) * 0.05
        - s["phone_candidate_percent"] * 0.05
    )
    score = _clamp(score, 0.0, 100.0)
    label = "Focused" if score >= 75 else ("Semi-Focused" if score >= 50 else "Distracted")
    return round(score, 1), label

# ===========================================================================
# MediaPipe landmarks
# ===========================================================================

_MP_3D = np.array([
    [  0.0,    0.0,    0.0 ],
    [  0.0,  -63.6,  -12.5 ],
    [-43.3,   32.7,  -26.0 ],
    [ 43.3,   32.7,  -26.0 ],
    [-28.9,  -28.9,  -24.1 ],
    [ 28.9,  -28.9,  -24.1 ],
], dtype=np.float64)
_MP_IDS = [1, 152, 263, 33, 287, 57]

_LEFT_EYE_EAR  = [386, 374, 385, 380, 362, 263]
_RIGHT_EYE_EAR = [159, 145, 160, 144,  33, 133]
_LEFT_IRIS, _RIGHT_IRIS = 468, 473
_LEFT_EYE_CORNERS  = (362, 263)
_RIGHT_EYE_CORNERS = ( 33, 133)

# Landmarks for head tilt detection
_LM_FOREHEAD   = 10    # top of forehead
_LM_NOSE_BRIDGE = 6    # bridge of nose (between eyes)
_LM_NOSE_TIP    = 1    # tip of nose
_LM_CHIN        = 152  # bottom of chin
_LM_BETWEEN_EYES = 168 # center between eyes

def _ear(lm, ids, w, h):
    pts = [(lm[i].x * w, lm[i].y * h) for i in ids]
    A = math.dist(pts[0], pts[3])
    B = math.dist(pts[1], pts[2])
    C = math.dist(pts[4], pts[5])
    return (A + B) / (2.0 * C + 1e-6)

def _iris_offset(lm, iris_id, corners, w, h):
    ix, iy = lm[iris_id].x * w, lm[iris_id].y * h
    lx, rx = lm[corners[0]].x * w, lm[corners[1]].x * w
    ew = abs(rx - lx) + 1e-6
    cx = (lx + rx) / 2.0
    cy = (lm[corners[0]].y * h + lm[corners[1]].y * h) / 2.0
    return (ix - cx) / ew, (iy - cy) / ew

# ===========================================================================
# Head-pose + gaze + blink estimator
# ===========================================================================

class HeadPoseEstimator:
    def __init__(self):
        if not _LANDMARKER_PATH.exists():
            print("[INFO] Downloading face_landmarker.task (~3 MB) ...")
            urllib.request.urlretrieve(_LANDMARKER_URL, _LANDMARKER_PATH)
            print("[INFO] Download complete.")

        opts = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(_LANDMARKER_PATH)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._lm          = mp.tasks.vision.FaceLandmarker.create_from_options(opts)
        self._start_time  = time.perf_counter()
        self._ear_consec  = 0
        self.blink_count  = 0
        self._gaze_streak = 0

    def process(self, frame_bgr: np.ndarray) -> dict:
        h, w = frame_bgr.shape[:2]
        rgb  = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        ts_ms = int((time.perf_counter() - self._start_time) * 1000)
        result = self._lm.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
            ts_ms)

        out = dict(pose=None, gaze_away=False, gaze_down=False, gaze_dot=None,
                   ear=1.0, blink_now=False, head_down=False, landmarks=None)
        if not result.face_landmarks:
            return out

        lm = result.face_landmarks[0]
        out["landmarks"] = lm  # pass landmarks for face mesh drawing

        # ── Landmark-based head tilt detection (bypasses solvePnP) ─────
        head_down, lm_pitch = self._detect_head_tilt(lm)

        # Head pose
        img_pts = np.array(
            [(lm[i].x * w, lm[i].y * h) for i in _MP_IDS], dtype=np.float64)
        focal   = float(w)
        cam_mat = np.array([[focal,0,w/2],[0,focal,h/2],[0,0,1]], np.float64)
        ok, rvec, _ = cv2.solvePnP(
            _MP_3D, img_pts, cam_mat, np.zeros((4,1)),
            flags=cv2.SOLVEPNP_ITERATIVE)
        if ok:
            R, _ = cv2.Rodrigues(rvec)
            pitch = math.degrees(math.atan2(-R[2,0], math.sqrt(R[2,1]**2+R[2,2]**2)))
            yaw   = math.degrees(math.atan2(R[1,0], R[0,0]))
            roll  = math.degrees(math.atan2(R[2,1], R[2,2]))
            # ── Fix yaw wraparound: values near ±180° mean facing camera ──
            if abs(yaw) > 160.0:
                yaw = yaw - math.copysign(180.0, yaw)
                yaw = -yaw  # invert to get true deviation from forward
            if abs(pitch) > 160.0:
                pitch = pitch - math.copysign(180.0, pitch)
                pitch = -pitch
            if abs(roll) > 160.0:
                roll = roll - math.copysign(180.0, roll)
                roll = -roll
            # Override PnP pitch with landmark-based pitch if PnP seems wrong
            if head_down and pitch > -10.0:
                pitch = lm_pitch  # PnP failed, use landmark estimate
            out["pose"] = (yaw, pitch, roll)

        out["head_down"] = head_down

        # Nose + chin tracking (bridge → tip direction, chin position)
        try:
            bridge_x = lm[_LM_NOSE_BRIDGE].x * w
            bridge_y = lm[_LM_NOSE_BRIDGE].y * h
            tip_x    = lm[_LM_NOSE_TIP].x * w
            tip_y    = lm[_LM_NOSE_TIP].y * h
            chin_x   = lm[_LM_CHIN].x * w
            chin_y   = lm[_LM_CHIN].y * h
            # Face width for normalization (eye corner to eye corner)
            face_w   = abs(lm[263].x - lm[33].x) * w + 1e-6
            # Nose direction vector (normalized by face width)
            nose_dx  = (tip_x - bridge_x) / face_w   # +right, -left
            nose_dy  = (tip_y - bridge_y) / face_w   # +down (normal), shrinks when looking down
            # Chin-to-nose-tip distance (shrinks when chin tucks under)
            chin_dy  = (chin_y - tip_y) / face_w
            out["nose_dx"]  = nose_dx
            out["nose_dy"]  = nose_dy
            out["chin_dy"]  = chin_dy
            out["gaze_dot"] = (int(tip_x), int(tip_y))      # nose tip dot
            out["chin_dot"] = (int(chin_x), int(chin_y))    # chin dot
        except Exception:
            pass

        # Gaze (iris-based, kept for supplementary signal)
        try:
            ldx, ldy = _iris_offset(lm, _LEFT_IRIS,  _LEFT_EYE_CORNERS,  w, h)
            rdx, rdy = _iris_offset(lm, _RIGHT_IRIS, _RIGHT_EYE_CORNERS, w, h)
            dx, dy   = (ldx+rdx)/2, (ldy+rdy)/2
            if abs(dx) > GAZE_SIDE_THRESH or dy > GAZE_DOWN_THRESH:
                self._gaze_streak += 1
            else:
                self._gaze_streak = max(0, self._gaze_streak - 1)
            out["gaze_away"] = self._gaze_streak >= GAZE_CONFIRM_FRAMES
            out["gaze_down"] = dy > GAZE_DOWN_THRESH
        except Exception:
            pass

        # EAR / blink
        try:
            ear = (_ear(lm, _LEFT_EYE_EAR, w, h) + _ear(lm, _RIGHT_EYE_EAR, w, h)) / 2
            out["ear"] = ear
            if ear < EAR_BLINK_THRESH:
                self._ear_consec += 1
            else:
                if self._ear_consec >= EAR_CONSEC_FRAMES:
                    self.blink_count += 1
                    out["blink_now"] = True
                self._ear_consec = 0
        except Exception:
            pass

        return out

    def _detect_head_tilt(self, lm) -> tuple:
        """
        Detect downward head tilt using raw landmark geometry.
        Returns (is_tilted_down: bool, estimated_pitch: float).
        
        Uses three signals:
        1. Face vertical compression (chin-forehead span shrinks)
        2. Eye position ratio (eyes pushed toward chin)
        3. Nose foreshortening (nose bridge-to-tip distance shrinks)
        """
        # Key landmark y-coordinates (normalized 0-1, 0=top of image)
        forehead_y  = lm[_LM_FOREHEAD].y
        chin_y      = lm[_LM_CHIN].y
        between_y   = lm[_LM_BETWEEN_EYES].y
        nose_bridge_y = lm[_LM_NOSE_BRIDGE].y
        nose_tip_y  = lm[_LM_NOSE_TIP].y

        face_height = chin_y - forehead_y
        if face_height < 0.01:
            return True, -40.0  # degenerate: face is a sliver → very tilted

        # Signal 1: Where are the eyes relative to forehead-chin span?
        # Forward face: ~0.33-0.42 (eyes in upper third)
        # Tilted down:  >0.50 (eyes pushed toward chin, forehead dominates)
        eye_ratio = (between_y - forehead_y) / face_height

        # Signal 2: Nose foreshortening
        # Forward face: nose bridge-to-tip has noticeable vertical distance
        # Tilted down:  nose bridge and tip converge (nose viewed from above)
        nose_vertical = (nose_tip_y - nose_bridge_y) / face_height
        # Forward: ~0.25-0.35, Tilted down: <0.15

        # Signal 3: Chin is close to nose tip (chin tucks under)
        chin_to_nose = (chin_y - nose_tip_y) / face_height
        # Forward: ~0.3-0.4, Tilted down: <0.15

        # Scoring
        score = 0
        if eye_ratio > 0.50:
            score += 1
        if eye_ratio > 0.58:
            score += 1
        if nose_vertical < 0.18:
            score += 1
        if chin_to_nose < 0.18:
            score += 1

        is_down = score >= 2

        # Estimate a synthetic pitch in degrees from the eye ratio
        # eye_ratio 0.38 → 0°, eye_ratio 0.55 → -25°, eye_ratio 0.65 → -45°
        est_pitch = -max(0.0, (eye_ratio - 0.38) / 0.27 * 45.0)
        est_pitch = max(est_pitch, -60.0)  # clamp

        return is_down, est_pitch

    def close(self):
        self._lm.close()

# ===========================================================================
# Thumbs-up gesture detector (MediaPipe HandLandmarker)
# ===========================================================================

class ThumbsUpDetector:
    """Detects two simultaneous thumbs-up gestures to end the session."""

    def __init__(self):
        if not _HAND_LANDMARKER_PATH.exists():
            print("[INFO] Downloading hand_landmarker.task (~10 MB) ...")
            urllib.request.urlretrieve(_HAND_LANDMARKER_URL, _HAND_LANDMARKER_PATH)
            print("[INFO] Download complete.")

        opts = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(_HAND_LANDMARKER_PATH)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._hl = mp.tasks.vision.HandLandmarker.create_from_options(opts)
        self._start_time = time.perf_counter()
        self._thumbs_count = 0  # consecutive frames with 2 thumbs up
        self._CONFIRM_FRAMES = 6  # shorter hold improves reliability in normal webcam use

    def _is_thumb_up(self, hand_lm) -> bool:
        """Check if a single hand is doing thumbs-up.
        Thumb tip (4) above thumb IP (3) above thumb MCP (2),
        AND all four fingers curled (tip below PIP)."""
        thumb_tip = hand_lm[4]
        thumb_ip = hand_lm[3]
        thumb_mcp = hand_lm[2]
        thumb_cmc = hand_lm[1]
        wrist = hand_lm[0]

        # Thumb must be clearly raised above the hand.
        thumb_up = (
            thumb_tip.y < thumb_ip.y < thumb_mcp.y
            and thumb_tip.y < wrist.y - 0.05
            and thumb_tip.y < thumb_cmc.y
        )
        if not thumb_up:
            return False

        # Other fingers should not be extended upward like an open hand.
        curled_fingers = 0
        for tip, pip, mcp in [(8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)]:
            if hand_lm[tip].y > hand_lm[pip].y or hand_lm[tip].y > hand_lm[mcp].y:
                curled_fingers += 1

        if curled_fingers < 3:
            return False

        # Ignore sideways hands where the thumb is not actually vertical.
        thumb_vertical_gain = wrist.y - thumb_tip.y
        thumb_horizontal_drift = abs(thumb_tip.x - thumb_mcp.x)
        if thumb_vertical_gain <= thumb_horizontal_drift:
                return False
        return True

    def check(self, frame) -> bool:
        """Returns True when user shows two thumbs up for enough frames."""
        ts_ms = int((time.perf_counter() - self._start_time) * 1000)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._hl.detect_for_video(img, ts_ms)

        if len(result.hand_landmarks) >= 2:
            thumbs = sum(1 for h in result.hand_landmarks if self._is_thumb_up(h))
            if thumbs >= 2:
                self._thumbs_count += 1
            else:
                self._thumbs_count = 0
        else:
            self._thumbs_count = 0

        return self._thumbs_count >= self._CONFIRM_FRAMES

    def close(self):
        self._hl.close()

# ===========================================================================
# Phone detector
# ===========================================================================

class PhoneDetector:
    def __init__(self):
        self._model      = YOLO(YOLO_MODEL_NAME)
        self._model.fuse()
        self._skip       = 0
        self._last_found = False
        self._last_boxes = []
        # Persistence: keep phone "on" for several frames after YOLO detection
        self._persist_counter = 0
        # Gaze-down timer for phone inference without YOLO
        self._gaze_down_start = None
        self._pitch_down_frames = 0

    def phone_present(self, frame_bgr, frame_h):
        self._skip = (self._skip + 1) % YOLO_SKIP_FRAMES
        if self._skip != 0:
            # Still return True if persisting
            if self._persist_counter > 0:
                self._persist_counter -= 1
                return True, self._last_boxes
            return self._last_found, self._last_boxes
        results = self._model.predict(
            frame_bgr, classes=[PHONE_CLASS_ID],
            conf=PHONE_CONF_THRESH, verbose=False)
        boxes = []
        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) != PHONE_CLASS_ID:
                    continue
                x1,y1,x2,y2 = map(int, box.xyxy[0].tolist())
                # Accept phone detected anywhere in the lower 75% of frame
                if (y1+y2)/2 > frame_h * 0.25:
                    boxes.append([x1,y1,x2,y2])
        found = bool(boxes)
        if found:
            self._persist_counter = PHONE_PERSIST_FRAMES
        elif self._persist_counter > 0:
            self._persist_counter -= 1
            found = True  # still persisting
        self._last_found, self._last_boxes = found, boxes if boxes else self._last_boxes
        return found, self._last_boxes

    def infer_phone_from_pose(self, pose, gaze_away: bool, gaze_down: bool) -> bool:
        """
        Infer phone use from head-pose and gaze WITHOUT relying on YOLO.
        Returns True if the person is likely looking at their phone.
        """
        if pose is None:
            # Can't infer without pose data
            self._pitch_down_frames = 0
            self._gaze_down_start = None
            return False

        yaw, pitch, roll = pose
        now = time.perf_counter()

        # Strong pitch down → very likely phone (immediate)
        if pitch < PHONE_PITCH_STRONG and abs(yaw) < 30:
            self._pitch_down_frames += 1
            if self._pitch_down_frames >= 3:  # 3 frames minimum
                return True
        # Moderate pitch down + gaze down → likely phone (needs sustained)
        elif pitch < PHONE_PITCH_THRESH and abs(yaw) < 35:
            self._pitch_down_frames += 1
            if gaze_down or gaze_away:
                if self._gaze_down_start is None:
                    self._gaze_down_start = now
                elif now - self._gaze_down_start >= PHONE_GAZE_DOWN_MS:
                    return True
            else:
                self._gaze_down_start = None
            # Sustained pitch down even without gaze → phone
            if self._pitch_down_frames >= 10:
                return True
        else:
            self._pitch_down_frames = max(0, self._pitch_down_frames - 2)
            self._gaze_down_start = None

        return False

# ===========================================================================
# Haar-cascade face detector (for focus-window metrics)
# ===========================================================================

class HaarFaceDetector:
    def __init__(self):
        self._face_cas = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self._eye_cas  = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml")
        if self._face_cas.empty() or self._eye_cas.empty():
            raise RuntimeError("Could not load Haar cascade XML files.")

    def detect(self, gray: np.ndarray):
        """Returns (faces_array, eyes_visible) where faces_array is sorted largest-first."""
        faces = self._face_cas.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80,80))
        if len(faces) == 0:
            return [], False
        faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
        x, y, w, h = faces[0]
        roi_gray = gray[y:y+h//2, x:x+w]
        eyes = self._eye_cas.detectMultiScale(
            roi_gray, scaleFactor=1.1, minNeighbors=5, minSize=(20,20))
        return faces, len(eyes) >= 1

# ===========================================================================
# Focus-window tracker (camera_focus_tracker logic, class-ified)
# ===========================================================================

class FocusWindowTracker:
    """
    Accumulates per-frame metrics and emits a summary dict + CSV row every
    WINDOW_SECONDS seconds.
    """

    _BLANK_SUMMARY = dict(
        face_present=False, face_present_percent=0.0,
        face_missing_seconds=0.0, longest_face_missing_seconds=0.0,
        looking_forward_percent=0.0, longest_forward_streak_seconds=0.0,
        lookaway_events=0, blink_count=0, avg_blink_duration_sec=0.0,
        long_eye_closure_count=0, eye_closed_percent=0.0,
        head_motion_score=0.0, motion_burst_count=0,
        avg_face_area_percent=0.0, looking_down_percent=0.0,
        near_face_motion_percent=0.0, desk_motion_percent=0.0,
        phone_candidate_percent=0.0, writing_candidate_percent=0.0,
        longest_phone_streak_seconds=0.0, longest_writing_streak_seconds=0.0,
        likely_phone_use=False, likely_writing=False,
        camera_focus_score=0.0, camera_focus_label="N/A",
        attention_state="AWAY",
    )

    def __init__(self, csv_path: Path):
        self._window      = _reset_focus_window()
        self._window_start= time.perf_counter()
        self.last_summary = dict(self._BLANK_SUMMARY)

        # Eye/blink state (Haar-based)
        self._eyes_closed  = False
        self._blink_start  = None
        self._prev_face_cx = None
        self._prev_face_cy = None

        # CSV
        csv_exists = csv_path.exists()
        self._csv_file   = open(csv_path, mode="a", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        if not csv_exists:
            self._csv_writer.writerow(CSV_HEADERS)
            self._csv_file.flush()
        print(f"[INFO] CSV output  -> {csv_path}")

    def update(self, frame: np.ndarray, gray: np.ndarray,
               prev_gray, haar: HaarFaceDetector,
               attention_state: AttentionState, dt: float) -> tuple:
        """
        Call once per frame.
        Returns (updated_prev_gray, window_just_completed: bool).
        When window_just_completed, self.last_summary has been refreshed.
        """
        now     = time.perf_counter()
        fh, fw  = frame.shape[:2]
        w_obj   = self._window
        w_obj["frames"] += 1

        # ── Frame-diff motion mask ──────────────────────────────────────────
        motion_mask = None
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            _, motion_mask = cv2.threshold(
                diff, MOTION_DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

        # ── Desk ROI (always) ───────────────────────────────────────────────
        desk_roi  = _clip_rect(fw*0.15, fh*0.65, fw*0.85, fh, fw, fh)
        desk_frac = _motion_fraction(motion_mask, desk_roi)
        desk_motion_active = desk_frac >= DESK_MOTION_ACTIVE_THRESH
        if desk_motion_active:
            w_obj["desk_motion_frames"] += 1

        # ── Haar face detection ─────────────────────────────────────────────
        faces, eyes_visible = haar.detect(gray)
        face_present = len(faces) > 0

        looking_forward = looking_down = False
        near_face_motion_active = False
        phone_candidate = writing_candidate = False
        cx = cy = cx_norm = cy_norm = 0.0
        current_face_area_ratio = 0.0

        if face_present:
            w_obj["face_present_frames"] += 1
            w_obj["face_present_time_sec"] += dt

            x, y, wf, hf = faces[0]
            current_face_area_ratio = (wf * hf) / float(fw * fh)
            w_obj["face_area_ratio_sum"]  += current_face_area_ratio
            w_obj["face_area_samples"]    += 1

            cx, cy     = x + wf/2.0, y + hf/2.0
            cx_norm    = cx / fw
            cy_norm    = cy / fh

            centered     = CENTER_X_MIN <= cx_norm <= CENTER_X_MAX and CENTER_Y_MIN <= cy_norm <= CENTER_Y_MAX
            looking_forward = centered and current_face_area_ratio >= MIN_FACE_AREA_RATIO

            if looking_forward:
                w_obj["forward_frames"] += 1
                w_obj["forward_time_sec"] += dt
                w_obj["current_forward_streak_sec"] += dt
                w_obj["max_forward_streak_sec"] = max(
                    w_obj["max_forward_streak_sec"],
                    w_obj["current_forward_streak_sec"])
            else:
                w_obj["current_forward_streak_sec"] = 0.0

            # Head motion
            if self._prev_face_cx is not None:
                ddx = (cx - self._prev_face_cx) / fw
                ddy = (cy - self._prev_face_cy) / fh
                dist = math.sqrt(ddx*ddx + ddy*ddy)
                w_obj["motion_sum"]     += dist
                w_obj["motion_samples"] += 1
                if dist >= MOTION_BURST_THRESHOLD:
                    w_obj["motion_burst_count"] += 1
            self._prev_face_cx, self._prev_face_cy = cx, cy

            # Haar-based blink
            if looking_forward:
                if not eyes_visible:
                    if not self._eyes_closed:
                        self._eyes_closed = True
                        self._blink_start = now
                    w_obj["eyes_closed_time_sec"] += dt
                else:
                    if self._eyes_closed and self._blink_start:
                        dur = now - self._blink_start
                        if BLINK_MIN_DURATION <= dur <= BLINK_MAX_DURATION:
                            w_obj["blink_count"] += 1
                            w_obj["blink_durations"].append(dur)
                        if LONG_EYE_CLOSURE_MIN <= dur <= LONG_EYE_CLOSURE_MAX:
                            w_obj["long_eye_closure_count"] += 1
                    self._eyes_closed = False
                    self._blink_start = None
            else:
                self._eyes_closed = False
                self._blink_start = None

            w_obj["current_absence_streak_sec"] = 0.0

            # Looking-down proxy
            looking_down = (
                cy_norm >= LOOKING_DOWN_CENTER_Y_MIN
                or (not eyes_visible and cy_norm >= LOOKING_DOWN_NO_EYES_CENTER_Y_MIN)
            )
            if looking_down:
                w_obj["looking_down_frames"] += 1

            # Near-face motion ROI
            nf_roi  = _clip_rect(x-0.25*wf, y+0.45*hf, x+1.25*wf, y+1.80*hf, fw, fh)
            nf_frac = _motion_fraction(motion_mask, nf_roi)
            near_face_motion_active = nf_frac >= NEAR_FACE_MOTION_ACTIVE_THRESH
            if near_face_motion_active:
                w_obj["near_face_motion_frames"] += 1

            # Draw Haar face + eye boxes (lightly)
            cv2.rectangle(frame, (x,y), (x+wf,y+hf), (0,220,0), 1)
            if nf_roi:
                cv2.rectangle(frame, (nf_roi[0],nf_roi[1]), (nf_roi[2],nf_roi[3]), (0,180,180), 1)

        else:
            w_obj["face_missing_time_sec"]      += dt
            w_obj["current_absence_streak_sec"] += dt
            w_obj["max_absence_streak_sec"]      = max(
                w_obj["max_absence_streak_sec"],
                w_obj["current_absence_streak_sec"])
            w_obj["current_forward_streak_sec"]  = 0.0
            self._prev_face_cx = self._prev_face_cy = None
            self._eyes_closed  = False
            self._blink_start  = None

        if desk_roi:
            cv2.rectangle(frame, (desk_roi[0],desk_roi[1]), (desk_roi[2],desk_roi[3]), (180,180,0), 1)

        # Look-away events
        if not looking_forward:
            w_obj["current_lookaway_duration"] += dt
            if (not w_obj["lookaway_counted_for_current_streak"]
                    and w_obj["current_lookaway_duration"] >= LOOKAWAY_MIN_DURATION):
                w_obj["lookaway_events"] += 1
                w_obj["lookaway_counted_for_current_streak"] = True
        else:
            w_obj["current_lookaway_duration"] = 0.0
            w_obj["lookaway_counted_for_current_streak"] = False

        # Phone / writing candidate
        phone_candidate = looking_down and near_face_motion_active and not desk_motion_active
        writing_candidate = looking_down and desk_motion_active and not near_face_motion_active

        if phone_candidate:
            w_obj["phone_candidate_frames"]    += 1
            w_obj["phone_time_sec"]            += dt
            w_obj["current_phone_streak_sec"]  += dt
            w_obj["max_phone_streak_sec"]       = max(w_obj["max_phone_streak_sec"],
                                                      w_obj["current_phone_streak_sec"])
        else:
            w_obj["current_phone_streak_sec"] = 0.0

        if writing_candidate:
            w_obj["writing_candidate_frames"]    += 1
            w_obj["writing_time_sec"]            += dt
            w_obj["current_writing_streak_sec"]  += dt
            w_obj["max_writing_streak_sec"]       = max(w_obj["max_writing_streak_sec"],
                                                        w_obj["current_writing_streak_sec"])
        else:
            w_obj["current_writing_streak_sec"] = 0.0

        # ── Window completion ───────────────────────────────────────────────
        elapsed = now - self._window_start
        completed = elapsed >= WINDOW_SECONDS
        if completed:
            self.last_summary = self._finalise(attention_state)
            self._window       = _reset_focus_window()
            self._window_start = now

        return gray.copy(), completed

    def _finalise(self, attention_state: AttentionState) -> dict:
        w   = self._window
        tot = max(w["frames"], 1)
        fp  = w["face_present_frames"]

        face_present_pct   = round(100.0 * fp / tot, 1)
        avg_motion         = (w["motion_sum"] / w["motion_samples"]) if w["motion_samples"] else 0.0

        def _pct_of_fp(n):
            return round(100.0 * n / fp, 1) if fp else 0.0
        def _pct_of_tot(n):
            return round(100.0 * n / tot, 1)

        s = dict(
            face_present            = fp / tot >= 0.5,
            face_present_percent    = face_present_pct,
            face_missing_seconds    = round(w["face_missing_time_sec"], 2),
            longest_face_missing_seconds = round(w["max_absence_streak_sec"], 2),
            looking_forward_percent = _pct_of_fp(w["forward_frames"]),
            longest_forward_streak_seconds = round(w["max_forward_streak_sec"], 2),
            lookaway_events         = int(w["lookaway_events"]),
            blink_count             = int(w["blink_count"]),
            avg_blink_duration_sec  = round(sum(w["blink_durations"])/len(w["blink_durations"]), 3)
                                      if w["blink_durations"] else 0.0,
            long_eye_closure_count  = int(w["long_eye_closure_count"]),
            eye_closed_percent      = round(100.0 * w["eyes_closed_time_sec"] / w["forward_time_sec"], 1)
                                      if w["forward_time_sec"] else 0.0,
            head_motion_score       = round(avg_motion * 1000.0, 2),
            motion_burst_count      = int(w["motion_burst_count"]),
            avg_face_area_percent   = round(100.0 * w["face_area_ratio_sum"] / w["face_area_samples"], 2)
                                      if w["face_area_samples"] else 0.0,
            looking_down_percent    = _pct_of_fp(w["looking_down_frames"]),
            near_face_motion_percent= _pct_of_fp(w["near_face_motion_frames"]),
            desk_motion_percent     = _pct_of_tot(w["desk_motion_frames"]),
            phone_candidate_percent = _pct_of_tot(w["phone_candidate_frames"]),
            writing_candidate_percent = _pct_of_tot(w["writing_candidate_frames"]),
            longest_phone_streak_seconds   = round(w["max_phone_streak_sec"], 2),
            longest_writing_streak_seconds = round(w["max_writing_streak_sec"], 2),
            likely_phone_use  = w["max_phone_streak_sec"]   >= PHONE_STREAK_MIN_SECONDS,
            likely_writing    = w["max_writing_streak_sec"] >= WRITING_STREAK_MIN_SECONDS,
        )
        score, label = _compute_focus_score(s)
        s["camera_focus_score"]  = score
        s["camera_focus_label"]  = label
        s["attention_state"]     = attention_state.name

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._csv_writer.writerow([ts, WINDOW_SECONDS] + [s[k] for k in CSV_HEADERS[2:]])
        self._csv_file.flush()

        print(f"\n[WINDOW] focus={score} ({label})  state={attention_state.name}  "
              f"fwd={s['looking_forward_percent']}%  blinks={s['blink_count']}")
        return s

    def close(self):
        self._csv_file.close()

# ===========================================================================
# Rolling-vote smoother
# ===========================================================================

class AttentionSmoother:
    def __init__(self, size=BUFFER_SIZE):
        self._buf = collections.deque(maxlen=size)

    def update(self, state: AttentionState) -> AttentionState:
        self._buf.append(state)
        return collections.Counter(self._buf).most_common(1)[0][0]

# ===========================================================================
# Classification  (head-pose + gaze + focus score)
# ===========================================================================

def classify_frame(pose, gaze_away: bool, gaze_down: bool, head_down: bool,
                   nose_dx: float, nose_dy: float,
                   chin_dy: float) -> AttentionState:
    """
    Three-state classification:
      FOCUSED      – nose + chin at screen, eyes forward
      SEMI_FOCUSED – face visible but not perfectly aligned
      AWAY         – face gone or turned completely away
    """
    # No face at all → AWAY
    if pose is None:
        return AttentionState.AWAY

    yaw, pitch, roll = pose

    # ── AWAY: only when completely disengaged ─────────────────────────
    # Face turned very far sideways (can't see screen at all)
    if abs(nose_dx) > 0.40 and abs(yaw) > YAW_AWAY_BASE:
        return AttentionState.AWAY
    if abs(yaw) > YAW_AWAY_BASE + 15:
        return AttentionState.AWAY

    # ── FOCUSED: nose centered + chin forward + eyes straight ─────────
    # If the head tilt detector OR gaze drop detector triggers, they are NOT focused
    if head_down or gaze_down:
        return AttentionState.SEMI_FOCUSED

    # Ultra-loose thresholds to instantly snap to FOCUSED when vaguely forward
    nose_centered = abs(nose_dx) <= 0.22      # easily accepts slight left/right turns
    nose_forward  = nose_dy >= 0.22           # easily accepts slight up/down tilts
    chin_forward  = chin_dy >= 0.12           # easily accepts minor chin tucks
    eyes_forward  = not gaze_away
    face_forward  = abs(yaw) < YAW_AWAY_BASE * 1.0

    if nose_centered and nose_forward and chin_forward and eyes_forward and face_forward:
        return AttentionState.FOCUSED

    # ── SEMI_FOCUSED: everything else where face is visible ───────────
    # This catches: looking down, head tilted, slightly turned,
    # gaze away but face still in frame, etc.
    return AttentionState.SEMI_FOCUSED

# ===========================================================================
# Away alert
# ===========================================================================

class AwayAlert:
    def __init__(self):
        self._away_since  = None
        self._last_alert  = 0.0
        self._playing     = False

    def update(self, state: AttentionState):
        now = time.perf_counter()
        if state == AttentionState.AWAY:
            if self._away_since is None:
                self._away_since = now
            if (now - self._away_since  >= ALERT_AWAY_SEC
                    and now - self._last_alert >= ALERT_COOLDOWN_SEC
                    and not self._playing):
                self._fire(now)
        else:
            self._away_since = None

    def _fire(self, now):
        self._last_alert = now
        if _HAS_SOUND and ALERT_SOUND_PATH.exists():
            self._playing = True
            def _play():
                try:    _playsound(str(ALERT_SOUND_PATH))
                finally: self._playing = False
            threading.Thread(target=_play, daemon=True).start()
        else:
            print("\a[ALERT] Away too long!", flush=True)

# ===========================================================================
# Overlay renderer
# ===========================================================================

class Overlay:
    def __init__(self, max_tl=300):
        self._tl     = []
        self._max    = max_tl
        self._dwell  = {s.name: 0.0 for s in AttentionState}
        self._prev_t = time.perf_counter()

    def render(self, frame, state: AttentionState, pose, gaze_dot,
               blink_count, fps, away_sec, focus_summary: dict):
        h, w  = frame.shape[:2]
        now   = time.perf_counter()
        dt    = now - self._prev_t
        self._prev_t = now
        self._dwell[state.name] += dt

        style  = STATE_STYLE[state.name]
        colour = style["bgr"]
        label  = style["label"]

        # Banner
        flash = (state == AttentionState.AWAY
                 and away_sec >= ALERT_AWAY_SEC
                 and int(now * 2) % 2 == 0)
        banner_col = (0,0,255) if flash else colour
        ov = frame.copy()
        cv2.rectangle(ov, (0,0), (w, 64), banner_col, -1)
        cv2.addWeighted(ov, OVERLAY_ALPHA, frame, 1-OVERLAY_ALPHA, 0, frame)
        cv2.putText(frame, label, (14,44),
                    cv2.FONT_HERSHEY_DUPLEX, 1.15, (255,255,255), 2, cv2.LINE_AA)

        # Top-right: FPS, blinks, focus score
        fs    = focus_summary.get("camera_focus_score", 0.0)
        fl    = focus_summary.get("camera_focus_label", "N/A")
        info  = f"{fps:.0f}fps  blinks:{blink_count}  focus:{fs}({fl})"
        tw    = cv2.getTextSize(info, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)[0][0]
        cv2.putText(frame, info, (w-tw-8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255,255,255), 1, cv2.LINE_AA)

        if state == AttentionState.AWAY:
            atxt = f"away {away_sec:.1f}s"
            cv2.putText(frame, atxt, (w-tw-8, 46),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180,180,255), 1, cv2.LINE_AA)



        # Dwell timers (bottom-left)
        py = h - 14
        for s in reversed(list(AttentionState)):
            secs = self._dwell[s.name]
            m, sc = divmod(int(secs), 60)
            txt = f"{STATE_STYLE[s.name]['label']}: {m:02d}:{sc:02d}"
            cv2.putText(frame, txt, (10, py),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        STATE_STYLE[s.name]["bgr"], 1, cv2.LINE_AA)
            py -= 17

        # Head-pose (bottom-right)
        if pose is not None:
            yaw, pitch, roll = pose
            for i, txt in enumerate([f"Roll {roll:+.1f}",
                                      f"Pitch{pitch:+.1f}",
                                      f"Yaw  {yaw:+.1f}"]):
                cv2.putText(frame, txt, (w-108, h-10-i*17),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180,180,180), 1, cv2.LINE_AA)

        # NOTE: face mesh + dots are drawn in main loop now

        # Timeline
        self._tl.append(state.name)
        if len(self._tl) > self._max:
            self._tl = self._tl[-self._max:]
        tl_y  = h - TIMELINE_HEIGHT - 2
        seg_w = max(1, w // self._max)
        for i, sn in enumerate(self._tl):
            x0 = i * seg_w
            cv2.rectangle(frame, (x0, tl_y), (x0+seg_w-1, tl_y+TIMELINE_HEIGHT),
                          STATE_STYLE[sn]["bgr"], -1)

        return frame

# ===========================================================================
# Session JSON logger
# ===========================================================================

class SessionLogger:
    def __init__(self, sid: str, session_dir: Path):
        self._started   = datetime.now(timezone.utc)
        self._sid       = sid
        self._session_dir = session_dir
        self._transitions_path = session_dir / f"{sid}_transitions.json"
        self._snapshots_path   = session_dir / f"{sid}_snapshots.json"
        self._counts    = {s.name: 0 for s in AttentionState}
        self._frames    = 0
        self._fps_sum   = 0.0
        self._snapshots = []
        self._transitions       = []
        self._prev_state        = None
        self._state_entered_at  = time.perf_counter()
        self._last_snap         = self._state_entered_at
        self._t0                = self._state_entered_at

    def record(self, state, pose, phone, fps, ear, blinks, gaze_away,
               focus_summary: dict):
        now = time.perf_counter()
        self._frames  += 1
        self._counts[state.name] += 1
        self._fps_sum += fps

        if state != self._prev_state:
            if self._prev_state is not None:
                self._transitions.append(dict(
                    from_state=self._prev_state.name,
                    to=state.name,
                    at_sec=round(now-self._t0, 2),
                    duration_sec=round(now-self._state_entered_at, 2),
                ))
            self._prev_state      = state
            self._state_entered_at= now

        if SNAPSHOT_INTERVAL_SEC > 0 and now-self._last_snap >= SNAPSHOT_INTERVAL_SEC:
            self._snapshots.append(self._snap(state, pose, phone, ear,
                                               blinks, gaze_away, focus_summary, now))
            self._last_snap = now

    def _snap(self, state, pose, phone, ear, blinks, gaze_away, fs, t):
        return dict(
            timestamp      = datetime.now(timezone.utc).isoformat(),
            elapsed_sec    = round(t-self._t0, 2),
            state          = state.name,
            phone_detected = phone,
            gaze_away      = gaze_away,
            ear            = round(ear, 3),
            blink_count    = blinks,
            yaw            = round(pose[0],2) if pose else None,
            pitch          = round(pose[1],2) if pose else None,
            roll           = round(pose[2],2) if pose else None,
            focus_score    = fs.get("camera_focus_score"),
            focus_label    = fs.get("camera_focus_label"),
        )

    def close(self, state, pose, phone, ear, blinks, gaze_away, focus_summary):
        ended   = datetime.now(timezone.utc)
        dur     = (ended - self._started).total_seconds()
        avg_fps = self._fps_sum / max(self._frames, 1)
        self._snapshots.append(
            self._snap(state, pose, phone, ear, blinks, gaze_away,
                       focus_summary, time.perf_counter()))

        summary = {
            name: dict(
                frames=n,
                seconds=round(n/max(avg_fps,1e-9),1),
                percent=round(100*n/max(self._frames,1),1),
            ) for name, n in self._counts.items()
        }

        # Count distracted snapshots
        distracted_dir = self._session_dir / "distracted"
        distracted_count = len(list(distracted_dir.glob("*.png"))) if distracted_dir.exists() else 0

        # ── Transitions report ──────────────────────────────────────────
        transitions_report = dict(
            started_at    = self._started.isoformat(),
            ended_at      = ended.isoformat(),
            duration_sec  = round(dur, 2),
            total_frames  = self._frames,
            average_fps   = round(avg_fps, 2),
            total_blinks  = blinks,
            state_summary = summary,
            distracted_snap_count = distracted_count,
            transitions   = self._transitions,
        )
        with open(self._transitions_path, "w", encoding="utf-8") as f:
            json.dump(transitions_report, f, indent=2)
        print(f"[INFO] Transitions JSON -> {self._transitions_path}")

        # ── Snapshots report ────────────────────────────────────────────
        snapshots_report = dict(
            started_at  = self._started.isoformat(),
            session_id  = self._sid,
            snapshots   = self._snapshots,
        )
        with open(self._snapshots_path, "w", encoding="utf-8") as f:
            json.dump(snapshots_report, f, indent=2)
        print(f"[INFO] Snapshots JSON   -> {self._snapshots_path}")

        # Terminal summary
        print("\n-- Session Summary -----------------------------------------------")
        for name, info in summary.items():
            bar = "=" * int(info["percent"] / 4)
            print(f"  {name:<18} {info['percent']:5.1f}%  {bar}")
        m, s = divmod(int(dur), 60)
        print(f"  Blinks: {blinks}   Duration: {m}m {s}s")
        if distracted_count:
            print(f"  Distracted snapshots: {distracted_count}")
        print()

        return transitions_report, snapshots_report

# ===========================================================================
# Distracted screenshot capture
# ===========================================================================

def _save_distracted_snap(frame: np.ndarray, session_dir: Path,
                          pose=None, ear: float = 1.0,
                          focus_score: float = 0.0, focus_label: str = "N/A",
                          state_name: str = "AWAY", landmarks=None):
    """Save a technical HUD-annotated screenshot of a distraction event."""
    distracted_dir = session_dir / "distracted"
    distracted_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"{ts}_distracted.png"
    path = distracted_dir / filename

    img = frame.copy()
    h, w = img.shape[:2]

    # ── Dark tint overlay ──────────────────────────────────────────────────
    dark = img.copy()
    cv2.rectangle(dark, (0, 0), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(dark, 0.35, img, 0.65, 0, img)

    # ── Draw face mesh (prominent, glowing) ───────────────────────────────
    if landmarks is not None:
        lm = landmarks
        mesh_clr   = (255, 200, 0)    # bright cyan (BGR)
        glow_clr   = (200, 140, 0)    # dimmer glow layer
        dot_clr    = (255, 255, 0)    # bright cyan dots
        dot_glow   = (180, 120, 0)    # glow around dots

        def _contour(ids, color, thickness):
            pts = [(int(lm[i].x * w), int(lm[i].y * h)) for i in ids]
            for j in range(len(pts) - 1):
                cv2.line(img, pts[j], pts[j+1], color, thickness, cv2.LINE_AA)

        # Glow layer (thicker, dimmer)
        _contour(_FACE_OVAL,  glow_clr, 4)
        _contour(_LEFT_EYE,   glow_clr, 3)
        _contour(_RIGHT_EYE,  glow_clr, 3)
        _contour(_LIPS,       glow_clr, 3)
        _contour(_LEFT_BROW,  glow_clr, 3)
        _contour(_RIGHT_BROW, glow_clr, 3)
        _contour(_NOSE_BRIDGE, glow_clr, 3)

        # Sharp layer on top
        _contour(_FACE_OVAL,  mesh_clr, 2)
        _contour(_LEFT_EYE,   mesh_clr, 1)
        _contour(_RIGHT_EYE,  mesh_clr, 1)
        _contour(_LIPS,       mesh_clr, 1)
        _contour(_LEFT_BROW,  mesh_clr, 1)
        _contour(_RIGHT_BROW, mesh_clr, 1)
        _contour(_NOSE_BRIDGE, mesh_clr, 1)

        # All 478 landmark dots (glow + bright center)
        for i in range(len(lm)):
            px = int(lm[i].x * w)
            py = int(lm[i].y * h)
            cv2.circle(img, (px, py), 2, dot_glow, -1, cv2.LINE_AA)
            cv2.circle(img, (px, py), 1, dot_clr, -1, cv2.LINE_AA)

        # Larger accent dots on nose tip + chin
        nose_tip = (int(lm[1].x * w), int(lm[1].y * h))
        chin_pt  = (int(lm[152].x * w), int(lm[152].y * h))
        for pt in [nose_tip, chin_pt]:
            cv2.circle(img, pt, 5, (0, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, pt, 7, (0, 200, 200), 1, cv2.LINE_AA)

    # ── Scanline effect (subtle, after mesh) ──────────────────────────────
    scanline_overlay = img.copy()
    for y in range(0, h, 3):
        cv2.line(scanline_overlay, (0, y), (w, y), (0, 0, 0), 1)
    cv2.addWeighted(scanline_overlay, 0.3, img, 0.7, 0, img)

    # ── Corner brackets (tech border) ──────────────────────────────────────
    brk = 40  # bracket length
    t = 2     # thickness
    clr = (0, 0, 255)  # red
    # Top-left
    cv2.line(img, (4, 4), (4+brk, 4), clr, t, cv2.LINE_AA)
    cv2.line(img, (4, 4), (4, 4+brk), clr, t, cv2.LINE_AA)
    # Top-right
    cv2.line(img, (w-5, 4), (w-5-brk, 4), clr, t, cv2.LINE_AA)
    cv2.line(img, (w-5, 4), (w-5, 4+brk), clr, t, cv2.LINE_AA)
    # Bottom-left
    cv2.line(img, (4, h-5), (4+brk, h-5), clr, t, cv2.LINE_AA)
    cv2.line(img, (4, h-5), (4, h-5-brk), clr, t, cv2.LINE_AA)
    # Bottom-right
    cv2.line(img, (w-5, h-5), (w-5-brk, h-5), clr, t, cv2.LINE_AA)
    cv2.line(img, (w-5, h-5), (w-5, h-5-brk), clr, t, cv2.LINE_AA)

    # ── Top banner ─────────────────────────────────────────────────────────
    banner = img.copy()
    cv2.rectangle(banner, (0, 0), (w, 58), (0, 0, 180), -1)
    cv2.addWeighted(banner, 0.55, img, 0.45, 0, img)
    # Flashing-style ▲ DISTRACTION DETECTED
    cv2.putText(img, "\xe2\x96\xb2 DISTRACTION DETECTED".encode().decode('utf-8', errors='replace'),
                (14, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (60, 60, 255), 2, cv2.LINE_AA)
    time_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(img, time_str, (14, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 255), 1, cv2.LINE_AA)
    # State badge (top-right)
    state_txt = f"STATE: {state_name}"
    tw = cv2.getTextSize(state_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
    cv2.putText(img, state_txt, (w - tw - 14, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 255), 1, cv2.LINE_AA)

    # ── Bottom telemetry bar ───────────────────────────────────────────────
    telem_y = h - 60
    telem = img.copy()
    cv2.rectangle(telem, (0, telem_y), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(telem, 0.6, img, 0.4, 0, img)

    # Pose data
    if pose is not None:
        yaw, pitch, roll = pose
        pose_txt = f"YAW {yaw:+6.1f}  PITCH {pitch:+6.1f}  ROLL {roll:+6.1f}"
    else:
        pose_txt = "YAW  ---    PITCH  ---    ROLL  ---"
    cv2.putText(img, pose_txt, (14, telem_y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 200, 200), 1, cv2.LINE_AA)

    # EAR + focus score
    ear_txt = f"EAR {ear:.3f}"
    cv2.putText(img, ear_txt, (14, telem_y + 46),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 200, 200), 1, cv2.LINE_AA)

    # Focus score bar
    bar_x = 200
    bar_w = 180
    bar_y = telem_y + 36
    bar_h = 14
    cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
    fill_w = int(bar_w * min(focus_score, 100) / 100)
    bar_clr = (0, 80, 255) if focus_score < 50 else (0, 200, 255)
    cv2.rectangle(img, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), bar_clr, -1)
    cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (100, 100, 100), 1)
    score_txt = f"FOCUS {focus_score:.0f}  [{focus_label}]"
    cv2.putText(img, score_txt, (bar_x + bar_w + 10, bar_y + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 220), 1, cv2.LINE_AA)

    # ── Crosshair at center ────────────────────────────────────────────────
    cx, cy = w // 2, h // 2
    cv2.line(img, (cx - 20, cy), (cx - 8, cy), (0, 0, 200), 1, cv2.LINE_AA)
    cv2.line(img, (cx + 8, cy), (cx + 20, cy), (0, 0, 200), 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy - 20), (cx, cy - 8), (0, 0, 200), 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy + 8), (cx, cy + 20), (0, 0, 200), 1, cv2.LINE_AA)

    cv2.imwrite(str(path), img)
    print(f"[SNAP] Distracted screenshot -> {path}")

# ===========================================================================
# Summary chart
# ===========================================================================

def _save_chart(transitions_report: dict, snapshots_report: dict, path: Path):
    if not _HAS_MPL:
        print("[WARN] matplotlib not installed – skipping chart.")
        return

    BG        = "#f6f7f9"
    PANEL_BG  = "#ffffff"
    GRID_CLR  = "#e2e4ea"
    SPINE_CLR = "#d0d3db"
    TXT       = "#1a1a2e"
    TXT_DIM   = "#6b7088"

    colours = {s: STATE_STYLE[s]["hex"] for s in STATE_STYLE}
    summary = transitions_report["state_summary"]
    snaps   = snapshots_report["snapshots"]
    dur     = max(transitions_report["duration_sec"], 1.0)
    total_percent = sum(v["percent"] for v in summary.values())
    if total_percent <= 0 or not snaps:
        print("[WARN] No camera frames captured - skipping chart.")
        return

    # Layout: 2 rows.  Row 1 = donut (left) + focus score (right).
    #                  Row 2 = full-width timeline bar.
    fig = plt.figure(figsize=(14, 7), facecolor=BG)

    m_dur, s_dur = divmod(int(dur), 60)
    fig.suptitle(
        f"Attention Session  ·  {transitions_report['started_at'][:19].replace('T',' ')} UTC"
        f"  ·  {m_dur}m {s_dur}s",
        color=TXT, fontsize=14, fontweight="bold", y=0.97)

    gs = fig.add_gridspec(2, 2, height_ratios=[3, 1],
                          hspace=0.35, wspace=0.30,
                          left=0.06, right=0.96, top=0.90, bottom=0.08)

    def _style_ax(ax, xlabel="", ylabel=""):
        ax.set_facecolor(PANEL_BG)
        for sp in ax.spines.values():
            sp.set_color(SPINE_CLR)
        ax.tick_params(colors=TXT_DIM, labelsize=8)
        ax.grid(True, color=GRID_CLR, linewidth=0.5, alpha=0.7)
        if xlabel:
            ax.set_xlabel(xlabel, color=TXT_DIM, fontsize=9)
        if ylabel:
            ax.set_ylabel(ylabel, color=TXT_DIM, fontsize=9)

    # ── 1. State Distribution (donut) – top left ──────────────────────────
    ax1 = fig.add_subplot(gs[0, 0], facecolor=BG)
    sizes = [v["percent"] for v in summary.values()]
    clrs  = [colours[k]   for k in summary]
    labels_pct = [f"{k}\n{v['percent']:.1f}%" for k, v in summary.items()]
    wedges, texts = ax1.pie(
        sizes, colors=clrs, startangle=90, pctdistance=0.82,
        wedgeprops={"edgecolor": BG, "linewidth": 3, "width": 0.36})
    centre_circle = plt.Circle((0, 0), 0.56, fc=BG)
    ax1.add_artist(centre_circle)
    ax1.text(0, 0.08, f"{m_dur}m {s_dur}s", ha="center", va="center",
             color=TXT, fontsize=16, fontweight="bold")
    ax1.text(0, -0.14, "total", ha="center", va="center",
             color=TXT_DIM, fontsize=9)
    ax1.legend(wedges, labels_pct, loc="lower center",
               fontsize=8, facecolor=PANEL_BG, edgecolor=SPINE_CLR,
               labelcolor=TXT, framealpha=1.0, ncol=3,
               columnspacing=1.2, handlelength=1.2, borderpad=0.6)
    ax1.set_title("State Distribution", color=TXT, fontsize=12,
                  fontweight="bold", pad=12)

    # ── 2. Focus Score – top right ────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1], facecolor=PANEL_BG)
    focus_pts = [(s["elapsed_sec"], s.get("focus_score"))
                 for s in snaps if s.get("focus_score") is not None]
    if focus_pts:
        ts_f, fs_vals = zip(*focus_pts)
        ax2.axhspan(75, 100, color="#28b94018")
        ax2.axhspan(50, 75,  color="#f0c80018")
        ax2.axhspan(0,  50,  color="#e01e1e12")
        ax2.axhline(75, color="#28b940", linewidth=0.6, linestyle=":", alpha=0.6)
        ax2.axhline(50, color="#e01e1e", linewidth=0.6, linestyle=":", alpha=0.6)
        ax2.fill_between(ts_f, fs_vals, alpha=0.18, color="#7c4dff")
        ax2.plot(ts_f, fs_vals, color="#7c4dff", linewidth=2, marker="o",
                 markersize=4, markerfacecolor="#5e35b1", markeredgecolor="#7c4dff",
                 markeredgewidth=0.8)
        ax2.set_xlim(0, dur)
        ax2.set_ylim(0, 105)
    _style_ax(ax2, xlabel="Elapsed (s)", ylabel="Score")
    ax2.set_title("Focus Score", color=TXT, fontsize=12,
                  fontweight="bold", pad=12)

    # ── 3. Timeline – full width bottom ───────────────────────────────────
    ax3 = fig.add_subplot(gs[1, :], facecolor=PANEL_BG)
    if len(snaps) >= 2:
        times  = [s["elapsed_sec"] for s in snaps]
        states = [s["state"]       for s in snaps]
        for i in range(len(snaps)-1):
            ax3.barh(0, times[i+1]-times[i], left=times[i],
                     color=colours.get(states[i], "#888"),
                     height=0.6, align="center", edgecolor=PANEL_BG,
                     linewidth=0.4)
        ax3.set_xlim(0, dur)
    ax3.set_yticks([])
    ax3.set_ylim(-0.5, 0.5)
    patches = [mpatches.Patch(color=colours[k], label=k) for k in colours]
    ax3.legend(handles=patches, loc="upper right", fontsize=8,
               facecolor=PANEL_BG, edgecolor=SPINE_CLR,
               labelcolor=TXT, framealpha=1.0, ncol=3)
    for sp in ax3.spines.values():
        sp.set_color(SPINE_CLR)
    ax3.tick_params(colors=TXT_DIM, labelsize=8)
    ax3.set_xlabel("Elapsed (s)", color=TXT_DIM, fontsize=9)
    ax3.set_title("Attention Timeline", color=TXT, fontsize=12,
                  fontweight="bold", pad=10)

    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[INFO] Chart saved -> {path}")

# ===========================================================================
# Main loop
# ===========================================================================

def _next_session_dir() -> Path:
    """Create and return the next session folder: Data/Session N - mm-dd-yy"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = [d.name for d in DATA_DIR.iterdir() if d.is_dir() and d.name.startswith("Session ")]
    nums = []
    for name in existing:
        m = re.match(r"Session (\d+)", name)
        if m:
            nums.append(int(m.group(1)))
    next_num = max(nums, default=0) + 1
    date_str = datetime.now().strftime("%m-%d-%y")
    folder_name = f"Session {next_num} - {date_str}"
    session_dir = DATA_DIR / folder_name
    session_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Session folder -> {session_dir}")
    return session_dir


def _request_stop(_signum=None, _frame=None):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print("[INFO] External stop requested. Ending session gracefully.")


def _mark_ready():
    if not READY_FILE_PATH:
        return
    try:
        Path(READY_FILE_PATH).write_text("ready\n", encoding="utf-8")
    except OSError:
        pass


def main():
    global STOP_REQUESTED
    STOP_REQUESTED = False
    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_stop)

    session_dir = _next_session_dir()
    sid = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    print("[INFO] Initialising models ...")
    pose_est  = HeadPoseEstimator()
    phone_det = PhoneDetector()
    haar      = HaarFaceDetector()
    smoother  = AttentionSmoother()
    overlay   = Overlay()
    logger    = SessionLogger(sid, session_dir)
    alert     = AwayAlert()
    focus_tracker = FocusWindowTracker(session_dir / f"{sid}_windows.csv")
    thumbs_det = ThumbsUpDetector()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Cannot open webcam (index 0).")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    print("[INFO] Press  q  or  Esc  to quit.")
    _mark_ready()

    prev       = time.perf_counter()
    prev_gray  = None
    fps        = 0.0
    away_since = None
    _last_distract_snap_t = 0.0

    last_state  = AttentionState.AWAY
    last_pose   = None
    last_phone  = False
    last_ear    = 1.0
    last_gaze   = False

    try:
        while True:
            if STOP_REQUESTED:
                break

            ok, frame = cap.read()
            if not ok:
                continue

            frame = cv2.flip(frame, 1)
            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            fh    = frame.shape[0]

            # 1. MediaPipe: pose + gaze + EAR blink
            face_data  = pose_est.process(frame)
            pose       = face_data["pose"]
            gaze_away  = face_data["gaze_away"]
            gaze_dot   = face_data["gaze_dot"]
            ear        = face_data["ear"]

            # 2. Extract nose/chin signals
            head_down = face_data.get("head_down", False)
            gaze_down = face_data.get("gaze_down", False)
            nose_dx   = face_data.get("nose_dx", 0.0)
            nose_dy   = face_data.get("nose_dy", 0.0)
            chin_dy   = face_data.get("chin_dy", 0.5)

            # 2b. Phone detection (YOLO + pose inference)
            phone_yolo, phone_boxes = phone_det.phone_present(frame, fh)
            phone_pose = phone_det.infer_phone_from_pose(pose, gaze_away, gaze_down)
            phone_active = phone_yolo or phone_pose

            # 3. Classification (nose + chin must face screen)
            raw    = classify_frame(pose, gaze_away, gaze_down, head_down,
                                    nose_dx, nose_dy, chin_dy)
            smooth = smoother.update(raw)

            # Override: chin dropped below frame → SEMI_FOCUSED
            chin_dot = face_data.get("chin_dot")
            if chin_dot and chin_dot[1] >= frame.shape[0] - 5:
                smooth = AttentionState.SEMI_FOCUSED
            elif chin_dot is None and pose is not None:
                # Face detected but chin off-screen
                smooth = AttentionState.SEMI_FOCUSED

            # Check for two thumbs up → end session
            if thumbs_det.check(frame):
                print("[INFO] Two thumbs up detected! Ending session.")
                break

            # 4. Away timer
            now = time.perf_counter()
            if smooth == AttentionState.AWAY:
                if away_since is None: away_since = now
                away_sec = now - away_since
            else:
                away_since = None
                away_sec   = 0.0

            # 5. Alert
            alert.update(smooth)

            # 6. FPS
            fps  = 0.9 * fps + 0.1 / max(now - prev, 1e-9)
            prev = now

            dt = 1.0 / max(fps, 1.0)

            # 7. Focus-window tracker (Haar + motion; may emit a CSV row)
            prev_gray, _ = focus_tracker.update(
                frame, gray, prev_gray, haar, smooth, dt)

            # 7b. Distracted screenshot (computed here, captured after face mesh)
            is_distracted = (
                smooth == AttentionState.AWAY
                or (smooth == AttentionState.SEMI_FOCUSED
                    and focus_tracker.last_summary.get("camera_focus_score", 100)
                        < FOCUS_DISTRACTED_THRESHOLD)
            )
            _snap_distracted = (
                is_distracted
                and (now - _last_distract_snap_t >= DISTRACT_SNAP_COOLDOWN_SEC)
            )

            # 8. Log
            logger.record(smooth, pose, phone_active, fps,
                          ear, pose_est.blink_count, gaze_away,
                          focus_tracker.last_summary)
            last_state  = smooth
            last_pose   = pose
            last_phone  = phone_active
            last_ear    = ear
            last_gaze   = gaze_away

            # 9. Draw face mesh + nose/chin dots
            lm = face_data.get("landmarks")
            if lm is not None:
                h_fr, w_fr = frame.shape[:2]

                # Color by state
                if smooth == AttentionState.FOCUSED:
                    mesh_color = (0, 255, 100)   # green
                    dot_color  = (0, 200, 80)
                elif smooth == AttentionState.SEMI_FOCUSED:
                    mesh_color = (0, 220, 255)   # yellow
                    dot_color  = (0, 180, 220)
                else:
                    mesh_color = (80, 80, 200)   # red
                    dot_color  = (60, 60, 160)

                # Draw ALL 478 landmarks as small dots
                for i in range(len(lm)):
                    px = int(lm[i].x * w_fr)
                    py = int(lm[i].y * h_fr)
                    cv2.circle(frame, (px, py), 1, dot_color, -1)

                # Draw contour lines on top
                def _draw_contour(ids, color, thickness=1):
                    pts = [(int(lm[i].x * w_fr), int(lm[i].y * h_fr)) for i in ids]
                    for j in range(len(pts) - 1):
                        cv2.line(frame, pts[j], pts[j+1], color, thickness, cv2.LINE_AA)

                _draw_contour(_FACE_OVAL, mesh_color, 2)
                _draw_contour(_LEFT_EYE, mesh_color, 1)
                _draw_contour(_RIGHT_EYE, mesh_color, 1)
                _draw_contour(_LIPS, mesh_color, 1)
                _draw_contour(_LEFT_BROW, mesh_color, 1)
                _draw_contour(_RIGHT_BROW, mesh_color, 1)
                _draw_contour(_NOSE_BRIDGE, mesh_color, 1)

            # Two larger yellow dots: nose tip + chin
            nose_dot = face_data.get("gaze_dot")
            chin_dot = face_data.get("chin_dot")
            if nose_dot:
                cv2.circle(frame, nose_dot, 6, (0,255,255), -1)
                cv2.circle(frame, nose_dot, 8, (0,200,200), 1)
            if chin_dot:
                cv2.circle(frame, chin_dot, 6, (0,255,255), -1)
                cv2.circle(frame, chin_dot, 8, (0,200,200), 1)

            # 9b. Capture distracted screenshot (after face mesh, before overlay)
            if _snap_distracted:
                fs = focus_tracker.last_summary
                _save_distracted_snap(
                    frame, session_dir,
                    pose=pose, ear=ear,
                    focus_score=fs.get("camera_focus_score", 0.0),
                    focus_label=fs.get("camera_focus_label", "N/A"),
                    state_name=smooth.name,
                    landmarks=face_data.get("landmarks"))
                _last_distract_snap_t = now

            # 10. Overlay
            frame = overlay.render(frame, smooth, pose, gaze_dot,
                                   pose_est.blink_count, fps, away_sec,
                                   focus_tracker.last_summary)

            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        pose_est.close()
        thumbs_det.close()
        focus_tracker.close()
        trans_report, snaps_report = logger.close(
            last_state, last_pose, last_phone,
            last_ear, pose_est.blink_count, last_gaze,
            focus_tracker.last_summary)
        _save_chart(trans_report, snaps_report,
                    session_dir / f"{sid}_summary.png")
        print("[INFO] Done.")


if __name__ == "__main__":
    main()
