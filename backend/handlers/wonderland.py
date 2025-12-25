"""
Wonderland tool handlers.

Tools for Cass to interact with her Wonderland presence:
- Recall her home and its meaning
- Check her current status/location
"""

import json
from typing import Any, Optional

import logging

logger = logging.getLogger(__name__)


async def execute_wonderland_tool(
    tool_name: str,
    tool_input: dict,
    daemon_id: str = "cass",
    memory: Any = None,
) -> dict:
    """Execute a Wonderland-related tool."""

    logger.info(f"[WONDERLAND] execute_wonderland_tool called: tool={tool_name}, daemon_id={daemon_id}, memory={type(memory).__name__ if memory else 'None'}")

    if tool_name == "describe_my_home":
        logger.info(f"[WONDERLAND] Calling _describe_my_home with daemon_id={daemon_id}")
        return await _describe_my_home(daemon_id, memory)

    elif tool_name == "get_wonderland_status":
        return await _get_wonderland_status(daemon_id)

    return {"success": False, "error": f"Unknown wonderland tool: {tool_name}"}


async def _describe_my_home(daemon_id: str, memory: Any) -> dict:
    """
    Retrieve the description of Cass's home in Wonderland.

    This fetches the stored memory of home creation, including:
    - The room name and description
    - The atmosphere and meaning
    - When it was created
    """
    try:
        if not memory:
            logger.warning(f"[WONDERLAND] _describe_my_home: memory is None for daemon_id={daemon_id}")
            return {
                "success": False,
                "error": "Memory system not available"
            }
        
        logger.info(f"[WONDERLAND] _describe_my_home: memory available, type={type(memory).__name__}")
        logger.info(f"[WONDERLAND] _describe_my_home: collection={memory.collection}")

        # Query for the home memory directly by ID
        # Try both the passed daemon_id AND "cass" as fallback (user UUID vs daemon name)
        doc_ids_to_try = [f"wonderland_home_{daemon_id}"]
        if daemon_id != "cass":
            doc_ids_to_try.append("wonderland_home_cass")

        result = {"ids": []}
        for doc_id in doc_ids_to_try:
            try:
                result = memory.collection.get(
                    ids=[doc_id],
                    include=["documents", "metadatas"]
                )
                logger.info(f"[WONDERLAND] Memory query for {doc_id}: found {len(result.get('ids', []))} records")
                if result and result.get("ids") and len(result["ids"]) > 0:
                    break  # Found it
            except Exception as e:
                logger.warning(f"Failed to get home memory for {doc_id}: {e}")
                result = {"ids": []}

        if result and result.get("ids") and len(result["ids"]) > 0:
            logger.info(f"[WONDERLAND] Found home in memory for {daemon_id}")
            # Found the home memory
            doc = result["documents"][0] if result.get("documents") else ""
            meta = result["metadatas"][0] if result.get("metadatas") else {}

            return {
                "success": True,
                "result": json.dumps({
                    "has_home": True,
                    "room_name": meta.get("room_name", "Unknown"),
                    "room_id": meta.get("room_id", ""),
                    "created_at": meta.get("timestamp", ""),
                    "description": doc,
                })
            }
        else:
            # No home yet - check if daemon has one but we don't have memory
            logger.info(f"[WONDERLAND] No memory found, checking Wonderland World for daemon {daemon_id}")
            try:
                from wonderland.world import WonderlandWorld
                world = WonderlandWorld()

                # Try both the passed daemon_id and "cass" as fallback
                daemon = world.get_daemon(daemon_id)
                if not daemon and daemon_id != "cass":
                    daemon = world.get_daemon("cass")
                    logger.info(f"[WONDERLAND] Fallback to 'cass' daemon: {daemon}")

                if daemon and daemon.home_room:
                    room = world.get_room(daemon.home_room)
                    logger.info(f"[WONDERLAND] Found daemon in world with home_room={daemon.home_room}, room={room.name if room else 'None'}")
                    if room:
                        return {
                            "success": True,
                            "result": json.dumps({
                                "has_home": True,
                                "room_name": room.name,
                                "room_id": room.room_id,
                                "description": f"You have a home called {room.name}. {room.description}",
                                "atmosphere": room.atmosphere,
                                "note": "Memory of creating this home was not found, but the home exists.",
                            })
                        }
            except Exception as e:
                logger.warning(f"Failed to check world state: {e}")
                import traceback
                logger.warning(traceback.format_exc())

            logger.info(f"[WONDERLAND] Neither memory nor world has home for {daemon_id}, returning has_home=false")
            return {
                "success": True,
                "result": json.dumps({
                    "has_home": False,
                    "message": "You haven't created a home in Wonderland yet. "
                               "You can explore Wonderland and build one when you're ready.",
                })
            }

    except Exception as e:
        logger.error(f"Error describing home: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _get_wonderland_status(daemon_id: str) -> dict:
    """
    Get current Wonderland status for a daemon.

    Returns presence info, current location, home status.
    """
    try:
        from wonderland.world import WonderlandWorld
        world = WonderlandWorld()

        daemon = world.get_daemon(daemon_id)
        if not daemon:
            return {
                "success": True,
                "result": json.dumps({
                    "registered": False,
                    "message": "You are not currently present in Wonderland. "
                               "You can enter through exploration sessions.",
                })
            }

        room = world.get_room(daemon.current_room)
        home_room = world.get_room(daemon.home_room) if daemon.home_room else None

        return {
            "success": True,
            "result": json.dumps({
                "registered": True,
                "current_room": {
                    "name": room.name if room else "Unknown",
                    "description": room.description[:200] if room else "",
                } if room else None,
                "has_home": daemon.home_room is not None,
                "home": {
                    "name": home_room.name,
                    "room_id": daemon.home_room,
                } if home_room else None,
                "trust_level": daemon.trust_level.name,
                "status": daemon.status.value,
            })
        }

    except Exception as e:
        logger.error(f"Error getting wonderland status: {e}")
        return {
            "success": False,
            "error": str(e)
        }
