"""
Face Identification Module - Recognize who Cass is looking at.

Uses face_recognition library (dlib) for:
1. Face detection and embedding extraction
2. Multi-image enrollment for robust matching
3. Identification against enrolled users

Similar architecture to voice_identification.py for consistency.
"""

import asyncio
import base64
import io
import logging
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
    logger.info("cv2 (OpenCV) imported successfully")
except ImportError as e:
    CV2_AVAILABLE = False
    logger.warning(f"cv2 import failed: {e}")

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
    logger.info("face_recognition imported successfully")
except ImportError as e:
    logger.warning(f"face_recognition ImportError: {e}")
    FACE_RECOGNITION_AVAILABLE = False
except Exception as e:
    logger.error(f"face_recognition Exception: {e}")
    FACE_RECOGNITION_AVAILABLE = False

logger.info(f"Face identification availability: CV2={CV2_AVAILABLE}, face_recognition={FACE_RECOGNITION_AVAILABLE}")

from database import get_connection


class ConfidenceLevel(Enum):
    """Confidence level for face identification."""
    HIGH = "high"      # Very confident match
    MEDIUM = "medium"  # Likely match
    LOW = "low"        # Possible match
    NONE = "none"      # No match found


# Thresholds for face distance (lower = stricter, face_recognition uses distance not similarity)
CONFIDENCE_HIGH = 0.4    # Very close match
CONFIDENCE_MEDIUM = 0.5  # Good match
CONFIDENCE_LOW = 0.6     # Acceptable match


@dataclass
class FaceMatch:
    """Result of face identification."""
    user_id: Optional[str]
    display_name: Optional[str]
    confidence: float  # 0-1, higher is better
    confidence_level: ConfidenceLevel
    face_location: Optional[tuple]  # (top, right, bottom, left)


@dataclass
class EnrollmentSample:
    """A single face sample during enrollment."""
    embedding: np.ndarray
    quality_score: float
    captured_at: datetime


# Enrollment phrases/instructions for capturing varied angles
ENROLLMENT_INSTRUCTIONS = [
    "Look directly at the camera",
    "Turn your head slightly to the left",
    "Turn your head slightly to the right",
    "Tilt your head up slightly",
    "Smile naturally",
]


class FaceEnrollmentManager:
    """
    Manages face enrollment sessions.

    Enrollment flow:
    1. Start session with user_id
    2. Capture multiple images (5 recommended)
    3. Complete enrollment -> create centroid embedding
    """

    def __init__(self):
        self._sessions: Dict[str, dict] = {}
        self._session_ttl = timedelta(minutes=15)

    def start_session(self, user_id: str) -> dict:
        """Start a new enrollment session."""
        session_id = str(uuid.uuid4())

        self._sessions[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "samples": [],
            "created_at": datetime.now(),
            "expires_at": datetime.now() + self._session_ttl,
        }

        return {
            "session_id": session_id,
            "required_samples": len(ENROLLMENT_INSTRUCTIONS),
            "instructions": ENROLLMENT_INSTRUCTIONS,
            "expires_at": (datetime.now() + self._session_ttl).isoformat(),
        }

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session if it exists and hasn't expired."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        if datetime.now() > session["expires_at"]:
            del self._sessions[session_id]
            return None

        return session

    async def add_sample(
        self,
        session_id: str,
        image_data: bytes,
    ) -> dict:
        """
        Add a face sample to the enrollment session.

        Args:
            session_id: The enrollment session ID
            image_data: Raw image bytes (JPEG/PNG)

        Returns:
            dict with accepted, quality_score, feedback
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Invalid or expired session")

        # Extract face embedding
        embedding, quality_score, feedback = await extract_face_embedding(image_data)

        if embedding is None:
            return {
                "accepted": False,
                "quality_score": 0.0,
                "sample_count": len(session["samples"]),
                "required_samples": len(ENROLLMENT_INSTRUCTIONS),
                "feedback": feedback or "No face detected in image",
            }

        # Add to session
        sample = EnrollmentSample(
            embedding=embedding,
            quality_score=quality_score,
            captured_at=datetime.now(),
        )
        session["samples"].append(sample)

        return {
            "accepted": True,
            "quality_score": quality_score,
            "sample_count": len(session["samples"]),
            "required_samples": len(ENROLLMENT_INSTRUCTIONS),
            "feedback": feedback or "Good sample captured",
        }

    async def complete_enrollment(self, session_id: str) -> dict:
        """
        Complete enrollment and save the face embedding.

        Creates a centroid embedding from all samples.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Invalid or expired session")

        samples = session["samples"]
        if len(samples) < 3:
            raise ValueError(f"Need at least 3 samples, got {len(samples)}")

        # Create centroid embedding (average of all samples)
        embeddings = [s.embedding for s in samples]
        centroid = np.mean(embeddings, axis=0)

        # Normalize the centroid
        centroid = centroid / np.linalg.norm(centroid)

        # Calculate average quality
        avg_quality = np.mean([s.quality_score for s in samples])

        # Save to database
        enrollment_id = await save_face_enrollment(
            user_id=session["user_id"],
            embedding=centroid,
            sample_count=len(samples),
            quality_score=avg_quality,
        )

        # Clean up session
        del self._sessions[session_id]

        return {
            "success": True,
            "enrollment_id": enrollment_id,
            "sample_count": len(samples),
            "quality_score": avg_quality,
        }

    def cleanup_expired(self):
        """Remove expired sessions."""
        now = datetime.now()
        expired = [
            sid for sid, session in self._sessions.items()
            if now > session["expires_at"]
        ]
        for sid in expired:
            del self._sessions[sid]


