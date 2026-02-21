#!/usr/bin/env python3
"""
Face Recognition Module - Identify who Cass is looking at.

Uses face_recognition library to:
1. Enroll known faces (save embeddings)
2. Match detected faces against known people
3. Return user identity for personalized interaction

Integrates with AttentionDetector for combined gaze + identity.
"""

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    print("face_recognition not available. Install with: pip install face_recognition")
    print("Note: Requires dlib, which may need cmake: sudo apt install cmake")


@dataclass
class RecognizedFace:
    """Result of face recognition."""
    user_id: Optional[str]  # None if unknown
    user_name: Optional[str]
    confidence: float  # 0-1, higher is better match
    face_location: tuple[int, int, int, int]  # (top, right, bottom, left)
    is_known: bool


class FaceDatabase:
    """
    Database of known faces.

    Stores face embeddings (128-d vectors) mapped to user IDs/names.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.embeddings_file = db_path / "face_embeddings.pkl"
        self.metadata_file = db_path / "face_metadata.json"

        # In-memory data
        self.embeddings: dict[str, list[np.ndarray]] = {}  # user_id -> list of embeddings
        self.metadata: dict[str, dict] = {}  # user_id -> {name, enrolled_at, ...}

        self._load()

    def _load(self):
        """Load database from disk."""
        self.db_path.mkdir(parents=True, exist_ok=True)

        if self.embeddings_file.exists():
            with open(self.embeddings_file, 'rb') as f:
                self.embeddings = pickle.load(f)

        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.metadata = json.load(f)

    def _save(self):
        """Save database to disk."""
        with open(self.embeddings_file, 'wb') as f:
            pickle.dump(self.embeddings, f)

        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    def enroll(
        self,
        user_id: str,
        user_name: str,
        face_image: np.ndarray,
    ) -> bool:
        """
        Enroll a face for a user.

        Can be called multiple times to add more reference images
        for better recognition accuracy.

        Args:
            user_id: Unique identifier (e.g., from Cass user system)
            user_name: Display name
            face_image: BGR image containing the face

        Returns:
            True if enrollment succeeded
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return False

        # Convert BGR to RGB
        rgb = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)

        # Get face encodings
        encodings = face_recognition.face_encodings(rgb)

        if not encodings:
            print(f"No face found in image for {user_name}")
            return False

        # Use first face found
        encoding = encodings[0]

        # Add to database
        if user_id not in self.embeddings:
            self.embeddings[user_id] = []
            self.metadata[user_id] = {
                "name": user_name,
                "enrolled_at": str(np.datetime64('now')),
                "image_count": 0,
            }

        self.embeddings[user_id].append(encoding)
        self.metadata[user_id]["image_count"] = len(self.embeddings[user_id])

        self._save()
        print(f"Enrolled face for {user_name} ({len(self.embeddings[user_id])} images)")
        return True

    def get_all_encodings(self) -> tuple[list[np.ndarray], list[str]]:
        """Get all encodings and their user IDs for matching."""
        all_encodings = []
        all_user_ids = []

        for user_id, encodings in self.embeddings.items():
            for encoding in encodings:
                all_encodings.append(encoding)
                all_user_ids.append(user_id)

        return all_encodings, all_user_ids

    def get_user_name(self, user_id: str) -> Optional[str]:
        """Get display name for a user ID."""
        if user_id in self.metadata:
            return self.metadata[user_id].get("name")
        return None

    def list_users(self) -> list[dict]:
        """List all enrolled users."""
        return [
            {"user_id": uid, **meta}
            for uid, meta in self.metadata.items()
        ]

    def remove_user(self, user_id: str) -> bool:
        """Remove a user from the database."""
        if user_id in self.embeddings:
            del self.embeddings[user_id]
            del self.metadata[user_id]
            self._save()
            return True
        return False


