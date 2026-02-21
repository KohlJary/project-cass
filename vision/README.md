# Cass Vision System

Visual awareness for natural conversation - eye contact detection + face recognition.

## Quick Start

```bash
# Install dependencies
pip install opencv-python mediapipe numpy

# For face recognition (optional, needs cmake):
# sudo apt install cmake build-essential
# pip install face-recognition

# Run the full vision system
python cass_vision.py

# Or just attention detection
python attention_detector.py

# Or just face recognition
python face_recognition_module.py
```

## Components

| File | Purpose |
|------|---------|
| `cass_vision.py` | **Integrated system** - attention + recognition |
| `attention_detector.py` | Eye contact / gaze detection |
| `face_recognition_module.py` | Face enrollment and identification |

## How It Works

```
Camera Frame
     │
     ├──► Attention Detector (every frame, fast)
     │    └──► Are they looking at the camera?
     │    └──► How long have they been looking?
     │
     └──► Face Recognition (every N frames, slower)
          └──► Who is this person?
          └──► Are they enrolled in the database?
                    │
                    ▼
              VisionState
              - attention: looking_at_camera
              - user_name: "Kohl"
              - engaged: true → WAKE TRIGGER
```

## Events

The vision system emits events when states change:

| Event | When |
|-------|------|
| `ATTENTION_START` | Someone started looking at camera |
| `ATTENTION_END` | They looked away |
| `ENGAGED` | Sustained eye contact (1.5s) - wake trigger |
| `USER_IDENTIFIED` | Known user recognized |
| `NEW_FACE` | Unknown person detected |

## Integration Example

```python
from cass_vision import CassVision, EngagementEvent

def on_event(event, state):
    if event == EngagementEvent.ENGAGED:
        if state.is_known_user:
            print(f"Wake! {state.user_name} wants to talk")
            start_conversation(user_id=state.user_id)
        else:
            print("Wake! Unknown person")
            start_conversation(user_id=None)

vision = CassVision(on_event=on_event)

while True:
    frame = camera.read()
    state = vision.process_frame(frame)
```

## Face Enrollment

Press 'e' while running `cass_vision.py` to enroll faces:

```
$ python cass_vision.py
User ID (Enter for auto): kohl
Display name: Kohl
✓ Enrolled Kohl
```

Faces are stored in `vision/face_db/`.

## Debug View

The visualization shows:
- **Eye positions** - colored circles on iris
- **Gaze direction** - arrow showing where you're looking
- **Attention bar** - progress toward engagement threshold
- **User name** - above face if recognized
- **Events** - purple text when states change

Colors:
- 🔴 Red = Looking away
- 🟡 Yellow = Looking at camera
- 🟢 Green = Engaged / Known user
- 🟠 Orange = Unknown user

## Hardware Notes

**Desktop (current):**
- Any USB webcam
- MediaPipe needs reasonable CPU

**Pi deployment (future):**
- Pi Camera Module v2/v3
- May need Pi 4 for MediaPipe (Pi Zero 2 W is borderline)
- Consider TFLite models for better performance
