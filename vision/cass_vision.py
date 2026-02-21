#!/usr/bin/env python3
"""
Cass Vision System - Integrated attention + recognition.

Combines:
- Eye contact detection (who is looking at Cass?)
- Face recognition (who is this person?)
- Engagement tracking (should Cass wake up?)

This is the main entry point for Cass's visual awareness.
"""

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from attention_detector import AttentionDetector, AttentionState, GazeResult
from face_recognition_module import FaceRecognizer, RecognizedFace


class EngagementEvent(Enum):
    """Types of engagement events."""
    NONE = "none"
    ATTENTION_START = "attention_start"  # Someone started looking
    ATTENTION_END = "attention_end"      # Someone looked away
    ENGAGED = "engaged"                   # Sustained eye contact (wake trigger)
    USER_IDENTIFIED = "user_identified"   # Known user recognized
    NEW_FACE = "new_face"                 # Unknown person detected


@dataclass
class VisionState:
    """Current state of Cass's visual awareness."""
    # Attention
    attention: AttentionState
    attention_confidence: float
    attention_duration: float
    gaze_direction: Optional[tuple[float, float]]

    # Recognition
    user_id: Optional[str]
    user_name: Optional[str]
    recognition_confidence: float
    is_known_user: bool

    # Face location
    face_location: Optional[tuple[int, int, int, int]]
    face_center: Optional[tuple[int, int]]

    # Events this frame
    events: list[EngagementEvent]