class FaceRecognizer:
    """
    Recognize faces in video frames.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        tolerance: float = 0.6,  # Lower = stricter matching
        min_confidence: float = 0.4,  # Minimum confidence to report match
    ):
        if db_path is None:
            db_path = Path(__file__).parent / "face_db"

        self.db = FaceDatabase(db_path)
        self.tolerance = tolerance
        self.min_confidence = min_confidence

        # Cache for performance
        self._known_encodings: list[np.ndarray] = []
        self._known_user_ids: list[str] = []
        self._refresh_cache()

    def _refresh_cache(self):
        """Refresh the encoding cache from database."""
        self._known_encodings, self._known_user_ids = self.db.get_all_encodings()

    def enroll_from_frame(
        self,
        frame: np.ndarray,
        user_id: str,
        user_name: str,
    ) -> bool:
        """Enroll the first face found in a frame."""
        success = self.db.enroll(user_id, user_name, frame)
        if success:
            self._refresh_cache()
        return success

    def recognize(self, frame: np.ndarray) -> list[RecognizedFace]:
        """
        Recognize all faces in a frame.

        Args:
            frame: BGR image from OpenCV

        Returns:
            List of RecognizedFace results
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return []

        # Convert BGR to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Detect faces and get encodings
        face_locations = face_recognition.face_locations(rgb)
        face_encodings = face_recognition.face_encodings(rgb, face_locations)

        results = []

        for location, encoding in zip(face_locations, face_encodings):
            if not self._known_encodings:
                # No known faces enrolled
                results.append(RecognizedFace(
                    user_id=None,
                    user_name=None,
                    confidence=0.0,
                    face_location=location,
                    is_known=False,
                ))
                continue

            # Compare against known faces
            distances = face_recognition.face_distance(self._known_encodings, encoding)

            if len(distances) == 0:
                results.append(RecognizedFace(
                    user_id=None,
                    user_name=None,
                    confidence=0.0,
                    face_location=location,
                    is_known=False,
                ))
                continue

            # Find best match
            best_idx = np.argmin(distances)
            best_distance = distances[best_idx]

            # Convert distance to confidence (0 distance = 1.0 confidence)
            confidence = max(0.0, 1.0 - (best_distance / self.tolerance))

            if best_distance <= self.tolerance and confidence >= self.min_confidence:
                user_id = self._known_user_ids[best_idx]
                user_name = self.db.get_user_name(user_id)
                results.append(RecognizedFace(
                    user_id=user_id,
                    user_name=user_name,
                    confidence=confidence,
                    face_location=location,
                    is_known=True,
                ))
            else:
                results.append(RecognizedFace(
                    user_id=None,
                    user_name=None,
                    confidence=confidence,
                    face_location=location,
                    is_known=False,
                ))

        return results

    def draw_recognition(
        self,
        frame: np.ndarray,
        faces: list[RecognizedFace],
    ) -> np.ndarray:
        """Draw recognition results on frame."""
        debug = frame.copy()

        for face in faces:
            top, right, bottom, left = face.face_location

            if face.is_known:
                color = (0, 255, 0)  # Green for known
                label = f"{face.user_name} ({face.confidence:.0%})"
            else:
                color = (0, 165, 255)  # Orange for unknown
                label = f"Unknown ({face.confidence:.0%})"

            # Draw box
            cv2.rectangle(debug, (left, top), (right, bottom), color, 2)

            # Draw label background
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            cv2.rectangle(
                debug,
                (left, bottom),
                (left + label_size[0] + 10, bottom + label_size[1] + 10),
                color,
                -1
            )

            # Draw label text
            cv2.putText(
                debug,
                label,
                (left + 5, bottom + label_size[1] + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                1
            )

        return debug


def enrollment_mode(recognizer: FaceRecognizer):
    """Interactive enrollment mode."""
    print("\n=== Face Enrollment Mode ===")
    print("Press 'e' to enroll current face")
    print("Press 'l' to list enrolled users")
    print("Press 'q' to quit enrollment mode")
    print()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)

        # Show current faces
        faces = recognizer.recognize(frame)
        debug = recognizer.draw_recognition(frame, faces)

        cv2.putText(
            debug,
            "ENROLLMENT MODE - Press 'e' to enroll",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

        cv2.imshow("Face Enrollment", debug)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break

        elif key == ord('e'):
            user_id = input("Enter user ID (or press Enter for auto): ").strip()
            if not user_id:
                import uuid
                user_id = str(uuid.uuid4())[:8]

            user_name = input("Enter display name: ").strip()
            if not user_name:
                user_name = f"User {user_id}"

            if recognizer.enroll_from_frame(frame, user_id, user_name):
                print(f"✓ Enrolled {user_name}")
            else:
                print("✗ Enrollment failed - no face detected")

        elif key == ord('l'):
            users = recognizer.db.list_users()
            print("\nEnrolled users:")
            for user in users:
                print(f"  - {user['name']} ({user['user_id']}): {user['image_count']} images")
            print()

    cap.release()
    cv2.destroyAllWindows()


def recognition_mode(recognizer: FaceRecognizer):
    """Live recognition mode."""
    print("\n=== Face Recognition Mode ===")
    print("Press 'q' to quit")
    print()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam")
        return

    # Track last announced person to avoid repetition
    last_announced: Optional[str] = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)

        # Recognize faces
        faces = recognizer.recognize(frame)
        debug = recognizer.draw_recognition(frame, faces)

        # Announce recognized people
        for face in faces:
            if face.is_known and face.user_id != last_announced:
                print(f"👋 Hello, {face.user_name}!")
                last_announced = face.user_id

        # Reset if no faces
        if not faces:
            last_announced = None

        cv2.imshow("Face Recognition", debug)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


def main():
    """Interactive face recognition demo."""
    print("Cass Face Recognition")
    print("=" * 40)

    if not FACE_RECOGNITION_AVAILABLE:
        print("\nface_recognition library not installed.")
        print("Install with: pip install face_recognition")
        print("Note: Requires dlib, which needs cmake")
        return

    recognizer = FaceRecognizer()

    users = recognizer.db.list_users()
    print(f"\nDatabase: {len(users)} enrolled users")

    print("\nModes:")
    print("  1. Enrollment - Add faces to database")
    print("  2. Recognition - Identify faces")
    print("  q. Quit")

    while True:
        choice = input("\nSelect mode: ").strip().lower()

        if choice == '1':
            enrollment_mode(recognizer)
        elif choice == '2':
            recognition_mode(recognizer)
        elif choice == 'q':
            break
        else:
            print("Invalid choice")


if __name__ == "__main__":
    main()
