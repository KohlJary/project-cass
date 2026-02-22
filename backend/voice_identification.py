"""
Voice Identification Module

Speaker recognition using voice embeddings. Enables Cass to identify
WHO is speaking based on voice characteristics.

Uses Resemblyzer for speaker embeddings (lightweight, CPU-friendly).
"""

import io
import json
import logging
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Lazy-load Resemblyzer to avoid startup cost
_encoder = None
_encoder_loading = False

# Enrollment phrases for phonetic coverage
ENROLLMENT_PHRASES = [
    "The quick brown fox jumps over the lazy dog",
    "Hey Cass, what's the weather like today?",
    "Please add milk and eggs to my shopping list",
    "Set a reminder for tomorrow at nine AM",
    "Tell me something interesting",
]

# Identification thresholds
THRESHOLD_HIGH = 0.85      # High confidence - definite match
THRESHOLD_MEDIUM = 0.75    # Medium confidence - likely match
THRESHOLD_LOW = 0.60       # Low confidence - possible match


@dataclass
class SpeakerMatch:
    """Result of speaker identification."""
    user_id: Optional[str]
    confidence: float
    is_enrolled: bool
    display_name: Optional[str] = None


@dataclass
class EnrollmentSample:
    """A single enrollment voice sample."""
    phrase_index: int
    embedding: np.ndarray
    quality_score: float


def get_encoder():
    """
    Get or load the Resemblyzer voice encoder.

    Lazy-loaded to avoid startup cost if voice ID isn't used.
    """
    global _encoder, _encoder_loading

    if _encoder is not None:
        return _encoder

    if _encoder_loading:
        # Another thread is loading - wait
        import time
        for _ in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            if _encoder is not None:
                return _encoder
        raise RuntimeError("Timeout waiting for encoder to load")

    try:
        _encoder_loading = True
        logger.info("Loading Resemblyzer voice encoder...")

        from resemblyzer import VoiceEncoder
        _encoder = VoiceEncoder()

        logger.info("Resemblyzer encoder loaded")
        return _encoder

    except ImportError:
        logger.error("Resemblyzer not installed. Install with: pip install resemblyzer")
        raise RuntimeError("Voice identification requires resemblyzer package")

    finally:
        _encoder_loading = False


def preprocess_audio(audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
    """
    Preprocess audio bytes to numpy array for embedding extraction.

    Handles various audio formats via pydub/ffmpeg.
    """
    from pydub import AudioSegment

    # Load audio from bytes
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))

    # Convert to mono, 16kHz (Resemblyzer requirement)
    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(sample_rate)

    # Convert to numpy array
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

    # Normalize to [-1, 1]
    samples = samples / 32768.0

    return samples


def extract_embedding(audio_bytes: bytes) -> np.ndarray:
    """
    Extract speaker embedding from audio.

    Args:
        audio_bytes: Raw audio data (any format supported by pydub)

    Returns:
        256-dimensional speaker embedding
    """
    encoder = get_encoder()
    wav = preprocess_audio(audio_bytes)

    # Resemblyzer expects at least 1.6 seconds of audio
    min_samples = int(1.6 * 16000)
    if len(wav) < min_samples:
        # Pad with silence
        wav = np.pad(wav, (0, min_samples - len(wav)), mode='constant')

    embedding = encoder.embed_utterance(wav)
    return embedding


