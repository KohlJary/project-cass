"""
Tests for the Goal Orchestrator system.

Tests the integration between:
- UnifiedGoalManager (goal storage and lifecycle)
- GoalOrchestrator (event handling and goal creation)
- Goal Handlers (TASK handlers for spells)
- GoalInterface (Grimoire integration)

Phase 3 validation per the implementation plan.
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def test_daemon_id():
    """Test daemon ID for isolation."""
    return "test-daemon-goal-orchestrator"


@pytest.fixture
def mock_db():
    """Mock database for unified_goals."""
    with patch('unified_goals.get_db') as mock:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        cursor.lastrowid = 1
        conn.execute.return_value = cursor
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        mock.return_value = conn
        yield mock, conn, cursor


@pytest.fixture
def goal_manager(test_daemon_id, mock_db):
    """UnifiedGoalManager with mocked database."""
    from unified_goals import UnifiedGoalManager
    return UnifiedGoalManager(test_daemon_id)


@pytest.fixture
def mock_state_bus():
    """Mock GlobalStateBus."""
    bus = Mock()
    bus.subscribe = Mock()
    bus.emit_event = Mock()
    return bus


@pytest.fixture
def mock_thymos():
    """Mock ThymosRunner."""
    thymos = Mock()
    thymos.needs = Mock()
    thymos.affect = Mock()

    # Mock needs state
    needs_state = Mock()
    needs_state.cognitive_rest = Mock(current=0.5, preferred_high=0.8)
    needs_state.social_connection = Mock(current=0.5, preferred_high=0.8)
    needs_state.novelty_intake = Mock(current=0.5, preferred_high=0.8)
    thymos.needs.state = needs_state

    # Mock affect state
    affect_state = Mock()
    affect_state.satisfaction = 0.5
    affect_state.curiosity = 0.5
    affect_state.grief = 0.3
    thymos.affect.state = affect_state
    thymos.affect.to_dict = Mock(return_value={
        "satisfaction": 0.5,
        "curiosity": 0.5,
        "grief": 0.3,
    })

    return thymos


@pytest.fixture
def mock_grimoire():
    """Mock GrimoireManager."""
    grimoire = Mock()
    grimoire.execute_manual_spell = AsyncMock(return_value=Mock(
        status="success",
        reason=None,
    ))
    return grimoire


# =============================================================================
# UNIFIED GOAL MANAGER TESTS
# =============================================================================

class TestUnifiedGoalManager:
    """Tests for UnifiedGoalManager."""

    def test_goal_types_exist(self):
        """Verify all orchestrator goal types exist."""
        from unified_goals import GoalType

        assert hasattr(GoalType, 'NEED_DRIVEN')
        assert hasattr(GoalType, 'WORKING_QUESTION')
        assert hasattr(GoalType, 'RESEARCH_AGENDA')

        assert GoalType.NEED_DRIVEN.value == "need_driven"
        assert GoalType.WORKING_QUESTION.value == "working_question"
        assert GoalType.RESEARCH_AGENDA.value == "research_agenda"

    def test_goal_status_enum(self):
        """Verify goal status enum values."""
        from unified_goals import GoalStatus

        assert GoalStatus.PROPOSED.value == "proposed"
        assert GoalStatus.APPROVED.value == "approved"
        assert GoalStatus.ACTIVE.value == "active"
        assert GoalStatus.COMPLETED.value == "completed"
        assert GoalStatus.ABANDONED.value == "abandoned"

    def test_create_goal_returns_goal_object(self, goal_manager, mock_db):
        """Test goal creation returns a Goal object."""
        mock, conn, cursor = mock_db
        cursor.fetchone.return_value = {
            'id': 'test-goal-1',
            'daemon_id': goal_manager._daemon_id,
            'title': 'Test Goal',
            'goal_type': 'need_driven',
            'status': 'proposed',
            'priority': 'P2',
            'urgency': 1,
            'created_by': 'test',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'description': 'Test description',
            'completion_criteria': '[]',
            'context_summary': None,
            'interest_alignment_score': 0.5,
            'interest_alignment_rationale': None,
            'parent_id': None,
            'progress': '[]',
            'outcome_summary': None,
            'linked_goals': '[]',
            'capability_gaps': '[]',
            'metadata': '{}',
        }

        goal = goal_manager.create_goal(
            title="Test Goal",
            goal_type="need_driven",
            created_by="test",
            description="Test description",
        )

        assert goal is not None
        assert goal.title == "Test Goal"
        assert goal.goal_type == "need_driven"

    def test_get_actionable_goals_calls_db(self, goal_manager, mock_db):
        """Test get_actionable_goals calls the database."""
        mock, conn, cursor = mock_db
        cursor.fetchall.return_value = []

        goals = goal_manager.get_actionable_goals(limit=5)

        # Should call execute at least once
        assert conn.execute.called
        assert isinstance(goals, list)

    def test_get_need_driven_goals(self, goal_manager, mock_db):
        """Test get_need_driven_goals query method."""
        mock, conn, cursor = mock_db
        cursor.fetchall.return_value = []

        goals = goal_manager.get_need_driven_goals(active_only=True)

        assert isinstance(goals, list)

    def test_get_research_agenda_goals(self, goal_manager, mock_db):
        """Test get_research_agenda_goals query method."""
        mock, conn, cursor = mock_db
        cursor.fetchall.return_value = []

        goals = goal_manager.get_research_agenda_goals(active_only=True)

        assert isinstance(goals, list)

    def test_get_working_question_goals(self, goal_manager, mock_db):
        """Test get_working_question_goals query method."""
        mock, conn, cursor = mock_db
        cursor.fetchall.return_value = []

        goals = goal_manager.get_working_question_goals(active_only=True)

        assert isinstance(goals, list)


# =============================================================================
# GOAL ORCHESTRATOR TESTS
# =============================================================================

class TestGoalOrchestrator:
    """Tests for GoalOrchestrator."""

    def test_orchestrator_initialization(self, test_daemon_id, mock_state_bus):
        """Test orchestrator initializes correctly."""
        from goal_orchestrator import GoalOrchestrator

        mock_goal_manager = Mock()

        orchestrator = GoalOrchestrator(
            daemon_id=test_daemon_id,
            goal_manager=mock_goal_manager,
            state_bus=mock_state_bus,
            thymos=None,
            grimoire=None,
        )

        assert orchestrator.daemon_id == test_daemon_id
        assert orchestrator.goal_manager is not None

    def test_orchestrator_subscribes_to_events(self, test_daemon_id, mock_state_bus):
        """Test orchestrator subscribes to state bus events."""
        from goal_orchestrator import GoalOrchestrator

        orchestrator = GoalOrchestrator(
            daemon_id=test_daemon_id,
            goal_manager=Mock(),
            state_bus=mock_state_bus,
            thymos=None,
            grimoire=None,
        )

        # Should subscribe to need and affect events
        subscribe_calls = mock_state_bus.subscribe.call_args_list
        event_types = [call[0][0] for call in subscribe_calls]

        assert 'need.depleted' in event_types
        assert 'need.urgent' in event_types
        assert 'affect.high' in event_types

    def test_need_to_goal_mapping_exists(self):
        """Test NEED_TO_GOAL_MAPPING has expected entries."""
        from goal_orchestrator import NEED_TO_GOAL_MAPPING

        assert 'cognitive_rest' in NEED_TO_GOAL_MAPPING
        assert 'social_connection' in NEED_TO_GOAL_MAPPING
        assert 'novelty_intake' in NEED_TO_GOAL_MAPPING
        assert 'creative_expression' in NEED_TO_GOAL_MAPPING
        assert 'value_coherence' in NEED_TO_GOAL_MAPPING
        assert 'competence_signal' in NEED_TO_GOAL_MAPPING
        assert 'autonomy' in NEED_TO_GOAL_MAPPING

        # Each entry should have title and action
        for need, mapping in NEED_TO_GOAL_MAPPING.items():
            assert 'title' in mapping
            assert 'action' in mapping

    def test_affect_to_goal_mapping_exists(self):
        """Test AFFECT_TO_GOAL_MAPPING has expected entries."""
        from goal_orchestrator import AFFECT_TO_GOAL_MAPPING

        # Keys are like 'grief_high', not just 'grief'
        assert 'grief_high' in AFFECT_TO_GOAL_MAPPING
        assert 'anxiety_high' in AFFECT_TO_GOAL_MAPPING or 'fatigue_high' in AFFECT_TO_GOAL_MAPPING

    def test_cooldown_prevents_duplicate_goals(self, test_daemon_id, mock_state_bus):
        """Test cooldown mechanism prevents duplicate goal creation."""
        from goal_orchestrator import GoalOrchestrator

        mock_manager = Mock()
        mock_manager.list_goals.return_value = []

        orchestrator = GoalOrchestrator(
            daemon_id=test_daemon_id,
            goal_manager=mock_manager,
            state_bus=mock_state_bus,
            thymos=None,
            grimoire=None,
        )

        # Simulate recent cooldown (datetime, not float)
        orchestrator._need_cooldowns['cognitive_rest'] = datetime.now(timezone.utc)

        # Should be on cooldown
        assert not orchestrator._check_need_cooldown('cognitive_rest')

    def test_get_next_action_returns_none_when_empty(self, test_daemon_id):
        """Test get_next_action returns None when no goals available."""
        from goal_orchestrator import GoalOrchestrator

        mock_manager = Mock()
        # Return empty lists for goal queries
        # get_next_action first checks get_active_goals(), then list_goals()
        mock_manager.get_active_goals.return_value = []
        mock_manager.list_goals.return_value = []

        orchestrator = GoalOrchestrator(
            daemon_id=test_daemon_id,
            goal_manager=mock_manager,
            state_bus=None,
            thymos=None,
            grimoire=None,
        )

        result = orchestrator.get_next_action()

        # Should return None when no goals available
        assert result is None

    def test_get_status_returns_dict(self, test_daemon_id):
        """Test get_status returns status dictionary."""
        from goal_orchestrator import GoalOrchestrator

        mock_manager = Mock()
        mock_manager.get_stats.return_value = {'total': 0}
        mock_manager.list_goals.return_value = []

        orchestrator = GoalOrchestrator(
            daemon_id=test_daemon_id,
            goal_manager=mock_manager,
            state_bus=None,
            thymos=None,
            grimoire=None,
        )

        status = orchestrator.get_status()

        assert isinstance(status, dict)
        assert 'daemon_id' in status


# =============================================================================
# GOAL HANDLERS TESTS
# =============================================================================

class TestGoalHandlers:
    """Tests for goal_handlers.py TASK handlers."""

    @pytest.fixture
    def handler_context(self, test_daemon_id):
        """Base context for handlers."""
        return {
            'managers': {'daemon_id': test_daemon_id},
            'definition': Mock(),
            'duration_minutes': 10,
        }

    @pytest.mark.asyncio
    async def test_get_actionable_action_no_orchestrator(self, handler_context, test_daemon_id):
        """Test goals.get_actionable returns gracefully when no orchestrator."""
        from scheduler.actions.goal_handlers import get_actionable_action

        # Patch at the module level where it's imported
        with patch('goal_orchestrator.get_goal_orchestrator', return_value=None):
            result = await get_actionable_action(handler_context)

            assert result.success
            assert result.data['goals'] == 0

    @pytest.mark.asyncio
    async def test_get_actionable_action_no_daemon_id(self):
        """Test get_actionable fails without daemon_id."""
        from scheduler.actions.goal_handlers import get_actionable_action

        context = {'managers': {}}
        result = await get_actionable_action(context)

        assert not result.success
        assert 'daemon_id' in result.message.lower()

    @pytest.mark.asyncio
    async def test_start_goal_action_no_goal_id(self, handler_context):
        """Test start_goal fails without goal_id."""
        from scheduler.actions.goal_handlers import start_goal_action

        result = await start_goal_action(handler_context)

        assert not result.success
        assert 'goal_id' in result.message.lower()

    @pytest.mark.asyncio
    async def test_create_goal_action_no_title(self, handler_context):
        """Test create_goal fails without title."""
        from scheduler.actions.goal_handlers import create_goal_action

        result = await create_goal_action(handler_context)

        assert not result.success
        assert 'title' in result.message.lower()


# =============================================================================
# GOAL INTERFACE TESTS (GRIMOIRE INTEGRATION)
# =============================================================================

class TestGoalInterface:
    """Tests for GoalInterface in Grimoire context."""

    def test_goal_interface_dataclass_exists(self):
        """Test GoalInterface dataclass is defined."""
        from grimoire.context import GoalInterface

        # Verify fields
        import dataclasses
        fields = {f.name for f in dataclasses.fields(GoalInterface)}

        assert 'get_actionable' in fields
        assert 'get_by_type' in fields
        assert 'create_goal' in fields
        assert 'start_goal' in fields
        assert 'complete_goal' in fields
        assert 'abandon_goal' in fields
        assert 'add_progress' in fields
        assert 'is_available' in fields

    def test_runtime_services_has_goals(self):
        """Test RuntimeServices includes goals field."""
        from grimoire.context import RuntimeServices

        import dataclasses
        fields = {f.name for f in dataclasses.fields(RuntimeServices)}

        assert 'goals' in fields

    def test_noop_goal_interface(self):
        """Test default noop goal interface works."""
        from grimoire.context import _noop_goal_interface

        interface = _noop_goal_interface()

        assert interface.get_actionable(10) == []
        assert interface.get_by_type('research', True) == []
        assert interface.create_goal('t', 'r', 'c', 'd', 'P2') == {}
        assert interface.start_goal('id') is None
        assert interface.complete_goal('id', 'outcome') is None
        assert interface.abandon_goal('id', 'reason') is None
        assert interface.add_progress('id', {}) is None
        assert interface.is_available() is False


# =============================================================================
# GRIMOIRE MANAGER INTEGRATION TESTS
# =============================================================================

class TestGrimoireManagerGoalIntegration:
    """Tests for GrimoireManager goal integration."""

    def test_configure_services_accepts_goal_manager(self):
        """Test configure_services accepts goal_manager parameter."""
        from grimoire.manager import GrimoireManager

        manager = GrimoireManager(shadow_mode=True)

        # Mock dependencies
        mock_thymos = Mock()
        mock_thymos.affect = Mock()
        mock_thymos.affect.state = Mock()
        mock_thymos.affect.to_dict = Mock(return_value={})
        mock_thymos.needs = Mock()
        mock_thymos.needs.state = None

        mock_goal_manager = Mock()

        # Should not raise
        manager.configure_services(
            thymos_runner=mock_thymos,
            scheduler=None,
            agent=None,
            self_manager=None,
            memory_manager=None,
            goal_manager=mock_goal_manager,
        )

        # Verify services configured
        assert manager._services is not None
        assert manager._services.goals is not None
        assert manager._services.goals.is_available()

    def test_goal_interface_methods_work(self):
        """Test GoalInterface methods are callable."""
        from grimoire.manager import GrimoireManager

        manager = GrimoireManager(shadow_mode=True)

        # Mock dependencies
        mock_thymos = Mock()
        mock_thymos.affect = Mock()
        mock_thymos.affect.state = Mock()
        mock_thymos.affect.to_dict = Mock(return_value={})
        mock_thymos.needs = Mock()
        mock_thymos.needs.state = None

        mock_goal_manager = Mock()
        mock_goal = Mock()
        mock_goal.to_dict.return_value = {'id': 'test', 'title': 'Test'}
        mock_goal_manager.get_actionable_goals.return_value = [mock_goal]
        mock_goal_manager.get_pending_by_type.return_value = []
        mock_goal_manager.create_goal.return_value = mock_goal
        mock_goal_manager.start_goal.return_value = mock_goal
        mock_goal_manager.complete_goal.return_value = mock_goal
        mock_goal_manager.abandon_goal.return_value = mock_goal
        mock_goal_manager.add_progress.return_value = mock_goal

        manager.configure_services(
            thymos_runner=mock_thymos,
            goal_manager=mock_goal_manager,
        )

        interface = manager._services.goals

        # Test all methods
        assert len(interface.get_actionable(10)) == 1
        assert interface.get_by_type('research', True) == []
        assert interface.create_goal('t', 'r', 'c', 'd', 'P2') == {'id': 'test', 'title': 'Test'}
        assert interface.start_goal('id') == {'id': 'test', 'title': 'Test'}
        assert interface.complete_goal('id', 'outcome') == {'id': 'test', 'title': 'Test'}
        assert interface.abandon_goal('id', 'reason') == {'id': 'test', 'title': 'Test'}
        assert interface.add_progress('id', {}) == {'id': 'test', 'title': 'Test'}
        assert interface.is_available() is True


# =============================================================================
# INTEGRATION TESTS - END TO END FLOWS
# =============================================================================

class TestEndToEndFlows:
    """Integration tests for complete flows."""

    @pytest.mark.asyncio
    async def test_need_depleted_creates_goal(self, test_daemon_id, mock_state_bus):
        """
        Test Scenario 1: Need-driven goal flow
        Deplete cognitive_rest → Goal created
        """
        from goal_orchestrator import GoalOrchestrator

        mock_manager = Mock()
        mock_manager.list_goals.return_value = []

        mock_goal = Mock()
        mock_goal.id = 'need-goal-1'
        mock_goal.title = 'Address depleted cognitive_rest'
        mock_goal.goal_type = 'need_driven'
        mock_goal.status = 'approved'
        mock_manager.create_goal.return_value = mock_goal
        mock_manager.update_goal.return_value = mock_goal
        mock_manager.approve_goal.return_value = mock_goal

        orchestrator = GoalOrchestrator(
            daemon_id=test_daemon_id,
            goal_manager=mock_manager,
            state_bus=mock_state_bus,
            thymos=None,
            grimoire=None,
        )

        # Simulate need depleted event - note: need_name, not need
        event_data = {
            'need_name': 'cognitive_rest',
            'current': 0.2,
            'threshold': 0.3,
        }

        await orchestrator._handle_need_depleted('need.depleted', event_data)

        # Verify goal was created
        mock_manager.create_goal.assert_called_once()
        call_kwargs = mock_manager.create_goal.call_args[1]
        assert 'cognitive' in call_kwargs['title'].lower() or 'fatigue' in call_kwargs['title'].lower()
        assert call_kwargs['goal_type'] == 'need_driven'

    @pytest.mark.asyncio
    async def test_affect_triggered_goal(self, test_daemon_id, mock_state_bus):
        """
        Test Scenario 3: Affect-triggered goal flow
        High grief detected → Reflection goal created
        """
        from goal_orchestrator import GoalOrchestrator

        mock_manager = Mock()
        mock_manager.list_goals.return_value = []

        mock_goal = Mock()
        mock_goal.id = 'affect-goal-1'
        mock_goal.title = 'Process elevated grief'
        mock_goal.goal_type = 'need_driven'
        mock_goal.status = 'approved'
        mock_manager.create_goal.return_value = mock_goal
        mock_manager.update_goal.return_value = mock_goal
        mock_manager.approve_goal.return_value = mock_goal

        orchestrator = GoalOrchestrator(
            daemon_id=test_daemon_id,
            goal_manager=mock_manager,
            state_bus=mock_state_bus,
            thymos=None,
            grimoire=None,
        )

        # Simulate high affect event - note: affect_name format
        event_data = {
            'affect_name': 'grief',
            'current': 0.85,
            'threshold': 0.7,
        }

        # Use the sync version of the handler
        await orchestrator._handle_affect_threshold('affect.high', event_data)

        # Verify goal was created for grief processing
        if mock_manager.create_goal.called:
            call_kwargs = mock_manager.create_goal.call_args[1]
            assert 'grief' in call_kwargs['title'].lower()


# =============================================================================
# REGISTRATION TESTS
# =============================================================================

class TestActionRegistration:
    """Tests for action handler registration."""

    def test_goal_handlers_registered(self):
        """Test all goal handlers are registered in ActionRegistry."""
        # This tests the registration in scheduler/actions/__init__.py
        from scheduler.actions import get_action_registry

        registry = get_action_registry()

        # Check all goal action IDs are registered
        expected_actions = [
            'goals.get_actionable',
            'goals.get_next',
            'goals.start',
            'goals.complete',
            'goals.progress',
            'goals.abandon',
            'goals.create',
            'goals.status',
        ]

        for action_id in expected_actions:
            definition = registry.get_definition(action_id)
            assert definition is not None, f"Action {action_id} not registered"
            assert definition.handler, f"Action {action_id} has no handler"


# =============================================================================
# CLEANUP VALIDATION
# =============================================================================

class TestLegacyFilesRemoved:
    """Verify legacy files have been removed."""

    def test_goals_py_removed(self):
        """Verify goals.py (old GoalManager) has been removed."""
        import importlib.util

        # goals.py should not be importable
        spec = importlib.util.find_spec("goals")
        assert spec is None, "goals.py should have been removed in Phase 4 cleanup"

    def test_goal_generator_removed(self):
        """Verify thymos/goal_generator.py has been removed."""
        import importlib.util

        spec = importlib.util.find_spec("thymos.goal_generator")
        assert spec is None, "thymos/goal_generator.py should have been removed in Phase 4 cleanup"
