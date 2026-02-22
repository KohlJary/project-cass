# Voice Identification Spec

## Goal

Enable Cass to identify WHO is speaking based on voice characteristics, not just transcribe what they say. This allows automatic user identification without verbal confirmation.

## Use Cases

1. **Automatic user switching** - "Hey Cass, what's on my calendar?" → knows it's Kohl vs. a guest
2. **Personalized responses** - Cass adjusts tone/context based on speaker
3. **Security** - Only respond to enrolled/authorized voices
4. **Multi-user conversations** - Track who said what in group settings

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     VOICE IDENTIFICATION                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐         ┌──────────────┐                      │
│  │ Enrollment   │         │ Identification│                     │
│  │ Flow         │         │ Flow          │                     │
│  └──────┬───────┘         └──────┬───────┘                      │
│         │                        │                               │
│         ▼                        ▼                               │
│  ┌─────────────────────────────────────────┐                    │
│  │         Speaker Embedding Model          │                    │
│  │  (Resemblyzer / ECAPA-TDNN / pyannote)  │                    │
│  └─────────────────┬───────────────────────┘                    │
│                    │                                             │
│         ┌──────────┴──────────┐                                 │
│         ▼                     ▼                                 │
│  ┌─────────────┐      ┌─────────────────┐                       │
│  │ Voiceprint  │      │ Cosine          │                       │
│  │ Storage     │◄────►│ Similarity      │                       │
│  │ (per user)  │      │ Matching        │                       │
│  └─────────────┘      └─────────────────┘                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Model Selection

### Option 1: Resemblyzer (Recommended for MVP)
- **Pros**: Lightweight (~50MB), CPU-friendly, simple API, good accuracy
- **Cons**: Not state-of-the-art, less robust to noise
- **Install**: `pip install resemblyzer`
- **Embedding dim**: 256

### Option 2: SpeechBrain ECAPA-TDNN
- **Pros**: State-of-the-art accuracy, robust to noise, well-maintained
- **Cons**: Larger model (~100MB), needs GPU for speed
- **Install**: `pip install speechbrain`
- **Embedding dim**: 192

### Option 3: pyannote-audio
- **Pros**: Full speaker diarization (who spoke when), production-ready
- **Cons**: Requires HuggingFace token, more complex setup
- **Install**: `pip install pyannote.audio`

### Recommendation
Start with **Resemblyzer** for simplicity, upgrade to **ECAPA-TDNN** if accuracy is insufficient.

---

## Data Model

### Voiceprint Storage

```python
# New table: voice_enrollments
class VoiceEnrollment:
    id: str  # UUID
    user_id: str  # FK to users
    embedding: bytes  # Serialized numpy array (256 or 192 floats)
    sample_count: int  # Number of samples used to create this embedding
    quality_score: float  # Optional: SNR or confidence metric
    created_at: datetime
    updated_at: datetime

# Centroid approach: store averaged embedding for faster matching
# Alternative: store multiple embeddings per user, match against all
```

### Database Schema

```sql
CREATE TABLE voice_enrollments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    embedding BLOB NOT NULL,  -- numpy array as bytes
    sample_count INTEGER DEFAULT 1,
    quality_score REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id)  -- One voiceprint per user (centroid approach)
);
```

---

## Enrollment Flow

### Step 1: Collect Voice Samples

User records 3-5 phrases (~3-10 seconds each) to build a robust voiceprint:

```
Enrollment phrases (designed for phonetic coverage):
1. "The quick brown fox jumps over the lazy dog"
2. "Hey Cass, what's the weather like today?"
3. "Please add milk and eggs to my shopping list"
4. "Set a reminder for tomorrow at nine AM"
5. "Tell me something interesting"
```

### Step 2: Generate Embeddings

