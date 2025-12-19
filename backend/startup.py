"""
Startup helpers for Cass Vessel server.
Extracted from main_sdk.py for clarity and testability.
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from config import ANTHROPIC_API_KEY, DATA_DIR

logger = logging.getLogger(__name__)


def validate_startup_requirements() -> None:
    """
    Validate required configuration before starting.
    Raises RuntimeError if critical requirements are not met.
    """
    errors = []

    # Check for API key (required for Anthropic mode)
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY not set - required for Claude API access")

    # Check data directory is writable
    try:
        test_file = DATA_DIR / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        errors.append(f"DATA_DIR ({DATA_DIR}) is not writable: {e}")

    # Log warnings for optional but recommended settings
    if os.getenv("JWT_SECRET_KEY", "").startswith("CHANGE_ME"):
        logger.warning("JWT_SECRET_KEY is using default value - change this in production!")

    if errors:
        for error in errors:
            logger.error(f"Startup validation failed: {error}")
        raise RuntimeError(f"Startup validation failed: {'; '.join(errors)}")

    logger.info("Startup validation passed")


def init_heavy_components() -> Dict[str, Any]:
    """
    Initialize ChromaDB and self-model graph (called in background).

    Returns dict with:
        - memory: CassMemory instance
        - self_model_graph: SelfModelGraph instance
        - self_manager: SelfManager instance
        - marker_store: MarkerStore instance
        - needs_embedding_rebuild: bool
    """
    from memory import CassMemory
    from self_model import SelfManager
    from self_model_graph import get_self_model_graph
    from scripts.migrate_to_graph import populate_graph as populate_self_model_graph
    from markers import MarkerStore

    needs_embedding_rebuild = False

    print("Initializing ChromaDB memory...")
    memory = CassMemory()

    print("Loading self-model graph...")
    self_model_graph = get_self_model_graph(DATA_DIR)
    graph_stats = self_model_graph.get_stats()

    if graph_stats['total_nodes'] == 0:
        print("  Self-model graph is empty, populating from existing data...")
        populate_result = populate_self_model_graph(self_model_graph, verbose=False)
        print(f"  Self-model graph populated: {populate_result['nodes']} nodes, "
              f"{populate_result['edges']} edges")
        needs_embedding_rebuild = True
    else:
        print(f"  Self-model graph loaded: {graph_stats['total_nodes']} nodes, "
              f"{graph_stats['total_edges']} edges")
        # Check if embeddings need rebuilding (collection might be empty)
        if self_model_graph._node_collection is not None:
            embedding_count = self_model_graph._node_collection.count()
            connectable_count = len([n for n in self_model_graph._nodes.values()
                                     if n.node_type in self_model_graph.CONNECTABLE_TYPES])
            if embedding_count < connectable_count * 0.5:  # Less than half embedded
                print(f"  Embeddings need rebuild ({embedding_count} < {connectable_count}) - will run in background")
                needs_embedding_rebuild = True

    self_manager = SelfManager(graph_callback=self_model_graph)

    # Initialize marker store now that memory is ready
    marker_store = MarkerStore(client=memory.client, graph_callback=self_model_graph)

    # Sync self-observations from file storage to ChromaDB for semantic search
    synced_count = memory.sync_self_observations_from_file(self_manager)
    if synced_count > 0:
        print(f"  Synced {synced_count} self-observations to ChromaDB")

    print("Heavy components initialized")

    return {
        "memory": memory,
        "self_model_graph": self_model_graph,
        "self_manager": self_manager,
        "marker_store": marker_store,
        "needs_embedding_rebuild": needs_embedding_rebuild,
    }


def init_llm_clients(
    daemon_name: str,
    daemon_id: str,
    use_agent_sdk: bool = True
) -> Dict[str, Any]:
    """
    Initialize LLM clients based on configuration.

    Returns dict with:
        - agent_client: CassAgentClient or None
        - legacy_client: ClaudeClient or None
        - ollama_client: OllamaClient or None
        - openai_client: OpenAIClient or None
    """
    from config import OLLAMA_ENABLED, OPENAI_ENABLED

    agent_client = None
    legacy_client = None
    ollama_client = None
    openai_client = None

    # Initialize appropriate Claude client
    if use_agent_sdk:
        from agent_client import CassAgentClient
        logger.info("Using Claude Agent SDK with Temple-Codex kernel")
        agent_client = CassAgentClient(
            enable_tools=True,
            enable_memory_tools=True,
            daemon_name=daemon_name,
            daemon_id=daemon_id
        )
    else:
        from claude_client import ClaudeClient
        logger.warning("Agent SDK not available, using raw API client")
        legacy_client = ClaudeClient()

    # Initialize Ollama client for local mode
    if OLLAMA_ENABLED:
        from agent_client import OllamaClient
        logger.info("Initializing Ollama client for local LLM...")
        ollama_client = OllamaClient(daemon_name=daemon_name, daemon_id=daemon_id)
        logger.info(f"Ollama ready (model: {ollama_client.model})")

    # Initialize OpenAI client if enabled
    if OPENAI_ENABLED:
        try:
            from openai_client import OpenAIClient, OPENAI_AVAILABLE
            if OPENAI_AVAILABLE:
                logger.info("Initializing OpenAI client...")
                openai_client = OpenAIClient(
                    enable_tools=True,
                    enable_memory_tools=True,
                    daemon_name=daemon_name,
                    daemon_id=daemon_id
                )
                logger.info(f"OpenAI ready (model: {openai_client.model})")
        except Exception as e:
            logger.error(f"OpenAI initialization failed: {e}")

    return {
        "agent_client": agent_client,
        "legacy_client": legacy_client,
        "ollama_client": ollama_client,
        "openai_client": openai_client,
    }


def preload_tts_voice(voice: str) -> bool:
    """
    Preload TTS voice for faster first response.

    Returns True if successful, False otherwise.
    """
    logger.info("Preloading TTS voice...")
    try:
        from tts import preload_voice
        preload_voice(voice)
        logger.info(f"Loaded voice: {voice}")
        return True
    except Exception as e:
        logger.error(f"TTS preload failed: {e}")
        return False


def print_startup_banner(use_agent_sdk: bool, version: str = "0.2.0") -> None:
    """Print the startup banner."""
    backend_mode = 'Agent SDK + Temple-Codex' if use_agent_sdk else 'Raw API (legacy)'
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║              CASS VESSEL SERVER v{version}                    ║
║         First Contact Embodiment System                   ║
║                                                           ║
║  Backend:  {backend_mode:^30}  ║
║  Memory:   {'(initializing in background)':^30}  ║
╚═══════════════════════════════════════════════════════════╝
    """)
