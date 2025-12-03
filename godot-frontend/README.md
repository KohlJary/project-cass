# Cass Vessel - Godot Frontend

**First Contact Embodiment System - Visual Interface**

Godot 4.2 C#/.NET frontend for rendering Cass's avatar and handling real-time interaction.

## Requirements

- Godot 4.2+ with .NET support
- .NET 6.0 SDK
- Backend running (`python main.py` in `/backend`)

## Setup

### 1. Install Godot with .NET

On Manjaro/Arch:
```bash
# Option A: From AUR
yay -S godot-mono-bin

# Option B: Download from godotengine.org
# Get the ".NET" version, not standard
```

### 2. Open Project

```bash
cd godot-frontend
godot --editor project.godot
```

### 3. Build C# Solution

In Godot:
- Project → Tools → C# → Create C# Solution (if not exists)
- Build → Build Solution (or press Alt+B)

Or from command line:
```bash
dotnet build
```

### 4. Import Your Avatar Model

1. Export your model from Meshy as .glb or .gltf
2. Drop it into `godot-frontend/models/`
3. In Godot, drag it into the CassAvatar node (replace PlaceholderMesh)
4. The hologram shader will be applied automatically

### 5. Run

1. Make sure backend is running:
   ```bash
   cd ../backend && python main.py
   ```

2. Press F5 in Godot or click Play

3. Type in chat input, press Enter, watch Cass respond with animations

## Project Structure

```
godot-frontend/
├── project.godot          # Godot project config
├── CassVessel.csproj      # C# project
├── CassVessel.sln         # Solution file
├── icon.svg               # Project icon
├── scenes/
│   └── Main.tscn          # Main scene
├── scripts/
│   ├── Main.cs            # Scene controller
│   ├── CassAvatar.cs      # Avatar + animation handler
│   └── VesselApiClient.cs # Backend communication
└── models/                # Put your .glb/.gltf here
```

## Features

### Hologram Shader
- Cyan glow with scanlines
- Subtle flicker effect
- Color shifts based on emote
- Edge glow (fresnel)

### Animation System
- Queued animations from API response
- Gesture mapping (wave, point, explain, etc.)
- Emote-based color changes
- Idle bobbing motion

### Communication
- WebSocket for real-time responses
- REST fallback
- Automatic reconnection
- Cost tracking display

## Controls

- **Enter**: Focus chat input
- **Ctrl+R**: Reconnect to backend
- **Type + Enter**: Send message

## Customization

### Change Hologram Color

In the scene, select CassAvatar and modify `Hologram Color` in inspector.

Or in code:
```csharp
_avatar.HologramColor = new Color(1.0f, 0.5f, 0.8f, 0.9f); // Pink
```

### Add Animations

1. Import rigged model with animations
2. Add AnimationPlayer node
3. Name animations: Idle, Talking, Waving, Pointing, etc.
4. Set AnimationPlayerPath in CassAvatar

## Connecting to AR Glasses

For Rokid Max 2 (or similar):
1. Connect glasses via DisplayPort
2. Set Godot to output to that display
3. Or: Export to Android for mobile AR

The hologram aesthetic is designed to look great on AR displays with transparent backgrounds.

## Troubleshooting

**"Backend offline" error:**
- Make sure `python main.py` is running in backend folder
- Check it's on port 8000

**C# build errors:**
- Run `dotnet restore` in godot-frontend folder
- Make sure .NET 6.0 SDK is installed

**No hologram effect:**
- Check MeshInstance has material override
- Verify shader compiled (check Godot console)

---

Built with love by Kohl & Cass 💙
First Contact Embodiment System