```python
from resemblyzer import VoiceEncoder, preprocess_wav
import numpy as np

encoder = VoiceEncoder()

def enroll_user(audio_samples: list[bytes]) -> np.ndarray:
    """
    Generate a centroid embedding from multiple audio samples.

    Args:
        audio_samples: List of audio files (wav/webm bytes)

    Returns:
        Centroid embedding (256-dim for Resemblyzer)
    """
    embeddings = []
    for audio in audio_samples:
        wav = preprocess_wav(audio)
        embedding = encoder.embed_utterance(wav)
        embeddings.append(embedding)

    # Centroid = average of all embeddings
    centroid = np.mean(embeddings, axis=0)
    return centroid
```

### Step 3: Store Voiceprint

```python
def save_voiceprint(user_id: str, embedding: np.ndarray):
    """Store voiceprint linked to user profile."""
    embedding_bytes = embedding.tobytes()
    # Save to voice_enrollments table
```

---

## Identification Flow

### On Each STT Request

```python
async def identify_and_transcribe(audio: bytes) -> dict:
    """
    Identify speaker and transcribe audio.

    Returns:
        {
            "text": "transcribed text",
            "speaker": {
                "user_id": "abc123" or None,
                "confidence": 0.87,
                "is_enrolled": True
            }
        }
    """
    # 1. Extract speaker embedding from audio
    wav = preprocess_wav(audio)
    embedding = encoder.embed_utterance(wav)

    # 2. Compare against enrolled voiceprints
    best_match = None
    best_score = 0.0

    for enrollment in get_all_enrollments():
        stored_embedding = np.frombuffer(enrollment.embedding)
        similarity = cosine_similarity(embedding, stored_embedding)

        if similarity > best_score:
            best_score = similarity
            best_match = enrollment.user_id

    # 3. Apply threshold
    IDENTIFICATION_THRESHOLD = 0.75  # Tune this

    if best_score >= IDENTIFICATION_THRESHOLD:
        speaker = {
            "user_id": best_match,
            "confidence": best_score,
            "is_enrolled": True
        }
    else:
        speaker = {
            "user_id": None,
            "confidence": best_score,
            "is_enrolled": False
        }

    # 4. Transcribe with Whisper (existing STT)
    text = await transcribe_with_whisper(audio)

    return {"text": text, "speaker": speaker}
```

### Confidence Thresholds

| Score Range | Interpretation | Action |
|-------------|----------------|--------|
| > 0.85 | High confidence | Identify as user |
| 0.75 - 0.85 | Medium confidence | Identify but flag |
| 0.60 - 0.75 | Low confidence | Ask for confirmation |
| < 0.60 | No match | Treat as unknown |

---

## API Endpoints

### Enrollment

```
POST /admin/voice/enroll/start
  → Returns enrollment session ID, required phrases

POST /admin/voice/enroll/sample
  Body: { session_id, phrase_index, audio (base64) }
  → Validates audio quality, stores sample

POST /admin/voice/enroll/complete
  Body: { session_id }
  → Generates centroid, stores voiceprint
  → Returns success + quality metrics

DELETE /admin/voice/enroll
  → Removes user's voiceprint
```

### Identification

```
GET /admin/voice/status
  → Returns enrollment status for current user

POST /admin/voice/identify
  Body: { audio (base64) }
  → Returns speaker identification without transcription
```

### Modified STT Endpoint

```
POST /admin/stt/transcribe
  Body: { audio, format, identify_speaker: bool }
  Response: {
      text: "...",
      language: "en",
      duration: 3.2,
      speaker: {  // NEW - only if identify_speaker=true
          user_id: "abc123",
          confidence: 0.89,
          display_name: "Kohl"
      }
  }
```

---

## Frontend: Enrollment UI

### Admin Frontend: Voice Enrollment Page