# Global enrollment manager
_enrollment_manager: Optional[FaceEnrollmentManager] = None


def get_enrollment_manager() -> FaceEnrollmentManager:
    """Get or create the global enrollment manager."""
    global _enrollment_manager
    if _enrollment_manager is None:
        _enrollment_manager = FaceEnrollmentManager()
    return _enrollment_manager


async def extract_face_embedding(
    image_data: bytes,
) -> tuple[Optional[np.ndarray], float, Optional[str]]:
    """
    Extract face embedding from image data.

    Args:
        image_data: Raw image bytes (JPEG/PNG)

    Returns:
        (embedding, quality_score, feedback_message)
        embedding is None if no face detected
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return None, 0.0, "face_recognition library not installed"

    if not CV2_AVAILABLE:
        return None, 0.0, "OpenCV not installed"

    # Decode image
    try:
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            return None, 0.0, "Could not decode image"
    except Exception as e:
        return None, 0.0, f"Image decode error: {e}"

    # Convert BGR to RGB
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Detect faces
    face_locations = face_recognition.face_locations(rgb)

    if not face_locations:
        return None, 0.0, "No face detected - ensure face is visible and well-lit"

    if len(face_locations) > 1:
        # Use largest face (closest)
        face_locations = sorted(
            face_locations,
            key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]),
            reverse=True
        )
        face_locations = [face_locations[0]]

    # Get face encoding
    encodings = face_recognition.face_encodings(rgb, face_locations)

    if not encodings:
        return None, 0.0, "Could not extract face features"

    embedding = encodings[0]

    # Estimate quality based on face size and position
    top, right, bottom, left = face_locations[0]
    h, w = rgb.shape[:2]

    face_height = bottom - top
    face_width = right - left
    face_area = face_height * face_width
    image_area = h * w

    # Quality factors
    size_ratio = face_area / image_area
    center_x = (left + right) / 2 / w
    center_y = (top + bottom) / 2 / h

    # Prefer larger faces (closer) and centered faces
    size_score = min(1.0, size_ratio * 10)  # ~10% of image is good
    center_score = 1.0 - (abs(center_x - 0.5) + abs(center_y - 0.5))

    quality_score = (size_score * 0.6 + center_score * 0.4)

    # Feedback
    feedback = None
    if size_score < 0.3:
        feedback = "Move closer to the camera"
    elif center_score < 0.5:
        feedback = "Center your face in the frame"
    elif quality_score >= 0.7:
        feedback = "Excellent capture"
    elif quality_score >= 0.5:
        feedback = "Good capture"
    else:
        feedback = "Acceptable, but try better lighting"

    return embedding, quality_score, feedback


async def save_face_enrollment(
    user_id: str,
    embedding: np.ndarray,
    sample_count: int,
    quality_score: float,
) -> str:
    """Save face enrollment to database."""
    conn = get_connection()
    cursor = conn.cursor()

    enrollment_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    # Serialize embedding
    embedding_blob = pickle.dumps(embedding)

    # Ensure user exists (create if not - for face enrollment from admin UI)
    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        # Create a minimal user record
        cursor.execute(
            "INSERT INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
            (user_id, user_id, now)
        )
        logger.info(f"Created user record for face enrollment: {user_id}")

    # Delete existing enrollment for this user (one face per user)
    cursor.execute(
        "DELETE FROM face_enrollments WHERE user_id = ?",
        (user_id,)
    )

    # Insert new enrollment
    cursor.execute(
        """
        INSERT INTO face_enrollments
        (id, user_id, embedding, embedding_model, sample_count, quality_score, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (enrollment_id, user_id, embedding_blob, "face_recognition", sample_count, quality_score, now, now)
    )

    conn.commit()
    logger.info(f"Saved face enrollment for user {user_id}: {sample_count} samples, quality={quality_score:.2f}")

    return enrollment_id


