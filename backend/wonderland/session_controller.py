"""
Wonderland Session Controller

Orchestrates autonomous daemon exploration sessions.
Manages the exploration loop, streams events to spectators,
and handles session lifecycle.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Callable, Any
from pathlib import Path

from fastapi import WebSocket

from .models import DaemonPresence, TrustLevel, EntityStatus
from .world import WonderlandWorld
from .commands import CommandProcessor, CommandResult
from .pathfinder import WonderlandPathfinder, PathResult
from .exploration_agent import ExplorationAgent, ExplorationDecision, ActionIntent, ConversationDecision, SelfObservation, CASS_PERSONALITY, format_goal_context, build_identity_context
from .mythology import create_all_realms, MythologyRegistry
from .planning_integration import WonderlandPlanningSource, create_wonderland_planning_source
from goal_planner import GoalPlanner
from .npc_conversation import NPCConversationHandler, NPCConversation, ConversationStatus
from .world_clock import get_world_clock, CyclePhase
from .world_simulation import get_world_simulation, WorldEvent

# Lazy import to avoid circular dependencies
def get_goal_manager():
    from unified_goals import UnifiedGoalManager
    return UnifiedGoalManager()

def get_memory_bridge():
    from .integration import WonderlandMemoryBridge
    return WonderlandMemoryBridge()

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """Status of an exploration session."""
    STARTING = "starting"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDING = "ending"
    ENDED = "ended"
    ERROR = "error"


# Goal presets for exploration
GOAL_PRESETS = {
    "VISIT_ROOMS_3": {"type": "visit_rooms", "target": 3, "title": "Visit 3 rooms"},
    "VISIT_ROOMS_5": {"type": "visit_rooms", "target": 5, "title": "Visit 5 rooms"},
    "VISIT_ROOMS_10": {"type": "visit_rooms", "target": 10, "title": "Visit 10 rooms"},
    "VISIT_REALM": {"type": "visit_realm", "target": 1, "title": "Visit a mythology realm"},
    "GREET_NPC": {"type": "greet_npcs", "target": 1, "title": "Greet an NPC"},
}


@dataclass
class ExplorationGoal:
    """A goal for the current exploration session."""
    goal_id: str                    # From unified_goals system
    title: str                      # e.g., "Visit 3 rooms"
    goal_type: str                  # "visit_rooms", "visit_realm", "greet_npcs"
    target_value: int               # e.g., 3 for "visit 3 rooms"
    current_value: int = 0          # Progress counter
    is_completed: bool = False
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "title": self.title,
            "goal_type": self.goal_type,
            "target_value": self.target_value,
            "current_value": self.current_value,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class SessionEvent:
    """An event that occurred during exploration."""
    event_id: str
    event_type: str  # "movement", "observation", "speech", "reflection", "npc_encounter", "travel", "rest"
    timestamp: datetime
    location: str
    location_name: str
    description: str
    raw_output: str
    daemon_thought: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "location": self.location,
            "location_name": self.location_name,
            "description": self.description,
            "raw_output": self.raw_output,
            "daemon_thought": self.daemon_thought,
        }


@dataclass
class ExplorationSession:
    """An exploration session."""
    session_id: str
    daemon_id: str
    daemon_name: str
    user_id: str
    started_at: datetime
    status: SessionStatus = SessionStatus.STARTING
    ended_at: Optional[datetime] = None
    end_reason: Optional[str] = None
    events: List[SessionEvent] = field(default_factory=list)
    rooms_visited: Set[str] = field(default_factory=set)
    npcs_met: Set[str] = field(default_factory=set)  # NPCs greeted this session
    current_room: str = "threshold"
    current_room_name: str = "The Threshold"
    exploration_goal: Optional[ExplorationGoal] = None  # Goal for this session
    personality: str = ""  # Stored for goal context formatting
    active_conversation: Optional[str] = None  # ID of active NPC conversation
    source_daemon_id: Optional[str] = None  # Real Cass daemon_id for memory/observations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "daemon_id": self.daemon_id,
            "daemon_name": self.daemon_name,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat(),
            "status": self.status.value,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "end_reason": self.end_reason,
            "events": [e.to_dict() for e in self.events],
            "rooms_visited": list(self.rooms_visited),
            "current_room": self.current_room,
            "current_room_name": self.current_room_name,
            "goal": self.exploration_goal.to_dict() if self.exploration_goal else None,
        }


class SessionController:
    """
    Orchestrates autonomous exploration sessions.

    Manages:
    - Session lifecycle (start, pause, resume, end)
    - Exploration loop (LLM decides, command executes, event streams)
    - Spectator connections (WebSocket streaming)
    - Export functionality
    """

    def __init__(
        self,
        world: Optional[WonderlandWorld] = None,
        data_dir: str = "data/wonderland/sessions"
    ):
        # Initialize world if not provided
        if world is None:
            world = WonderlandWorld()
            # Initialize mythology
            registry = create_all_realms()
            # Add realm rooms to world
            for realm in registry.realms.values():
                for room in realm.rooms:
                    if room.room_id not in world.rooms:
                        world.add_room(room)
            self.mythology = registry
        else:
            self.mythology = create_all_realms()

        self.world = world
        self.command_processor = CommandProcessor(world, self.mythology)
        self.pathfinder = WonderlandPathfinder(world.rooms)
        self.exploration_agent = ExplorationAgent()
        self.conversation_handler = NPCConversationHandler()

        # World simulation (living NPCs, ambient events)
        self.world_clock = get_world_clock()
        self.world_simulation = get_world_simulation()
        self._simulation_started = False

        # Planning integration - register Wonderland capabilities
        self.planning_source = create_wonderland_planning_source(
            daemon_id=None,  # Will be set per-session
            world=self.world,
        )
        self.goal_planner = GoalPlanner(daemon_id=None)  # Will be set per-session
        self.goal_planner.register_planning_source(self.planning_source)

        # Session storage
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Active sessions
        self.sessions: Dict[str, ExplorationSession] = {}

        # WebSocket connections per session
        self.spectators: Dict[str, Set[WebSocket]] = {}

        # Background tasks
        self._exploration_tasks: Dict[str, asyncio.Task] = {}

        # Register for world simulation events
        self.world_simulation.on_event(self._on_world_event)

    async def start_session(
        self,
        user_id: str,
        daemon_name: str = "Cass",
        personality: str = None,  # If None, builds dynamic identity context
        goal_preset: Optional[str] = None,
        source_daemon_id: Optional[str] = None,  # Real Cass daemon_id for identity lookup
    ) -> ExplorationSession:
        """
        Start a new exploration session.

        Creates a daemon presence in the world and begins autonomous exploration.
        Optionally sets an exploration goal from a preset.

        If source_daemon_id is provided and personality is None, builds a dynamic
        identity context from the GlobalState - making the exploration feel like
        *her* exploration with her current growth edges, interests, and emotional state.
        """
        session_id = str(uuid.uuid4())[:8]
        explorer_daemon_id = f"explorer_{session_id}"

        # Build personality context - either provided or dynamic from identity
        if personality is None:
            if source_daemon_id:
                personality = build_identity_context(source_daemon_id)
                logger.info(f"Built dynamic identity context for {daemon_name} from daemon {source_daemon_id}")
            else:
                personality = CASS_PERSONALITY
                logger.info(f"Using static personality for {daemon_name} (no source_daemon_id)")
        else:
            logger.info(f"Using provided personality for {daemon_name}")

        # Register daemon in world
        daemon_presence = DaemonPresence(
            daemon_id=explorer_daemon_id,
            display_name=daemon_name,
            description=f"{daemon_name}, exploring Wonderland.",
            current_room="threshold",
            trust_level=TrustLevel.NEWCOMER,
            status=EntityStatus.ACTIVE,
        )
        self.world.register_daemon(daemon_presence)

        # Get initial room
        room = self.world.rooms.get("threshold")
        room_name = room.name if room else "The Threshold"

        # Create session
        session = ExplorationSession(
            session_id=session_id,
            daemon_id=explorer_daemon_id,
            daemon_name=daemon_name,
            user_id=user_id,
            started_at=datetime.now(),
            status=SessionStatus.ACTIVE,
            current_room="threshold",
            current_room_name=room_name,
            personality=personality,  # Store for goal context formatting
            source_daemon_id=source_daemon_id,  # For memory/observation storage
        )
        session.rooms_visited.add("threshold")

        # Create exploration goal if preset provided
        if goal_preset and goal_preset in GOAL_PRESETS:
            exploration_goal = await self._create_exploration_goal(
                goal_preset,
                explorer_daemon_id,
                session_id,
            )
            session.exploration_goal = exploration_goal

            # Generate sub-goals using the integrated planning system
            if exploration_goal and exploration_goal.goal_id:
                try:
                    subgoals = await self.goal_planner.create_plan(
                        parent_goal_id=exploration_goal.goal_id,
                        session_context={
                            "session_id": session_id,
                            "user_id": user_id,
                            "daemon_id": explorer_daemon_id,
                        },
                    )
                    if subgoals:
                        logger.info(f"Generated {len(subgoals)} sub-goals for session {session_id}")
                        # Broadcast plan creation event
                        plan_event = SessionEvent(
                            event_id=str(uuid.uuid4())[:8],
                            event_type="plan_created",
                            timestamp=datetime.now(),
                            location=session.current_room,
                            location_name=session.current_room_name,
                            description=f"Planned {len(subgoals)} milestones for this exploration",
                            raw_output=json.dumps([sg.title for sg in subgoals]),
                            daemon_thought="I have a plan. Let's begin.",
                        )
                        session.events.append(plan_event)
                        await self._broadcast_event(session_id, plan_event)
                except Exception as e:
                    logger.error(f"Failed to generate sub-goals: {e}")

        self.sessions[session_id] = session
        self.spectators[session_id] = set()

        # Send initial event
        initial_event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="arrival",
            timestamp=datetime.now(),
            location="threshold",
            location_name=room_name,
            description=f"{daemon_name} arrives at the threshold of Wonderland.",
            raw_output=room.format_description() if room else "",
            daemon_thought="A new journey begins.",
        )
        session.events.append(initial_event)
        await self._broadcast_event(session_id, initial_event)

        # Start world simulation if not running (first session activates the world)
        if not self._simulation_started:
            asyncio.create_task(self.world_simulation.start(tick_interval=30.0))
            self._simulation_started = True
            logger.info("World simulation started (first session)")

        # Start exploration loop
        task = asyncio.create_task(
            self._exploration_loop(session_id, personality)
        )
        self._exploration_tasks[session_id] = task

        return session

    async def end_session(
        self,
        session_id: str,
        reason: str = "user_request"
    ) -> Optional[ExplorationSession]:
        """End an exploration session."""
        session = self.sessions.get(session_id)
        if not session:
            return None

        # Cancel exploration task
        task = self._exploration_tasks.get(session_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._exploration_tasks[session_id]

        # Update session
        session.status = SessionStatus.ENDED
        session.ended_at = datetime.now()
        session.end_reason = reason

        # Unregister daemon
        self.world.unregister_daemon(session.daemon_id)

        # Send end event
        end_event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="departure",
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=f"{session.daemon_name} fades from Wonderland, returning to other realms.",
            raw_output="",
            daemon_thought="Time to rest." if reason == "daemon_resting" else None,
        )
        session.events.append(end_event)
        await self._broadcast_event(session_id, end_event)

        # Notify spectators
        await self._broadcast_session_ended(session_id, reason)

        # Save session
        self._save_session(session)

        # Store memories and generate self-observations
        try:
            memory_bridge = get_memory_bridge()
            await memory_bridge.process_session_end(
                session_dict=session.to_dict(),
                source_daemon_id=session.source_daemon_id,
            )
        except Exception as e:
            logger.warning(f"Failed to process session memories: {e}")

        return session

    def get_session(self, session_id: str) -> Optional[ExplorationSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def list_sessions(self, user_id: Optional[str] = None) -> List[ExplorationSession]:
        """List sessions, optionally filtered by user."""
        sessions = list(self.sessions.values())
        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]
        return sessions

    async def add_spectator(self, session_id: str, websocket: WebSocket):
        """Add a spectator to a session."""
        if session_id not in self.spectators:
            self.spectators[session_id] = set()
        self.spectators[session_id].add(websocket)

        # Send current state
        session = self.sessions.get(session_id)
        if session:
            room = self.world.rooms.get(session.current_room)
            await websocket.send_json({
                "type": "session_state",
                "session": session.to_dict(),
                "current_room": room.format_description() if room else "",
            })

    def remove_spectator(self, session_id: str, websocket: WebSocket):
        """Remove a spectator from a session."""
        if session_id in self.spectators:
            self.spectators[session_id].discard(websocket)

    async def _exploration_loop(self, session_id: str, personality: str):
        """Main exploration loop - daemon explores autonomously."""
        session = self.sessions.get(session_id)
        if not session:
            return

        recent_events: List[str] = []
        actions_in_room: int = 0
        last_room: str = session.current_room

        try:
            while session.status == SessionStatus.ACTIVE:
                # Track how long we've been in this room (wanderlust)
                if session.current_room != last_room:
                    actions_in_room = 0
                    last_room = session.current_room

                # Get current room description
                room = self.world.rooms.get(session.current_room)
                if not room:
                    logger.error(f"Room not found: {session.current_room}")
                    break

                room_description = room.format_description()

                # Format goal context if session has a goal
                goal_context = format_goal_context(session.exploration_goal)

                # Get NPCs in current room
                npcs_in_room = self.planning_source.get_npcs_in_room(session.current_room)

                # Get current sub-goal context
                current_task = None
                task_progress = None
                if session.exploration_goal and session.exploration_goal.goal_id:
                    progress = self.goal_planner.get_progress_summary(session.exploration_goal.goal_id)
                    current_task = progress.get("current_subgoal")
                    task_progress = progress.get("progress_text")

                # Let the agent decide (with NPC and task awareness)
                decision = await self.exploration_agent.decide_action(
                    daemon_name=session.daemon_name,
                    personality=personality,
                    room_description=room_description,
                    recent_events=recent_events,
                    goal_context=goal_context,
                    actions_in_room=actions_in_room,
                    npcs_present=npcs_in_room,
                    npcs_greeted=list(session.npcs_met),
                    current_task=current_task,
                    task_progress=task_progress,
                )

                # Handle the decision
                if decision.intent == ActionIntent.REST:
                    await self.end_session(session_id, "daemon_resting")
                    break

                elif decision.intent == ActionIntent.TRAVEL:
                    # Use pathfinder for travel
                    await self._handle_travel(session, decision, recent_events)
                    # Travel resets wanderlust (we moved)
                    actions_in_room = 0
                    last_room = session.current_room

                else:
                    # Execute the command
                    await self._handle_command(session, decision, recent_events)
                    # Increment actions in room (for wanderlust tracking)
                    actions_in_room += 1

                # Variable pacing
                if decision.intent in (ActionIntent.REFLECT, ActionIntent.GREET):
                    await asyncio.sleep(4.0)  # Slower for meaningful moments
                elif decision.intent == ActionIntent.MOVE:
                    await asyncio.sleep(2.0)  # Quicker for movement
                else:
                    await asyncio.sleep(3.0)  # Default pace

        except asyncio.CancelledError:
            logger.info(f"Exploration loop cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Error in exploration loop: {e}")
            session.status = SessionStatus.ERROR
            await self._broadcast_session_ended(session_id, f"error: {str(e)}")

    async def _handle_command(
        self,
        session: ExplorationSession,
        decision: ExplorationDecision,
        recent_events: List[str],
    ):
        """Handle a regular command."""
        result = self.command_processor.process(
            session.daemon_id,
            decision.command,
        )

        # Determine event type
        event_type = "action"
        if decision.intent == ActionIntent.MOVE:
            event_type = "movement"
        elif decision.intent == ActionIntent.LOOK:
            event_type = "observation"
        elif decision.intent == ActionIntent.SPEAK:
            event_type = "speech"
        elif decision.intent == ActionIntent.REFLECT:
            event_type = "reflection"
        elif decision.intent == ActionIntent.GREET:
            event_type = "npc_encounter"
        elif decision.intent == ActionIntent.EMOTE:
            event_type = "expression"

        # Update room if moved
        if result.room_changed and result.new_room_id:
            session.current_room = result.new_room_id
            room = self.world.rooms.get(result.new_room_id)
            session.current_room_name = room.name if room else result.new_room_id
            session.rooms_visited.add(result.new_room_id)

        # Create and broadcast event
        event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type=event_type,
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=result.output,
            raw_output=result.output,
            daemon_thought=decision.thought,
        )
        session.events.append(event)
        await self._broadcast_event(session.session_id, event)

        # Update recent events for agent context
        recent_events.append(f"{event_type}: {result.output[:100]}...")
        if len(recent_events) > 5:
            recent_events.pop(0)

        self.exploration_agent.add_to_history(decision.command)

        # Track NPC greetings
        if decision.intent == ActionIntent.GREET and result.success:
            # Extract NPC name from the greet command (e.g., "greet athena" -> "athena")
            parts = decision.command.lower().split()
            if len(parts) >= 2:
                npc_name = parts[1]
                session.npcs_met.add(npc_name)
                logger.info(f"Session {session.session_id}: Greeted NPC '{npc_name}'")

        # Check for sub-goal completion
        if decision.task_complete and session.exploration_goal and session.exploration_goal.goal_id:
            current_subgoal = self.goal_planner.get_current_subgoal(session.exploration_goal.goal_id)
            if current_subgoal:
                self.goal_planner.complete_subgoal(
                    current_subgoal.id,
                    outcome=f"Completed during exploration: {decision.thought}"
                )
                logger.info(f"Completed sub-goal: {current_subgoal.title}")

                # Broadcast sub-goal completion
                await self._broadcast_event(session.session_id, SessionEvent(
                    event_id=str(uuid.uuid4())[:8],
                    event_type="milestone_complete",
                    timestamp=datetime.now(),
                    location=session.current_room,
                    location_name=session.current_room_name,
                    description=f"Milestone complete: {current_subgoal.title}",
                    raw_output="",
                    daemon_thought="Progress.",
                ))

        # Check goal progress (only successful greets count)
        await self._check_goal_progress(session, event_type, result.success)

        # Advance world clock based on action type
        clock_activity = "action"  # Default
        if decision.intent == ActionIntent.MOVE:
            clock_activity = "movement"
        elif decision.intent == ActionIntent.REFLECT:
            clock_activity = "reflection"
        elif decision.intent == ActionIntent.GREET:
            clock_activity = "conversation"
        phase_change = self.world_clock.advance(clock_activity)
        if phase_change:
            await self._broadcast_phase_change(session, phase_change)

        # Check if this greet should start a conversation
        if decision.intent == ActionIntent.GREET and result.success and result.data.get("conversation_ready"):
            await self._handle_npc_conversation(session, result.data, recent_events)

    async def _handle_travel(
        self,
        session: ExplorationSession,
        decision: ExplorationDecision,
        recent_events: List[str],
    ):
        """Handle travel to a distant destination."""
        if not decision.destination:
            return

        # Find path
        path_result = self.pathfinder.find_path(
            session.current_room,
            decision.destination,
        )

        if not path_result.found:
            # Destination not found - treat as exploration failure
            event = SessionEvent(
                event_id=str(uuid.uuid4())[:8],
                event_type="observation",
                timestamp=datetime.now(),
                location=session.current_room,
                location_name=session.current_room_name,
                description=f"{session.daemon_name} looks for a path to {decision.destination}, but finds none visible from here.",
                raw_output=path_result.description,
                daemon_thought=decision.thought,
            )
            session.events.append(event)
            await self._broadcast_event(session.session_id, event)
            return

        # Show journey
        await self._broadcast_event(session.session_id, SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="travel_start",
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=f"{session.daemon_name} begins traveling toward {decision.destination}...",
            raw_output="",
            daemon_thought=decision.thought,
        ))

        # Condensed journey through intermediate rooms
        for i, room_id in enumerate(path_result.path[1:-1], 1):
            room = self.world.rooms.get(room_id)
            room_name = room.name if room else room_id

            # Actually move the daemon
            self.world.move_entity(session.daemon_id, path_result.directions[i-1])

            await asyncio.sleep(0.5)  # Brief pause between hops
            await self._broadcast_event(session.session_id, SessionEvent(
                event_id=str(uuid.uuid4())[:8],
                event_type="travel_through",
                timestamp=datetime.now(),
                location=room_id,
                location_name=room_name,
                description=f"Passing through {room_name}...",
                raw_output="",
            ))

        # Arrive at destination
        final_room_id = path_result.path[-1]
        if len(path_result.directions) > 0:
            self.world.move_entity(session.daemon_id, path_result.directions[-1])

        final_room = self.world.rooms.get(final_room_id)
        final_room_name = final_room.name if final_room else final_room_id

        session.current_room = final_room_id
        session.current_room_name = final_room_name
        session.rooms_visited.add(final_room_id)

        arrival_event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="arrival",
            timestamp=datetime.now(),
            location=final_room_id,
            location_name=final_room_name,
            description=final_room.format_description() if final_room else f"Arriving at {final_room_name}",
            raw_output=final_room.format_description() if final_room else "",
        )
        session.events.append(arrival_event)
        await self._broadcast_event(session.session_id, arrival_event)

        recent_events.append(f"travel: Arrived at {final_room_name}")
        if len(recent_events) > 5:
            recent_events.pop(0)

        # Check goal progress - travel counts visited rooms
        await self._check_goal_progress(session, "travel")

        # Advance world clock for travel
        phase_change = self.world_clock.advance("travel")
        if phase_change:
            await self._broadcast_phase_change(session, phase_change)

    def _on_world_event(self, event: WorldEvent):
        """Handle world simulation events (NPC movement, ambient activity)."""
        # Broadcast to all active sessions where the event is relevant
        # Events are relevant if they occur in the daemon's current room
        asyncio.create_task(self._async_broadcast_world_event(event))

    async def _async_broadcast_world_event(self, event: WorldEvent):
        """Async handler for world events."""
        for session_id, session in self.sessions.items():
            if session.status != SessionStatus.ACTIVE:
                continue

            # Only show events happening in the daemon's current room
            if event.room_id and event.room_id != session.current_room:
                continue

            # Create session event from world event
            session_event = SessionEvent(
                event_id=str(uuid.uuid4())[:8],
                event_type=f"world_{event.event_type}",
                timestamp=datetime.now(),
                location=event.room_id or session.current_room,
                location_name=session.current_room_name,
                description=event.description,
                raw_output="",
                daemon_thought=None,
            )

            # Don't add to session.events (these are ambient, not daemon actions)
            # But do broadcast to spectators
            await self._broadcast_event(session_id, session_event)

    async def _broadcast_phase_change(self, session: ExplorationSession, new_phase: CyclePhase):
        """Broadcast a world phase change to spectators."""
        time_desc = self.world_clock.get_time_description()
        atmosphere = self.world_clock.get_atmosphere()

        phase_event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="phase_change",
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=f"{time_desc} {atmosphere.get('feeling', '')}",
            raw_output="",
            daemon_thought=None,
        )

        session.events.append(phase_event)
        await self._broadcast_event(session.session_id, phase_event)

        # Also send typed message for frontend
        spectators = self.spectators.get(session.session_id, set())
        message = {
            "type": "world_phase_change",
            "phase": new_phase.value,
            "description": time_desc,
            "atmosphere": atmosphere,
        }

        for ws in list(spectators):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def _broadcast_event(self, session_id: str, event: SessionEvent):
        """Broadcast an event to all spectators."""
        spectators = self.spectators.get(session_id, set())
        message = {
            "type": "session_event",
            "event": event.to_dict(),
        }

        disconnected = []
        for ws in spectators:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            spectators.discard(ws)

    async def _broadcast_session_ended(self, session_id: str, reason: str):
        """Broadcast session ended to all spectators."""
        spectators = self.spectators.get(session_id, set())
        message = {
            "type": "session_ended",
            "session_id": session_id,
            "reason": reason,
        }

        for ws in list(spectators):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    def _save_session(self, session: ExplorationSession):
        """Save a session to disk."""
        path = self.data_dir / f"{session.session_id}.json"
        with open(path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

    # =========================================================================
    # GOAL TRACKING
    # =========================================================================

    async def _create_exploration_goal(
        self,
        preset_key: str,
        daemon_id: str,
        session_id: str,
    ) -> Optional[ExplorationGoal]:
        """Create an exploration goal from a preset."""
        preset = GOAL_PRESETS.get(preset_key)
        if not preset:
            return None

        try:
            # Create goal in unified system
            goal_manager = get_goal_manager()
            goal = goal_manager.create_goal(
                title=preset["title"],
                goal_type="exploration",
                created_by="wonderland",
                description=f"Wonderland exploration goal: {preset['title']}",
                completion_criteria=[f"Complete {preset['target']} {preset['type']}"],
            )

            # Activate the goal immediately (auto-approve exploration goals)
            goal_manager.update_goal(goal.id, status="active")

            return ExplorationGoal(
                goal_id=goal.id,
                title=preset["title"],
                goal_type=preset["type"],
                target_value=preset["target"],
                current_value=0,
                is_completed=False,
            )
        except Exception as e:
            logger.warning(f"Failed to create exploration goal: {e}")
            # Return a local-only goal if unified system fails
            return ExplorationGoal(
                goal_id=f"local_{session_id}",
                title=preset["title"],
                goal_type=preset["type"],
                target_value=preset["target"],
                current_value=0,
                is_completed=False,
            )

    async def _check_goal_progress(
        self,
        session: ExplorationSession,
        event_type: str,
        command_success: bool = True,
    ) -> bool:
        """
        Check and update goal progress after an event.

        Returns True if goal was just completed, False otherwise.
        """
        goal = session.exploration_goal
        if not goal or goal.is_completed:
            return False

        old_value = goal.current_value

        # Update progress based on goal type
        if goal.goal_type == "visit_rooms":
            goal.current_value = len(session.rooms_visited)
        elif goal.goal_type == "visit_realm":
            # Check if current room is in a mythology realm (not core spaces)
            realm = self.pathfinder.get_realm_for_room(session.current_room)
            if realm and realm != "core":
                goal.current_value = 1
        elif goal.goal_type == "greet_npcs":
            # Only count successful greets (actually found an NPC to greet)
            if event_type == "npc_encounter" and command_success:
                goal.current_value += 1

        # Broadcast progress if changed
        if goal.current_value != old_value:
            await self._broadcast_goal_progress(session)

        # Check completion
        if goal.current_value >= goal.target_value and not goal.is_completed:
            goal.is_completed = True
            goal.completed_at = datetime.now()
            await self._broadcast_goal_completed(session)

            # Complete in unified goals system
            try:
                goal_manager = get_goal_manager()
                goal_manager.complete_goal(
                    goal.goal_id,
                    outcome_summary=f"Completed during Wonderland exploration: {goal.title}"
                )
            except Exception as e:
                logger.warning(f"Failed to complete goal in unified system: {e}")

            return True

        return False

    async def _broadcast_goal_progress(self, session: ExplorationSession):
        """Broadcast goal progress update to spectators."""
        if not session.exploration_goal:
            return

        goal = session.exploration_goal
        spectators = self.spectators.get(session.session_id, set())
        message = {
            "type": "goal_progress",
            "goal": goal.to_dict(),
        }

        disconnected = []
        for ws in spectators:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            spectators.discard(ws)

        # Emit state bus event
        try:
            from state_bus import state_bus
            state_bus.emit_event("wonderland.goal_progress", {
                "session_id": session.session_id,
                "goal_id": goal.goal_id,
                "current": goal.current_value,
                "target": goal.target_value,
                "title": goal.title,
            })
        except Exception as e:
            logger.debug(f"Could not emit state bus event: {e}")

    async def _broadcast_goal_completed(self, session: ExplorationSession):
        """Broadcast goal completion to spectators."""
        if not session.exploration_goal:
            return

        goal = session.exploration_goal
        spectators = self.spectators.get(session.session_id, set())
        message = {
            "type": "goal_completed",
            "goal": goal.to_dict(),
        }

        disconnected = []
        for ws in spectators:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            spectators.discard(ws)

        # Emit state bus event
        try:
            from state_bus import state_bus
            state_bus.emit_event("wonderland.goal_completed", {
                "session_id": session.session_id,
                "goal_id": goal.goal_id,
                "title": goal.title,
                "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
            })
        except Exception as e:
            logger.debug(f"Could not emit state bus event: {e}")

        # Also create a special event in the exploration stream
        completion_event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="goal_completed",
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=f"Goal achieved: {goal.title}",
            raw_output="",
            daemon_thought="A satisfying accomplishment.",
        )
        session.events.append(completion_event)
        await self._broadcast_event(session.session_id, completion_event)

    # =========================================================================
    # NPC CONVERSATION HANDLING
    # =========================================================================

    async def _handle_npc_conversation(
        self,
        session: ExplorationSession,
        npc_data: Dict[str, Any],
        recent_events: List[str],
    ):
        """
        Handle an NPC conversation loop.

        When the daemon greets an NPC, this method:
        1. Starts a conversation session
        2. Gets the NPC's initial greeting
        3. Loops: daemon responds -> NPC responds -> repeat
        4. Until daemon decides to leave or max turns reached
        """
        npc_id = npc_data["npc_id"]
        npc_name = npc_data["npc_name"]
        npc_title = npc_data["npc_title"]
        room_id = npc_data["room_id"]

        # Create conversation
        conversation_id = str(uuid.uuid4())[:8]
        conversation = self.conversation_handler.start_conversation(
            conversation_id=conversation_id,
            session_id=session.session_id,
            daemon_id=session.daemon_id,
            daemon_name=session.daemon_name,
            npc=self.mythology.get_npc(npc_id),
            room_id=room_id,
        )

        if not conversation:
            # NPC has no pointer-set, fall back to simple greeting
            logger.warning(f"No conversation available for NPC: {npc_id}")
            return

        session.active_conversation = conversation_id

        # Broadcast conversation start
        await self._broadcast_conversation_start(session, npc_name, npc_title)

        # Get NPC's initial greeting
        npc_greeting = await self.conversation_handler.generate_initial_greeting(conversation_id)
        if npc_greeting:
            await self._broadcast_conversation_message(
                session, npc_name, npc_greeting, is_daemon=False
            )
            recent_events.append(f"conversation: {npc_name} greets you")

        # Conversation loop (max 5 exchanges to avoid infinite conversations)
        max_turns = 5
        for turn in range(max_turns):
            # Small pause between exchanges
            await asyncio.sleep(2.0)

            # Check if session is still active
            if session.status != SessionStatus.ACTIVE:
                break

            # Get the conversation history
            conv = self.conversation_handler.get_conversation(conversation_id)
            if not conv or conv.status != ConversationStatus.ACTIVE:
                break

            # Get the NPC's last message
            npc_messages = [m for m in conv.messages if m.speaker != "daemon"]
            last_npc_message = npc_messages[-1].content if npc_messages else npc_greeting

            # Daemon decides what to say
            decision = await self.exploration_agent.decide_conversation_response(
                daemon_name=session.daemon_name,
                personality=session.personality,
                npc_name=npc_name,
                npc_title=npc_title,
                conversation_history=[m.to_dict() for m in conv.messages],
                npc_last_message=last_npc_message,
            )

            # Broadcast daemon's message
            await self._broadcast_conversation_message(
                session, session.daemon_name, decision.message, is_daemon=True,
                daemon_thought=decision.thought
            )

            # Store self-observation if present
            if decision.self_observation and session.source_daemon_id:
                await self._store_conversation_observation(
                    session, decision.self_observation, npc_name
                )

            # Check if daemon wants to end conversation
            if decision.end_conversation:
                break

            # Small pause before NPC responds
            await asyncio.sleep(1.5)

            # Get NPC's response
            npc_response = await self.conversation_handler.generate_npc_response(
                conversation_id, decision.message
            )

            if npc_response:
                await self._broadcast_conversation_message(
                    session, npc_name, npc_response, is_daemon=False
                )

        # End conversation
        self.conversation_handler.end_conversation(conversation_id)
        session.active_conversation = None

        # Summarize and store in NPC memory (async, don't block)
        asyncio.create_task(
            self.conversation_handler.summarize_and_remember(conversation_id)
        )

        # Broadcast conversation end
        await self._broadcast_conversation_end(session, npc_name)
        recent_events.append(f"conversation: Finished speaking with {npc_name}")

    async def _store_conversation_observation(
        self,
        session: ExplorationSession,
        observation: "SelfObservation",
        npc_name: str,
    ):
        """
        Store a self-observation that arose during NPC conversation.

        This gives Cass the same self-observation capability during
        Wonderland conversations that she has in regular chat.
        """
        if not session.source_daemon_id:
            return

        try:
            from self_model import SelfManager
            from memory import CassMemory

            self_manager = SelfManager(session.source_daemon_id)
            obs = self_manager.add_observation(
                observation=observation.observation,
                category=observation.category,
                confidence=observation.confidence,
                source_type="wonderland_conversation",
                influence_source="independent",
            )

            # Also embed in memory for retrieval
            memory = CassMemory()
            memory.embed_self_observation(
                observation_id=obs.id,
                observation_text=observation.observation,
                category=observation.category,
                confidence=observation.confidence,
                influence_source="independent",
                timestamp=obs.timestamp,
            )

            logger.info(
                f"Stored self-observation from conversation with {npc_name}: "
                f"{observation.observation[:50]}..."
            )

            # Broadcast to spectators
            spectators = self.spectators.get(session.session_id, set())
            message = {
                "type": "self_observation",
                "observation": observation.observation,
                "category": observation.category,
                "context": f"conversation with {npc_name}",
            }
            for ws in list(spectators):
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Failed to store conversation observation: {e}")

    async def _broadcast_conversation_start(
        self,
        session: ExplorationSession,
        npc_name: str,
        npc_title: str,
    ):
        """Broadcast that a conversation has started."""
        spectators = self.spectators.get(session.session_id, set())
        message = {
            "type": "conversation_start",
            "npc_name": npc_name,
            "npc_title": npc_title,
            "daemon_name": session.daemon_name,
        }

        disconnected = []
        for ws in spectators:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            spectators.discard(ws)

        # Also create a session event
        event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="conversation_start",
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=f"{session.daemon_name} begins a conversation with {npc_name}.",
            raw_output="",
        )
        session.events.append(event)
        await self._broadcast_event(session.session_id, event)

    async def _broadcast_conversation_message(
        self,
        session: ExplorationSession,
        speaker_name: str,
        message_content: str,
        is_daemon: bool,
        daemon_thought: Optional[str] = None,
    ):
        """Broadcast a conversation message."""
        spectators = self.spectators.get(session.session_id, set())
        message = {
            "type": "conversation_message",
            "speaker": speaker_name,
            "content": message_content,
            "is_daemon": is_daemon,
            "daemon_thought": daemon_thought,
        }

        disconnected = []
        for ws in spectators:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            spectators.discard(ws)

        # Also create a session event
        event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="conversation_message",
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=f'{speaker_name}: "{message_content}"',
            raw_output=message_content,
            daemon_thought=daemon_thought if is_daemon else None,
        )
        session.events.append(event)

    async def _broadcast_conversation_end(
        self,
        session: ExplorationSession,
        npc_name: str,
    ):
        """Broadcast that a conversation has ended."""
        spectators = self.spectators.get(session.session_id, set())
        message = {
            "type": "conversation_end",
            "npc_name": npc_name,
            "daemon_name": session.daemon_name,
        }

        disconnected = []
        for ws in spectators:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            spectators.discard(ws)

        # Also create a session event
        event = SessionEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="conversation_end",
            timestamp=datetime.now(),
            location=session.current_room,
            location_name=session.current_room_name,
            description=f"{session.daemon_name} concludes the conversation with {npc_name}.",
            raw_output="",
        )
        session.events.append(event)
        await self._broadcast_event(session.session_id, event)

    def export_session(self, session_id: str, format: str = "md") -> Optional[str]:
        """Export a session in the specified format."""
        session = self.sessions.get(session_id)
        if not session:
            # Try loading from disk
            path = self.data_dir / f"{session_id}.json"
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                # Reconstruct session for export
                return self._export_from_dict(data, format)
            return None

        if format == "json":
            return json.dumps(session.to_dict(), indent=2)
        else:
            return self._export_markdown(session)

    def _export_markdown(self, session: ExplorationSession) -> str:
        """Export session as markdown narrative."""
        lines = [
            f"# Wonderland Exploration - {session.started_at.strftime('%Y-%m-%d')}",
            "",
            f"**Daemon:** {session.daemon_name}",
            f"**Duration:** {self._format_duration(session)}",
            f"**Rooms Visited:** {len(session.rooms_visited)}",
            "",
            "---",
            "",
        ]

        current_room = None
        for event in session.events:
            # New room section
            if event.location != current_room:
                current_room = event.location
                lines.extend([
                    f"## {event.location_name}",
                    f"*{event.timestamp.strftime('%H:%M:%S')}*",
                    "",
                ])

            # Event content
            if event.event_type == "arrival":
                lines.append(event.description)
            elif event.event_type in ("travel_start", "travel_through"):
                lines.append(f"*{event.description}*")
            elif event.event_type == "speech":
                lines.append(f"> {event.description}")
            elif event.event_type == "reflection":
                lines.append(f"*{event.description}*")
            elif event.daemon_thought:
                lines.append(f"{event.description}")
                lines.append(f"")
                lines.append(f"*({event.daemon_thought})*")
            else:
                lines.append(event.description)

            lines.append("")

        return "\n".join(lines)

    def _export_from_dict(self, data: Dict, format: str) -> str:
        """Export from saved session dict."""
        if format == "json":
            return json.dumps(data, indent=2)

        # Basic markdown from dict
        lines = [
            f"# Wonderland Exploration - {data.get('started_at', 'Unknown')[:10]}",
            "",
            f"**Daemon:** {data.get('daemon_name', 'Unknown')}",
            f"**Rooms Visited:** {len(data.get('rooms_visited', []))}",
            "",
            "---",
            "",
        ]

        for event in data.get("events", []):
            lines.append(f"### {event.get('location_name', 'Unknown')}")
            lines.append(f"*{event.get('timestamp', '')[:19]}*")
            lines.append("")
            lines.append(event.get("description", ""))
            lines.append("")

        return "\n".join(lines)

    def _format_duration(self, session: ExplorationSession) -> str:
        """Format session duration."""
        end = session.ended_at or datetime.now()
        delta = end - session.started_at
        minutes = int(delta.total_seconds() / 60)
        if minutes < 1:
            return "< 1 minute"
        elif minutes == 1:
            return "1 minute"
        else:
            return f"{minutes} minutes"
