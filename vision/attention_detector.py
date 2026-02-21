#!/usr/bin/env python3
"""
Attention Detector - Eye contact detection for Cass wake trigger.

Uses webcam + MediaPipe Face Landmarker to detect when someone is looking
at the camera. Sustained eye contact triggers a wake event.

This is a desktop prototype - will be ported to Pi Camera later.
"""

import time
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# MediaPipe Tasks API (0.10.x+)
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("MediaPipe not available. Install with: pip install mediapipe")


class AttentionState(Enum):
    """Current attention state."""
    NO_FACE = "no_face"
    FACE_DETECTED = "face_detected"
    LOOKING_AWAY = "looking_away"
    LOOKING_AT_CAMERA = "looking_at_camera"
    ENGAGED = "engaged"  # Sustained eye contact


@dataclass
class GazeResult:
    """Result of gaze estimation."""
    state: AttentionState
    confidence: float
    face_center: Optional[tuple[int, int]] = None
    left_eye: Optional[tuple[int, int]] = None
    right_eye: Optional[tuple[int, int]] = None
    gaze_direction: Optional[tuple[float, float]] = None  # (x, y) normalized
    attention_duration: float = 0.0  # Seconds of sustained attention


class AttentionDetector:
    """
    Detects eye contact using MediaPipe Face Landmarker.

    Uses iris landmarks to estimate gaze direction and determine
    if the person is looking at the camera.
    """

    # Model download URL
    MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    MODEL_PATH = Path(__file__).parent / "face_landmarker.task"

    def __init__(
        self,
        engagement_threshold: float = 1.5,  # Seconds to trigger engagement
        gaze_threshold: float = 0.15,  # How centered eyes need to be
        smoothing_frames: int = 5,  # Frames to average for stability
    ):
        self.engagement_threshold = engagement_threshold
        self.gaze_threshold = gaze_threshold
        self.smoothing_frames = smoothing_frames

        # State tracking
        self.attention_start: Optional[float] = None
        self.gaze_history: list[tuple[float, float]] = []

        # MediaPipe setup
        self.landmarker = None
        if MEDIAPIPE_AVAILABLE:
            self._init_landmarker()

    def _download_model(self):
        """Download the face landmarker model if not present."""
        if self.MODEL_PATH.exists():
            return

        print(f"Downloading face landmarker model...")
        urllib.request.urlretrieve(self.MODEL_URL, self.MODEL_PATH)
        print(f"Model saved to {self.MODEL_PATH}")

    def _init_landmarker(self):
        """Initialize the MediaPipe Face Landmarker."""
        self._download_model()

        base_options = mp_tasks.BaseOptions(model_asset_path=str(self.MODEL_PATH))
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)

    def _get_landmark_point(self, landmarks, index, w, h):
        """Get a landmark as (x, y) pixel coordinates."""
        lm = landmarks[index]
        return (int(lm.x * w), int(lm.y * h))

    def _get_iris_center(self, landmarks, indices, w, h):
        """Calculate center of iris from landmark indices."""
        points = [self._get_landmark_point(landmarks, i, w, h) for i in indices]
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        return (cx, cy)

    def _get_eye_bounds(self, landmarks, indices, w, h):
        """Get bounding box of eye from landmark indices."""
        points = [self._get_landmark_point(landmarks, i, w, h) for i in indices]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return (min(xs), min(ys), max(xs), max(ys))

    def _estimate_gaze(self, landmarks, w, h) -> tuple[float, float]:
        """
        Estimate gaze direction from iris position relative to eye bounds.

        Returns (x, y) where (0, 0) is looking directly at camera.
        Positive x = looking right, positive y = looking down.
        """
        # MediaPipe landmark indices (same as solutions API)
        LEFT_IRIS = [468, 469, 470, 471, 472]
        RIGHT_IRIS = [473, 474, 475, 476, 477]
        LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
        RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]

        # Get iris centers
        left_iris = self._get_iris_center(landmarks, LEFT_IRIS, w, h)
        right_iris = self._get_iris_center(landmarks, RIGHT_IRIS, w, h)

        # Get eye bounds
        left_bounds = self._get_eye_bounds(landmarks, LEFT_EYE, w, h)
        right_bounds = self._get_eye_bounds(landmarks, RIGHT_EYE, w, h)

        # Calculate iris position relative to eye bounds (0-1)
        def relative_position(iris, bounds):
            x_min, y_min, x_max, y_max = bounds
            eye_w = x_max - x_min
            eye_h = y_max - y_min
            if eye_w == 0 or eye_h == 0:
                return (0.5, 0.5)
            rel_x = (iris[0] - x_min) / eye_w
            rel_y = (iris[1] - y_min) / eye_h
            return (rel_x, rel_y)

        left_rel = relative_position(left_iris, left_bounds)
        right_rel = relative_position(right_iris, right_bounds)

        # Average both eyes and center at 0
        gaze_x = ((left_rel[0] + right_rel[0]) / 2) - 0.5
        gaze_y = ((left_rel[1] + right_rel[1]) / 2) - 0.5

        return (gaze_x, gaze_y)

    def _smooth_gaze(self, gaze: tuple[float, float]) -> tuple[float, float]:
        """Apply temporal smoothing to gaze estimate."""
        self.gaze_history.append(gaze)
        if len(self.gaze_history) > self.smoothing_frames:
            self.gaze_history.pop(0)

        avg_x = sum(g[0] for g in self.gaze_history) / len(self.gaze_history)
        avg_y = sum(g[1] for g in self.gaze_history) / len(self.gaze_history)
        return (avg_x, avg_y)

    def process_frame(self, frame: np.ndarray) -> GazeResult:
        """
        Process a video frame and return gaze result.

        Args:
            frame: BGR image from OpenCV

        Returns:
            GazeResult with attention state and details
        """
        if not MEDIAPIPE_AVAILABLE or self.landmarker is None:
            return GazeResult(state=AttentionState.NO_FACE, confidence=0.0)

        h, w = frame.shape[:2]

        # Convert to RGB and create MediaPipe Image
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # Run face landmarker
        result = self.landmarker.detect(mp_image)

        if not result.face_landmarks:
            self.attention_start = None
            self.gaze_history.clear()
            return GazeResult(state=AttentionState.NO_FACE, confidence=0.0)

        landmarks = result.face_landmarks[0]

        # Get face center (nose tip - index 1)
        face_center = self._get_landmark_point(landmarks, 1, w, h)

        # Get eye centers for visualization (iris centers)
        left_eye = self._get_iris_center(landmarks, [468, 469, 470, 471, 472], w, h)
        right_eye = self._get_iris_center(landmarks, [473, 474, 475, 476, 477], w, h)

        # Estimate gaze
        raw_gaze = self._estimate_gaze(landmarks, w, h)
        gaze = self._smooth_gaze(raw_gaze)

        # Determine if looking at camera
        gaze_magnitude = (gaze[0]**2 + gaze[1]**2) ** 0.5
        looking_at_camera = gaze_magnitude < self.gaze_threshold

        # Calculate confidence (inverse of gaze magnitude, clamped)
        confidence = max(0.0, min(1.0, 1.0 - (gaze_magnitude / self.gaze_threshold)))

        # Track attention duration
        now = time.time()
        if looking_at_camera:
            if self.attention_start is None:
                self.attention_start = now
            attention_duration = now - self.attention_start

            if attention_duration >= self.engagement_threshold:
                state = AttentionState.ENGAGED
            else:
                state = AttentionState.LOOKING_AT_CAMERA
        else:
            self.attention_start = None
            attention_duration = 0.0
            state = AttentionState.LOOKING_AWAY

        return GazeResult(
            state=state,
            confidence=confidence,
            face_center=face_center,
            left_eye=(int(left_eye[0]), int(left_eye[1])),
            right_eye=(int(right_eye[0]), int(right_eye[1])),
            gaze_direction=gaze,
            attention_duration=attention_duration,
        )

    def draw_debug(self, frame: np.ndarray, result: GazeResult) -> np.ndarray:
        """Draw debug visualization on frame."""
        debug = frame.copy()

        # Colors based on state
        colors = {
            AttentionState.NO_FACE: (128, 128, 128),
            AttentionState.FACE_DETECTED: (255, 255, 0),
            AttentionState.LOOKING_AWAY: (0, 0, 255),
            AttentionState.LOOKING_AT_CAMERA: (0, 255, 255),
            AttentionState.ENGAGED: (0, 255, 0),
        }
        color = colors.get(result.state, (255, 255, 255))

        # Draw eye positions
        if result.left_eye:
            cv2.circle(debug, result.left_eye, 5, color, -1)
        if result.right_eye:
            cv2.circle(debug, result.right_eye, 5, color, -1)

        # Draw gaze direction indicator
        if result.gaze_direction and result.face_center:
            gx, gy = result.gaze_direction
            cx, cy = result.face_center
            # Scale for visualization
            end_x = int(cx + gx * 100)
            end_y = int(cy + gy * 100)
            cv2.arrowedLine(debug, result.face_center, (end_x, end_y), color, 2)

        # Draw state text
        state_text = f"{result.state.value} ({result.confidence:.2f})"
        cv2.putText(debug, state_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Draw attention progress bar
        if result.state in [AttentionState.LOOKING_AT_CAMERA, AttentionState.ENGAGED]:
            progress = min(1.0, result.attention_duration / self.engagement_threshold)
            bar_w = int(200 * progress)
            cv2.rectangle(debug, (10, 50), (10 + bar_w, 70), color, -1)
            cv2.rectangle(debug, (10, 50), (210, 70), color, 2)

            time_text = f"{result.attention_duration:.1f}s / {self.engagement_threshold}s"
            cv2.putText(debug, time_text, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        return debug


def main():
    """Run attention detector on webcam feed."""
    print("Starting Attention Detector...")
    print("Press 'q' to quit, 's' to save screenshot")
    print()

    detector = AttentionDetector(
        engagement_threshold=1.5,  # 1.5 seconds for wake
        gaze_threshold=0.12,  # Fairly strict center requirement
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam")
        return

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    engagement_callback_fired = False

    print("Webcam ready. Look at the camera to test eye contact detection.")
    print()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Mirror for more natural interaction
        frame = cv2.flip(frame, 1)

        # Process frame
        result = detector.process_frame(frame)

        # Check for engagement trigger
        if result.state == AttentionState.ENGAGED and not engagement_callback_fired:
            print("🎯 ENGAGED - Wake trigger!")
            engagement_callback_fired = True
        elif result.state != AttentionState.ENGAGED:
            engagement_callback_fired = False

        # Draw debug visualization
        debug = detector.draw_debug(frame, result)

        # Show frame
        cv2.imshow("Cass Attention Detector", debug)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            filename = f"attention_capture_{int(time.time())}.png"
            cv2.imwrite(filename, debug)
            print(f"Saved: {filename}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