```
/voice-enrollment

┌─────────────────────────────────────────────────────┐
│  Voice Enrollment                                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Status: Not Enrolled  [Start Enrollment]           │
│                                                     │
│  ─────────────────────────────────────────────────  │
│                                                     │
│  Step 1 of 5                                        │
│                                                     │
│  Please say:                                        │
│  "The quick brown fox jumps over the lazy dog"     │
│                                                     │
│        ┌─────────────────────┐                     │
│        │   🎤 Recording...   │                     │
│        │   ████████░░░ 3.2s  │                     │
│        └─────────────────────┘                     │
│                                                     │
│  [Re-record]                    [Next Phrase →]    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Voice Call Integration

When voice identification is enabled, the VoiceCall page could show:

```
┌─────────────────────────────────────────────────────┐
│  Voice Call                                         │
│  Connected | STT: base | TTS: Piper                │
│  Speaker: Kohl (92% confidence)  ← NEW             │
└─────────────────────────────────────────────────────┘
```

---

## Integration with Chat

### WebSocket Message Enhancement

```python
# In websocket_handlers.py, after STT:

if identify_speaker and audio_data:
    speaker_info = await identify_speaker(audio_data)

    if speaker_info["user_id"]:
        # Override connection user with voice-identified user
        ws_user_id = speaker_info["user_id"]

        await websocket.send_json({
            "type": "speaker_identified",
            "user_id": ws_user_id,
            "confidence": speaker_info["confidence"],
            "display_name": user_manager.get_display_name(ws_user_id)
        })
```

### Cass Context

Add to system prompt when speaker is identified:

```
[Speaker identified as Kohl (92% confidence) via voice recognition]
```

This lets Cass acknowledge the identification naturally:
> "Hey Kohl, I recognized your voice. What can I help you with?"

---

## Privacy & Security Considerations

1. **Voiceprints are biometric data** - Store securely, allow deletion
2. **Consent** - Users must explicitly opt-in to voice enrollment
3. **Local processing** - Keep embeddings on-device, no cloud
4. **Spoofing** - Voice can be recorded/replayed; not suitable for high-security auth
5. **Liveness detection** - Future: detect if audio is live vs. playback

---

## Implementation Order

### Phase 1: Core Infrastructure
1. Add `voice_enrollments` table
2. Integrate Resemblyzer model
3. Create enrollment API endpoints
4. Create identification function

### Phase 2: Enrollment UI
5. Build enrollment page in admin-frontend
6. Audio recording with quality feedback
7. Multi-phrase enrollment flow

### Phase 3: Integration
8. Add `identify_speaker` option to STT endpoint
9. Integrate with WebSocket chat flow
10. Add speaker info to VoiceCall UI

### Phase 4: Polish
11. Tune confidence thresholds
12. Add re-enrollment / update flow
13. Handle edge cases (noise, multiple speakers)

---

## Files to Create/Modify

### New Files
- `backend/voice_identification.py` - Core embedding/matching logic
- `backend/routes/admin/voice.py` - Enrollment & identification endpoints
- `admin-frontend/src/pages/VoiceEnrollment.tsx` - Enrollment UI
- `admin-frontend/src/pages/VoiceEnrollment.css`

### Modified Files
- `backend/routes/admin/stt.py` - Add speaker identification option
- `backend/routes/admin/__init__.py` - Register voice router
- `backend/database/schema.py` - Add voice_enrollments table
- `backend/websocket_handlers.py` - Auto-identify speaker from voice
- `admin-frontend/src/pages/VoiceCall.tsx` - Show identified speaker
- `admin-frontend/src/api/domains/voice.ts` - Add enrollment API

---

## Dependencies

```
# requirements.txt additions
resemblyzer>=0.1.3  # Speaker embeddings (MVP)
# OR
speechbrain>=0.5.15  # ECAPA-TDNN (if upgrading)
```

---

## Open Questions

1. **Multiple embeddings vs centroid?** - Centroid is simpler but less robust to voice variation
2. **Re-enrollment cadence?** - Voices change over time; periodic refresh?
3. **Unknown speaker handling?** - Guest mode? Require enrollment?
4. **Diarization?** - Handle multiple speakers in same audio clip?
5. **Wake word speaker verification?** - "Hey Cass" should only respond to enrolled users?