class CassVision:
    """
    Integrated vision system for Cass.

    Combines attention detection and face recognition into a unified
    awareness system. Emits events when engagement states change.
    """

    def __init__(
        self,
        face_db_path: Optional[Path] = None,
        engagement_threshold: float = 1.5,
        recognition_interval: int = 10,  # Run recognition every N frames
        on_event: Optional[Callable[[EngagementEvent, VisionState], None]] = None,
    ):
        """
        Initialize the vision system.

        Args:
            face_db_path: Path to face database directory
            engagement_threshold: Seconds of eye contact to trigger wake
            recognition_interval: Frames between face recognition (for performance)
            on_event: Callback for engagement events
        """
        self.attention = AttentionDetector(
            engagement_threshold=engagement_threshold,
            gaze_threshold=0.12,
        )
        self.recognizer = FaceRecognizer(
            db_path=face_db_path,
            tolerance=0.6,
        )
        self.recognition_interval = recognition_interval
        self.on_event = on_event

        # State tracking
        self.frame_count = 0
        self.last_attention_state = AttentionState.NO_FACE
        self.last_user_id: Optional[str] = None
        self.current_recognition: Optional[RecognizedFace] = None
        self.engaged_announced = False

    def process_frame(self, frame: np.ndarray) -> VisionState:
        """
        Process a video frame and return vision state.

        Args:
            frame: BGR image from OpenCV

        Returns:
            VisionState with attention, recognition, and events
        """
        self.frame_count += 1
        events = []

        # Always run attention detection (fast)
        gaze_result = self.attention.process_frame(frame)

        # Run face recognition periodically (slower)
        if self.frame_count % self.recognition_interval == 0:
            faces = self.recognizer.recognize(frame)
            if faces:
                # Use first/closest face
                self.current_recognition = faces[0]

                # Check for new user
                if self.current_recognition.is_known:
                    if self.current_recognition.user_id != self.last_user_id:
                        events.append(EngagementEvent.USER_IDENTIFIED)
                        self.last_user_id = self.current_recognition.user_id
                else:
                    if self.last_user_id is not None:
                        # Was known, now unknown (different person?)
                        events.append(EngagementEvent.NEW_FACE)
                    self.last_user_id = None
            else:
                self.current_recognition = None
                self.last_user_id = None

        # Detect attention state changes
        if gaze_result.state != self.last_attention_state:
            if gaze_result.state == AttentionState.LOOKING_AT_CAMERA:
                events.append(EngagementEvent.ATTENTION_START)
            elif self.last_attention_state == AttentionState.LOOKING_AT_CAMERA:
                events.append(EngagementEvent.ATTENTION_END)

            self.last_attention_state = gaze_result.state

        # Check for engagement trigger
        if gaze_result.state == AttentionState.ENGAGED and not self.engaged_announced:
            events.append(EngagementEvent.ENGAGED)
            self.engaged_announced = True
        elif gaze_result.state != AttentionState.ENGAGED:
            self.engaged_announced = False

        # Build state
        state = VisionState(
            attention=gaze_result.state,
            attention_confidence=gaze_result.confidence,
            attention_duration=gaze_result.attention_duration,
            gaze_direction=gaze_result.gaze_direction,
            user_id=self.current_recognition.user_id if self.current_recognition else None,
            user_name=self.current_recognition.user_name if self.current_recognition else None,
            recognition_confidence=self.current_recognition.confidence if self.current_recognition else 0.0,
            is_known_user=self.current_recognition.is_known if self.current_recognition else False,
            face_location=self.current_recognition.face_location if self.current_recognition else None,
            face_center=gaze_result.face_center,
            events=events,
        )

        # Fire event callbacks
        if self.on_event and events:
            for event in events:
                self.on_event(event, state)

        return state

    def draw_debug(self, frame: np.ndarray, state: VisionState) -> np.ndarray:
        """Draw combined debug visualization."""
        debug = frame.copy()

        # Draw attention visualization
        gaze_result = GazeResult(
            state=state.attention,
            confidence=state.attention_confidence,
            face_center=state.face_center,
            left_eye=None,
            right_eye=None,
            gaze_direction=state.gaze_direction,
            attention_duration=state.attention_duration,
        )
        debug = self.attention.draw_debug(debug, gaze_result)

        # Draw recognition overlay
        if state.face_location:
            top, right, bottom, left = state.face_location

            if state.is_known_user:
                color = (0, 255, 0)
                label = f"{state.user_name}"
            else:
                color = (0, 165, 255)
                label = "Unknown"

            # Draw name above face
            cv2.putText(
                debug,
                label,
                (left, top - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2
            )

        # Draw events
        y_offset = 120
        for event in state.events:
            cv2.putText(
                debug,
                f"EVENT: {event.value}",
                (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 255),
                2
            )
            y_offset += 25

        return debug

    def enroll_user(self, frame: np.ndarray, user_id: str, user_name: str) -> bool:
        """Enroll a face from the current frame."""
        return self.recognizer.enroll_from_frame(frame, user_id, user_name)

    def list_users(self) -> list[dict]:
        """List all enrolled users."""
        return self.recognizer.db.list_users()


def on_vision_event(event: EngagementEvent, state: VisionState):
    """Example event handler."""
    if event == EngagementEvent.ENGAGED:
        if state.is_known_user:
            print(f"🎯 WAKE: {state.user_name} is engaging!")
        else:
            print(f"🎯 WAKE: Unknown person engaging")

    elif event == EngagementEvent.USER_IDENTIFIED:
        print(f"👋 Recognized: {state.user_name}")

    elif event == EngagementEvent.NEW_FACE:
        print(f"👤 New face detected")

    elif event == EngagementEvent.ATTENTION_START:
        print(f"👁️ Someone is looking")

    elif event == EngagementEvent.ATTENTION_END:
        print(f"👁️ Looked away")


def main():
    """Run integrated vision system."""
    print("Cass Vision System")
    print("=" * 40)
    print()
    print("Commands:")
    print("  e - Enroll current face")
    print("  l - List enrolled users")
    print("  s - Save screenshot")
    print("  q - Quit")
    print()

    vision = CassVision(
        engagement_threshold=1.5,
        recognition_interval=10,
        on_event=on_vision_event,
    )

    # List existing users
    users = vision.list_users()
    if users:
        print(f"Enrolled users: {', '.join(u['name'] for u in users)}")
    else:
        print("No enrolled users. Press 'e' to enroll.")
    print()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)

        # Process frame
        state = vision.process_frame(frame)

        # Draw debug
        debug = vision.draw_debug(frame, state)

        cv2.imshow("Cass Vision", debug)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break

        elif key == ord('e'):
            print("\n>>> Position your face in the GREEN box and press SPACE when box appears...")
            print(">>> Press Q to cancel")

            import face_recognition_models
            import face_recognition

            # Wait for space key while showing live preview with face detection
            while True:
                ret, enroll_frame = cap.read()
                if not ret:
                    break
                enroll_frame = cv2.flip(enroll_frame, 1)
                h, w = enroll_frame.shape[:2]

                # Draw target zone (center of frame)
                margin = 100
                cv2.rectangle(
                    enroll_frame,
                    (margin, margin),
                    (w - margin, h - margin),
                    (128, 128, 128),
                    2
                )

                # Detect faces in real-time
                rgb = cv2.cvtColor(enroll_frame, cv2.COLOR_BGR2RGB)
                # Use smaller frame for faster detection
                small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
                face_locations = face_recognition.face_locations(small)

                face_detected = len(face_locations) > 0

                # Draw detected faces (scale back up)
                for (top, right, bottom, left) in face_locations:
                    top *= 2
                    right *= 2
                    bottom *= 2
                    left *= 2
                    cv2.rectangle(enroll_frame, (left, top), (right, bottom), (0, 255, 0), 3)

                # Draw status
                if face_detected:
                    status = "FACE DETECTED - Press SPACE to capture"
                    color = (0, 255, 0)
                else:
                    status = "No face - move closer, check lighting"
                    color = (0, 0, 255)

                cv2.putText(enroll_frame, status, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                cv2.putText(enroll_frame, "Press Q to cancel", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                cv2.imshow("Cass Vision", enroll_frame)

                k = cv2.waitKey(1) & 0xFF
                if k == ord(' ') and face_detected:
                    break
                elif k == ord(' ') and not face_detected:
                    print("  No face detected yet - keep trying")
                elif k == ord('q'):
                    enroll_frame = None
                    break

            if enroll_frame is None:
                print("Enrollment cancelled")
                continue

            user_id = input("User ID (Enter for auto): ").strip()
            if not user_id:
                import uuid
                user_id = str(uuid.uuid4())[:8]

            user_name = input("Display name: ").strip()
            if not user_name:
                user_name = f"User {user_id}"

            if vision.enroll_user(enroll_frame, user_id, user_name):
                print(f"✓ Enrolled {user_name}")
            else:
                print("✗ Failed - no face detected (check lighting/position)")

        elif key == ord('l'):
            users = vision.list_users()
            print("\nEnrolled users:")
            for u in users:
                print(f"  - {u['name']} ({u['user_id']})")
            print()

        elif key == ord('s'):
            filename = f"cass_vision_{int(time.time())}.png"
            cv2.imwrite(filename, debug)
            print(f"Saved: {filename}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