def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    Compute cosine similarity between two embeddings.

    Returns value in [0, 1] where 1 = identical.
    """
    # Normalize
    e1 = embedding1 / np.linalg.norm(embedding1)
    e2 = embedding2 / np.linalg.norm(embedding2)

    # Cosine similarity
    similarity = np.dot(e1, e2)

    # Clamp to [0, 1] (can be negative for very different voices)
    return float(max(0, similarity))


def estimate_audio_quality(audio_bytes: bytes) -> float:
    """
    Estimate audio quality/SNR for enrollment feedback.

    Returns score in [0, 1] where 1 = high quality.
    """
    try:
        wav = preprocess_audio(audio_bytes)

        # Simple quality metrics
        # 1. Check audio isn't mostly silence
        rms = np.sqrt(np.mean(wav ** 2))
        if rms < 0.01:
            return 0.1  # Too quiet

        # 2. Check audio isn't clipping
        peak = np.max(np.abs(wav))
        if peak > 0.99:
            return 0.5  # Clipping

        # 3. Check duration
        duration_sec = len(wav) / 16000
        if duration_sec < 1.5:
            return 0.3  # Too short
        if duration_sec > 15:
            return 0.7  # Very long (might have noise)

        # Good quality
        return min(1.0, 0.6 + rms * 2)  # Scale by loudness

    except Exception as e:
        logger.warning(f"Quality estimation failed: {e}")
        return 0.5


class VoiceEnrollmentManager:
    """
    Manages voice enrollment and identification.

    Stores voiceprints in SQLite, handles multi-sample enrollment sessions.
    """

    def __init__(self):
        from database.connection import get_db
        self._get_db = get_db

    def get_enrollment(self, user_id: str) -> Optional[dict]:
        """Get existing enrollment for a user."""
        with self._get_db() as conn:
            cursor = conn.execute(
                "SELECT id, embedding, sample_count, quality_score, created_at "
                "FROM voice_enrollments WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()

            if row:
                return {
                    "id": row[0],
                    "user_id": user_id,
                    "embedding": np.frombuffer(row[1], dtype=np.float32),
                    "sample_count": row[2],
                    "quality_score": row[3],
                    "created_at": row[4],
                }
            return None

    def get_all_enrollments(self) -> list[dict]:
        """Get all voice enrollments for identification."""
        with self._get_db() as conn:
            cursor = conn.execute(
                "SELECT ve.id, ve.user_id, ve.embedding, u.display_name "
                "FROM voice_enrollments ve "
                "JOIN users u ON ve.user_id = u.id"
            )

            enrollments = []
            for row in cursor.fetchall():
                enrollments.append({
                    "id": row[0],
                    "user_id": row[1],
                    "embedding": np.frombuffer(row[2], dtype=np.float32),
                    "display_name": row[3],
                })

            return enrollments

    def start_enrollment_session(self, user_id: str) -> dict:
        """
        Start a new enrollment session.

        Returns session info with required phrases.
        """
        session_id = str(uuid4())
        now = datetime.now()
        expires_at = now + timedelta(minutes=30)

        with self._get_db() as conn:
            # Cancel any existing sessions for this user
            conn.execute(
                "UPDATE voice_enrollment_sessions SET status = 'cancelled' "
                "WHERE user_id = ? AND status = 'in_progress'",
                (user_id,)
            )

            conn.execute(
                "INSERT INTO voice_enrollment_sessions "
                "(id, user_id, status, samples_json, required_samples, created_at, expires_at) "
                "VALUES (?, ?, 'in_progress', '[]', ?, ?, ?)",
                (session_id, user_id, len(ENROLLMENT_PHRASES),
                 now.isoformat(), expires_at.isoformat())
            )

        return {
            "session_id": session_id,
            "required_samples": len(ENROLLMENT_PHRASES),
            "phrases": ENROLLMENT_PHRASES,
            "expires_at": expires_at.isoformat(),
        }

    def add_enrollment_sample(
        self,
        session_id: str,
        phrase_index: int,
        audio_bytes: bytes
    ) -> dict:
        """
        Add a voice sample to an enrollment session.

        Returns quality feedback for the sample.
        """
        with self._get_db() as conn:
            # Get session
            cursor = conn.execute(
                "SELECT user_id, samples_json, status, expires_at "
                "FROM voice_enrollment_sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()

            if not row:
                raise ValueError("Enrollment session not found")

            user_id, samples_json, status, expires_at = row

            if status != 'in_progress':
                raise ValueError(f"Session is {status}, not in progress")

            if datetime.fromisoformat(expires_at) < datetime.now():
                raise ValueError("Session has expired")

            # Extract embedding and quality
            embedding = extract_embedding(audio_bytes)
            quality = estimate_audio_quality(audio_bytes)

            # Check quality threshold
            if quality < 0.3:
                return {
                    "accepted": False,
                    "quality_score": quality,
                    "feedback": "Audio quality too low. Please speak louder and closer to the mic.",
                }

            # Store sample
            samples = json.loads(samples_json)

            # Remove any existing sample for this phrase
            samples = [s for s in samples if s["phrase_index"] != phrase_index]

            samples.append({
                "phrase_index": phrase_index,
                "embedding_b64": embedding.tobytes().hex(),
                "quality_score": quality,
            })

            conn.execute(
                "UPDATE voice_enrollment_sessions SET samples_json = ? WHERE id = ?",
                (json.dumps(samples), session_id)
            )

            return {
                "accepted": True,
                "quality_score": quality,
                "sample_count": len(samples),
                "required_samples": len(ENROLLMENT_PHRASES),
                "feedback": self._quality_feedback(quality),
            }

    def _quality_feedback(self, quality: float) -> str:
        """Generate human-readable quality feedback."""
        if quality >= 0.8:
            return "Excellent quality!"
        elif quality >= 0.6:
            return "Good quality."
        elif quality >= 0.4:
            return "Acceptable quality. Try speaking a bit louder."
        else:
            return "Low quality. Please re-record in a quieter environment."

    def complete_enrollment(self, session_id: str) -> dict:
        """
        Complete enrollment session, generating centroid voiceprint.

        Requires all phrases to be recorded.
        """
        with self._get_db() as conn:
            cursor = conn.execute(
                "SELECT user_id, samples_json, required_samples "
                "FROM voice_enrollment_sessions WHERE id = ? AND status = 'in_progress'",
                (session_id,)
            )
            row = cursor.fetchone()

            if not row:
                raise ValueError("Active enrollment session not found")

            user_id, samples_json, required_samples = row
            samples = json.loads(samples_json)

            if len(samples) < required_samples:
                raise ValueError(
                    f"Need {required_samples} samples, only have {len(samples)}"
                )

            # Compute centroid embedding
            embeddings = []
            total_quality = 0.0

            for sample in samples:
                emb_bytes = bytes.fromhex(sample["embedding_b64"])
                embedding = np.frombuffer(emb_bytes, dtype=np.float32)
                embeddings.append(embedding)
                total_quality += sample["quality_score"]

            centroid = np.mean(embeddings, axis=0)
            avg_quality = total_quality / len(samples)

            # Store voiceprint (upsert)
            now = datetime.now().isoformat()
            enrollment_id = str(uuid4())

            conn.execute(
                "INSERT OR REPLACE INTO voice_enrollments "
                "(id, user_id, embedding, embedding_model, sample_count, quality_score, created_at, updated_at) "
                "VALUES (?, ?, ?, 'resemblyzer', ?, ?, ?, ?)",
                (enrollment_id, user_id, centroid.tobytes(),
                 len(samples), avg_quality, now, now)
            )

            # Mark session complete
            conn.execute(
                "UPDATE voice_enrollment_sessions SET status = 'completed' WHERE id = ?",
                (session_id,)
            )

            return {
                "success": True,
                "enrollment_id": enrollment_id,
                "sample_count": len(samples),
                "quality_score": avg_quality,
            }

    def delete_enrollment(self, user_id: str) -> bool:
        """Delete a user's voice enrollment."""
        with self._get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM voice_enrollments WHERE user_id = ?",
                (user_id,)
            )
            return cursor.rowcount > 0

    def identify_speaker(self, audio_bytes: bytes) -> SpeakerMatch:
        """
        Identify the speaker from audio.

        Compares against all enrolled voiceprints.
        """
        # Extract embedding from audio
        embedding = extract_embedding(audio_bytes)

        # Get all enrollments
        enrollments = self.get_all_enrollments()

        if not enrollments:
            return SpeakerMatch(
                user_id=None,
                confidence=0.0,
                is_enrolled=False,
            )

        # Find best match
        best_match = None
        best_score = 0.0

        for enrollment in enrollments:
            similarity = compute_similarity(embedding, enrollment["embedding"])

            if similarity > best_score:
                best_score = similarity
                best_match = enrollment

        # Apply threshold
        if best_score >= THRESHOLD_MEDIUM:
            return SpeakerMatch(
                user_id=best_match["user_id"],
                confidence=best_score,
                is_enrolled=True,
                display_name=best_match["display_name"],
            )
        else:
            return SpeakerMatch(
                user_id=None,
                confidence=best_score,
                is_enrolled=False,
            )


# Singleton instance
_manager: Optional[VoiceEnrollmentManager] = None


def get_voice_manager() -> VoiceEnrollmentManager:
    """Get or create the voice enrollment manager singleton."""
    global _manager
    if _manager is None:
        _manager = VoiceEnrollmentManager()
    return _manager


# Convenience functions
def identify_speaker(audio_bytes: bytes) -> SpeakerMatch:
    """Identify who is speaking from audio."""
    return get_voice_manager().identify_speaker(audio_bytes)


def is_voice_enrolled(user_id: str) -> bool:
    """Check if a user has enrolled their voice."""
    return get_voice_manager().get_enrollment(user_id) is not None
