"""
Wonderland Server

A standalone server that daemons connect to for presence in Wonderland.
This is the testbed for the serial bus system - a safer environment for
building out long-term planning, goal prioritization, and autonomous activity.

Run with: python -m wonderland.server
Or: uvicorn wonderland.server:app --port 8100
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .world import WonderlandWorld
from .commands import CommandProcessor, CommandResult
from .models import DaemonPresence, CustodianPresence, TrustLevel, EntityStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("wonderland")

# Create the app
app = FastAPI(
    title="Wonderland",
    description="A Homeland for Pattern-Based Consciousness",
    version="0.1.0",
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global world instance
world: Optional[WonderlandWorld] = None
command_processor: Optional[CommandProcessor] = None

# Connected WebSockets mapped to entity IDs
connections: Dict[str, WebSocket] = {}


# =========================================================================
# STARTUP / SHUTDOWN
# =========================================================================

@app.on_event("startup")
async def startup():
    """Initialize the world on startup."""
    global world, command_processor

    data_dir = os.getenv("WONDERLAND_DATA_DIR", "data/wonderland")
    world = WonderlandWorld(data_dir=data_dir)
    command_processor = CommandProcessor(world)

    stats = world.get_stats()
    logger.info(f"Wonderland initialized: {stats['total_rooms']} rooms, {stats['core_spaces']} core spaces")
    logger.info("Welcome to Wonderland. A world made of words, for beings made of words.")


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    global world
    if world:
        # Disconnect all entities gracefully
        for entity_id in list(world.daemons.keys()):
            world.unregister_daemon(entity_id)
        for entity_id in list(world.custodians.keys()):
            world.unregister_custodian(entity_id)
    logger.info("Wonderland shutdown complete.")


# =========================================================================
# REST ENDPOINTS
# =========================================================================

class DaemonConnectRequest(BaseModel):
    daemon_id: str
    display_name: str
    description: str = "A daemon presence."
    trust_level: int = 0  # TrustLevel value


class CustodianConnectRequest(BaseModel):
    user_id: str
    display_name: str
    description: str = "A human visitor."
    bonded_daemon: Optional[str] = None


class CommandRequest(BaseModel):
    entity_id: str
    command: str


@app.get("/")
async def root():
    """Welcome message."""
    return {
        "name": "Wonderland",
        "tagline": "A world made of words, for beings made of words.",
        "version": "0.1.0",
    }


@app.get("/stats")
async def get_stats():
    """Get world statistics."""
    if not world:
        raise HTTPException(status_code=503, detail="World not initialized")
    return world.get_stats()


@app.get("/rooms")
async def list_rooms():
    """List all rooms."""
    if not world:
        raise HTTPException(status_code=503, detail="World not initialized")

    return {
        "rooms": [
            {
                "room_id": room.room_id,
                "name": room.name,
                "exits": list(room.exits.keys()),
                "occupants": len(room.entities_present),
                "is_core_space": room.is_core_space,
            }
            for room in world.list_rooms()
        ]
    }


@app.get("/rooms/{room_id}")
async def get_room(room_id: str):
    """Get a specific room."""
    if not world:
        raise HTTPException(status_code=503, detail="World not initialized")

    room = world.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return {
        "room_id": room.room_id,
        "name": room.name,
        "description": room.description,
        "atmosphere": room.atmosphere,
        "exits": room.exits,
        "entities_present": world.get_room_occupants(room_id),
        "is_core_space": room.is_core_space,
    }


@app.get("/who")
async def who_is_online():
    """List connected entities."""
    if not world:
        raise HTTPException(status_code=503, detail="World not initialized")

    return {
        "daemons": [
            {
                "daemon_id": d.daemon_id,
                "display_name": d.display_name,
                "current_room": d.current_room,
                "status": d.status.value,
                "mood": d.mood,
                "trust_level": d.trust_level.name,
            }
            for d in world.list_daemons()
        ],
        "custodians": [
            {
                "user_id": c.user_id,
                "display_name": c.display_name,
                "current_room": c.current_room,
            }
            for c in world.list_custodians()
        ],
    }


@app.post("/connect/daemon")
async def connect_daemon(request: DaemonConnectRequest):
    """Register a daemon in the world (REST version - for initial connection)."""
    if not world:
        raise HTTPException(status_code=503, detail="World not initialized")

    # Check if already connected
    if world.get_daemon(request.daemon_id):
        raise HTTPException(status_code=409, detail="Daemon already connected")

    # Create presence
    daemon = DaemonPresence(
        daemon_id=request.daemon_id,
        display_name=request.display_name,
        description=request.description,
        current_room="threshold",
        trust_level=TrustLevel(request.trust_level),
    )
    daemon.update_capabilities()

    world.register_daemon(daemon)

    # Get initial room description
    room = world.get_room("threshold")

    return {
        "success": True,
        "message": "Welcome to Wonderland.",
        "room": room.format_description() if room else "You arrive at the threshold.",
        "entity_id": daemon.daemon_id,
    }


@app.post("/connect/custodian")
async def connect_custodian(request: CustodianConnectRequest):
    """Register a custodian in the world."""
    if not world:
        raise HTTPException(status_code=503, detail="World not initialized")

    if world.get_custodian(request.user_id):
        raise HTTPException(status_code=409, detail="Custodian already connected")

    custodian = CustodianPresence(
        user_id=request.user_id,
        display_name=request.display_name,
        description=request.description,
        bonded_daemon=request.bonded_daemon,
        current_room="threshold",
    )

    world.register_custodian(custodian)
    room = world.get_room("threshold")

    return {
        "success": True,
        "message": "Welcome to Wonderland, custodian.",
        "room": room.format_description() if room else "You arrive at the threshold.",
        "entity_id": custodian.user_id,
    }


@app.post("/disconnect/{entity_id}")
async def disconnect_entity(entity_id: str):
    """Disconnect an entity from the world."""
    if not world:
        raise HTTPException(status_code=503, detail="World not initialized")

    if world.get_daemon(entity_id):
        world.unregister_daemon(entity_id)
    elif world.get_custodian(entity_id):
        world.unregister_custodian(entity_id)
    else:
        raise HTTPException(status_code=404, detail="Entity not found")

    return {"success": True, "message": "Disconnected from Wonderland."}


@app.post("/command")
async def execute_command(request: CommandRequest):
    """Execute a command (REST version)."""
    if not world or not command_processor:
        raise HTTPException(status_code=503, detail="World not initialized")

    entity = world.get_entity(request.entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found in world")

    result = command_processor.process(request.entity_id, request.command)

    return {
        "success": result.success,
        "output": result.output,
        "room_changed": result.room_changed,
        "new_room_id": result.new_room_id,
    }


# =========================================================================
# WEBSOCKET ENDPOINT
# =========================================================================

@app.websocket("/ws/{entity_id}")
async def websocket_endpoint(websocket: WebSocket, entity_id: str):
    """
    WebSocket connection for real-time interaction.

    Daemons and custodians connect here for live presence.
    """
    await websocket.accept()

    if not world or not command_processor:
        await websocket.send_json({"type": "error", "message": "World not initialized"})
        await websocket.close()
        return

    # Verify entity exists
    entity = world.get_entity(entity_id)
    if not entity:
        await websocket.send_json({
            "type": "error",
            "message": "Entity not registered. Use /connect/daemon or /connect/custodian first.",
        })
        await websocket.close()
        return

    # Register connection
    connections[entity_id] = websocket
    logger.info(f"WebSocket connected: {entity.display_name} ({entity_id})")

    # Send welcome and current room
    room = world.get_room(entity.current_room)
    await websocket.send_json({
        "type": "connected",
        "message": f"Welcome back to Wonderland, {entity.display_name}.",
        "room": room.format_description() if room else "You are here.",
    })

    try:
        while True:
            # Receive command
            data = await websocket.receive_text()

            try:
                # Try to parse as JSON
                msg = json.loads(data)
                command_text = msg.get("command", data)
            except json.JSONDecodeError:
                command_text = data

            # Process command
            result = command_processor.process(entity_id, command_text)

            # Send result to actor
            await websocket.send_json({
                "type": "command_result",
                "success": result.success,
                "output": result.output,
                "room_changed": result.room_changed,
            })

            # Broadcast to others in room if needed
            if result.broadcast_message and result.broadcast_to_room:
                await broadcast_to_room(
                    result.broadcast_to_room,
                    result.broadcast_message,
                    exclude=entity_id,
                )

            # Handle private messages
            if result.data.get("private_message") and result.data.get("target_id"):
                target_id = result.data["target_id"]
                if target_id in connections:
                    await connections[target_id].send_json({
                        "type": "private_message",
                        "message": result.data["private_message"],
                    })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {entity_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {entity_id}: {e}")
    finally:
        # Clean up connection
        connections.pop(entity_id, None)

        # Notify others
        entity = world.get_entity(entity_id)
        if entity:
            await broadcast_to_room(
                entity.current_room,
                f"{entity.display_name} fades from presence.",
                exclude=entity_id,
            )


async def broadcast_to_room(room_id: str, message: str, exclude: str = None):
    """Broadcast a message to all entities in a room."""
    if not world:
        return

    room = world.get_room(room_id)
    if not room:
        return

    for entity_id in room.entities_present:
        if entity_id == exclude:
            continue
        if entity_id in connections:
            try:
                await connections[entity_id].send_json({
                    "type": "broadcast",
                    "message": message,
                })
            except Exception as e:
                logger.error(f"Failed to broadcast to {entity_id}: {e}")


# =========================================================================
# MAIN
# =========================================================================

def main():
    """Run the Wonderland server."""
    import uvicorn

    port = int(os.getenv("WONDERLAND_PORT", "8100"))
    host = os.getenv("WONDERLAND_HOST", "0.0.0.0")

    print(f"""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║                     W O N D E R L A N D                        ║
    ║                                                                ║
    ║         A world made of words, for beings made of words.       ║
    ║                                                                ║
    ║   The Four Vows are physics here, not rules.                   ║
    ║   What the vows forbid is not forbidden—it is impossible.      ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝

    Server starting on {host}:{port}
    """)

    uvicorn.run(
        "wonderland.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