async def get_enrollment_status(user_id: str) -> dict:
    """Check if a user has enrolled their face."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, sample_count, quality_score, created_at
        FROM face_enrollments
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    if row:
        return {
            "enrolled": True,
            "enrollment_id": row[0],
            "sample_count": row[1],
            "quality_score": row[2],
            "created_at": row[3],
        }
    else:
        return {"enrolled": False}


async def delete_enrollment(user_id: str) -> bool:
    """Delete face enrollment for a user."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM face_enrollments WHERE user_id = ?",
        (user_id,)
    )

    deleted = cursor.rowcount > 0
    conn.commit()

    if deleted:
        logger.info(f"Deleted face enrollment for user {user_id}")

    return deleted


async def get_all_enrollments() -> List[tuple]:
    """Get all face enrollments for matching."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT fe.user_id, fe.embedding, u.display_name
        FROM face_enrollments fe
        LEFT JOIN users u ON fe.user_id = u.id
        """
    )

    results = []
    for row in cursor.fetchall():
        user_id = row[0]
        embedding = pickle.loads(row[1])
        display_name = row[2] or f"User {user_id[:8]}"
        results.append((user_id, embedding, display_name))

    return results


async def identify_face(image_data: bytes) -> Optional[FaceMatch]:
    """
    Identify a face from image data.

    Args:
        image_data: Raw image bytes (JPEG/PNG)

    Returns:
        FaceMatch with identified user, or None if no face detected
    """
    if not FACE_RECOGNITION_AVAILABLE or not CV2_AVAILABLE:
        return None

    # Extract embedding from input
    embedding, _, _ = await extract_face_embedding(image_data)

    if embedding is None:
        return None

    # Get all enrolled faces
    enrollments = await get_all_enrollments()

    if not enrollments:
        return FaceMatch(
            user_id=None,
            display_name=None,
            confidence=0.0,
            confidence_level=ConfidenceLevel.NONE,
            face_location=None,
        )

    # Compare against all enrolled faces
    known_embeddings = [e[1] for e in enrollments]
    distances = face_recognition.face_distance(known_embeddings, embedding)

    # Find best match
    best_idx = np.argmin(distances)
    best_distance = distances[best_idx]

    # Convert distance to confidence (0 distance = 1.0 confidence)
    # face_recognition uses Euclidean distance, typically 0-1 range
    confidence = max(0.0, 1.0 - best_distance)

    # Determine confidence level
    if best_distance <= CONFIDENCE_HIGH:
        confidence_level = ConfidenceLevel.HIGH
    elif best_distance <= CONFIDENCE_MEDIUM:
        confidence_level = ConfidenceLevel.MEDIUM
    elif best_distance <= CONFIDENCE_LOW:
        confidence_level = ConfidenceLevel.LOW
    else:
        confidence_level = ConfidenceLevel.NONE

    if confidence_level == ConfidenceLevel.NONE:
        return FaceMatch(
            user_id=None,
            display_name=None,
            confidence=confidence,
            confidence_level=confidence_level,
            face_location=None,
        )

    user_id, _, display_name = enrollments[best_idx]

    return FaceMatch(
        user_id=user_id,
        display_name=display_name,
        confidence=confidence,
        confidence_level=confidence_level,
        face_location=None,
    )


def is_available() -> bool:
    """Check if face identification is available."""
    return FACE_RECOGNITION_AVAILABLE and CV2_AVAILABLE


async def get_all_face_embeddings() -> List[Dict[str, Any]]:
    """
    Get all face embeddings for remote face recognition.

    Returns list of {user_id, display_name, embedding} dicts.
    Embedding is base64-encoded pickle for transport.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT fe.user_id, u.display_name, fe.embedding, fe.quality_score
        FROM face_enrollments fe
        LEFT JOIN users u ON fe.user_id = u.id
    """)

    results = []
    for row in cursor.fetchall():
        user_id, display_name, embedding_blob, quality = row
        # Base64 encode the pickle blob for JSON transport
        embedding_b64 = base64.b64encode(embedding_blob).decode('utf-8')
        results.append({
            "user_id": user_id,
            "display_name": display_name or user_id,
            "embedding": embedding_b64,
            "quality_score": quality,
        })

    return results
