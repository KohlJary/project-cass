"""
GPU Coordinator for Cass Vessel.

Manages GPU memory access between competing services:
- Ollama (LLM inference)
- ACE-Step (music generation)
- ComfyUI (image generation)

When a service needs GPU memory, it requests access through this coordinator.
The coordinator checks available memory and can ask other services to release
their memory if needed.
"""

import asyncio
import subprocess
import httpx
import time
import fcntl
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class GPUService(Enum):
    """Services that use GPU memory."""
    OLLAMA = "ollama"
    ACESTEP = "acestep"
    COMFYUI = "comfyui"
    WHISPER = "whisper"  # STT


@dataclass
class GPUMemoryInfo:
    """GPU memory status."""
    total_mb: int
    used_mb: int
    free_mb: int
    processes: Dict[str, int]  # process name -> memory in MB


# Memory requirements (in MB) - additional free memory needed for operation
# Note: If the service already has models loaded, it needs less additional memory
SERVICE_MEMORY_REQUIREMENTS = {
    GPUService.OLLAMA: 8500,    # ~8.5GB for llama3.1:8b (full load)
    GPUService.ACESTEP: 6000,   # ~6GB for music generation
    GPUService.COMFYUI: 2500,   # ~2.5GB additional headroom (base model often pre-loaded)
    GPUService.WHISPER: 1000,   # ~1GB for whisper base/small (tiny=500MB, medium=2GB, large=5GB)
}

# Lock file for coordination
LOCK_FILE = Path("/tmp/cass-gpu-coordinator.lock")


class GPUCoordinator:
    """
    Coordinates GPU memory access between services.

    Usage:
        coordinator = GPUCoordinator()

        # Request GPU access before heavy operation
        async with coordinator.request_gpu(GPUService.ACESTEP, required_mb=10000):
            # GPU memory is available, run your operation
            await generate_music(...)
    """

    def __init__(self):
        self.ollama_base_url = "http://localhost:11434"
        self.comfyui_base_url = "http://localhost:8188"
        self._lock_fd = None

    def get_gpu_memory(self) -> Optional[GPUMemoryInfo]:
        """Get current GPU memory status using nvidia-smi."""
        # Use full path since systemd services have minimal PATH
        nvidia_smi = "/usr/bin/nvidia-smi"

        try:
            # Get overall memory
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=memory.total,memory.used,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None

            total, used, free = map(int, result.stdout.strip().split(", "))

            # Get per-process memory
            proc_result = subprocess.run(
                [nvidia_smi, "--query-compute-apps=process_name,used_memory",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )

            processes = {}
            if proc_result.returncode == 0 and proc_result.stdout.strip():
                for line in proc_result.stdout.strip().split("\n"):
                    if ", " in line:
                        name, mem = line.rsplit(", ", 1)
                        name = Path(name).name  # Just the executable name
                        processes[name] = int(mem)

            return GPUMemoryInfo(
                total_mb=total,
                used_mb=used,
                free_mb=free,
                processes=processes
            )
        except Exception as e:
            logger.error(f"Failed to get GPU memory: {e}")
            return None

    def is_ollama_loaded(self, memory_info: Optional[GPUMemoryInfo] = None) -> bool:
        """Check if Ollama has a model loaded in GPU memory."""
        if memory_info is None:
            memory_info = self.get_gpu_memory()
        if memory_info is None:
            return False
        return any("ollama" in name.lower() for name in memory_info.processes)

    async def unload_ollama(self, timeout: float = 30.0) -> bool:
        """
        Ask Ollama to unload its model from GPU memory.

        Uses 'ollama stop' to unload all running models.
        """
        try:
            # First, find what models are loaded
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.ollama_base_url}/api/ps",
                    timeout=5.0
                )
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])

                    # Stop each loaded model
                    for model in models:
                        model_name = model.get("name", "")
                        if model_name:
                            logger.info(f"Unloading Ollama model: {model_name}")
                            # Use full path since systemd services have minimal PATH
                            subprocess.run(
                                ["/usr/bin/ollama", "stop", model_name],
                                capture_output=True, timeout=10
                            )

            # Wait for memory to be freed
            start = time.time()
            while time.time() - start < timeout:
                if not self.is_ollama_loaded():
                    logger.info("Ollama models unloaded successfully")
                    return True
                await asyncio.sleep(1.0)

            return False

        except Exception as e:
            logger.error(f"Failed to unload Ollama: {e}")
            return False

    async def free_comfyui_memory(self) -> bool:
        """Ask ComfyUI to free its GPU memory."""
        try:
            async with httpx.AsyncClient() as client:
                # ComfyUI's free endpoint
                response = await client.post(
                    f"{self.comfyui_base_url}/free",
                    json={"unload_models": True, "free_memory": True},
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to free ComfyUI memory: {e}")
            return False

    def is_acestep_loaded(self, memory_info: Optional[GPUMemoryInfo] = None) -> bool:
        """Check if ACE-Step has models loaded in GPU memory."""
        if memory_info is None:
            memory_info = self.get_gpu_memory()
        if memory_info is None:
            return False
        # ACE-Step runs as python in its venv
        return any(
            "ace-step" in name.lower() or
            (name == "python3" and mem > 2000)  # ACE-Step uses ~5GB
            for name, mem in memory_info.processes.items()
        )

    async def stop_acestep(self, timeout: float = 30.0) -> bool:
        """
        Stop ACE-Step service to free GPU memory.

        Will be restarted automatically when music generation is requested.
        Uses systemctl --user if available, falls back to pkill.
        """
        try:
            logger.info("Stopping ACE-Step service to free GPU memory...")

            # Try systemctl (works if user has permissions via polkit)
            result = subprocess.run(
                ["/usr/bin/systemctl", "stop", "acestep.service"],
                capture_output=True, timeout=15
            )

            if result.returncode != 0:
                # Fall back to sending SIGTERM to the ACE-Step process
                logger.info("systemctl failed, trying pkill...")
                result = subprocess.run(
                    ["/usr/bin/pkill", "-f", "ace-step.*uvicorn"],
                    capture_output=True, timeout=10
                )
                # pkill returns 1 if no processes matched, which is fine

            # Wait for memory to be freed
            start = time.time()
            while time.time() - start < timeout:
                if not self.is_acestep_loaded():
                    logger.info("ACE-Step stopped, GPU memory freed")
                    return True
                await asyncio.sleep(1.0)

            logger.warning("ACE-Step memory not freed within timeout")
            return False

        except Exception as e:
            logger.error(f"Failed to stop ACE-Step: {e}")
            return False

    async def ensure_acestep_running(self) -> bool:
        """Ensure ACE-Step service is running."""
        try:
            # Check if already running
            result = subprocess.run(
                ["/usr/bin/systemctl", "is-active", "acestep.service"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip() == "active":
                return True

            # Try to start it
            logger.info("Starting ACE-Step service...")
            result = subprocess.run(
                ["/usr/bin/systemctl", "start", "acestep.service"],
                capture_output=True, timeout=30
            )

            if result.returncode != 0:
                logger.warning(f"Failed to start ACE-Step: {result.stderr.decode()}")
                return False

            # Wait for service to be ready
            for _ in range(30):  # 30 second timeout
                await asyncio.sleep(1.0)
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get("http://localhost:8001/health", timeout=2.0)
                        if resp.status_code == 200:
                            logger.info("ACE-Step service started and healthy")
                            return True
                except:
                    pass

            logger.warning("ACE-Step started but health check failed")
            return False

        except Exception as e:
            logger.error(f"Failed to ensure ACE-Step running: {e}")
            return False

    async def ensure_memory_available(
        self,
        required_mb: int,
        requesting_service: GPUService,
        max_wait: float = 60.0,
    ) -> bool:
        """
        Ensure sufficient GPU memory is available.

        Will attempt to free memory from other services if needed.

        Args:
            required_mb: Amount of memory needed in MB
            requesting_service: The service requesting memory
            max_wait: Maximum time to wait for memory in seconds

        Returns:
            True if memory is available, False if timed out
        """
        start = time.time()

        while time.time() - start < max_wait:
            memory = self.get_gpu_memory()
            if memory is None:
                logger.warning("Could not get GPU memory info, proceeding anyway")
                return True

            logger.info(f"GPU memory: {memory.free_mb}MB free, need {required_mb}MB")

            # Check if we have enough memory
            if memory.free_mb >= required_mb:
                return True

            # Try to free memory from other services
            freed_any = False

            # Try Ollama first (usually the biggest consumer)
            if requesting_service != GPUService.OLLAMA and self.is_ollama_loaded(memory):
                logger.info("Requesting Ollama to unload models...")
                if await self.unload_ollama(timeout=30.0):
                    freed_any = True

            # Try ACE-Step (uses ~5GB when loaded)
            if requesting_service != GPUService.ACESTEP and self.is_acestep_loaded(memory):
                logger.info("Stopping ACE-Step to free GPU memory...")
                if await self.stop_acestep(timeout=30.0):
                    freed_any = True

            # Try ComfyUI
            if requesting_service != GPUService.COMFYUI:
                comfyui_mem = memory.processes.get("python", 0)  # ComfyUI runs as python
                if comfyui_mem > 500:  # More than 500MB
                    logger.info("Requesting ComfyUI to free memory...")
                    if await self.free_comfyui_memory():
                        freed_any = True

            if freed_any:
                # Give time for memory to be released
                await asyncio.sleep(2.0)
            else:
                # Nothing to free, just wait
                await asyncio.sleep(5.0)

        logger.error(f"Timed out waiting for {required_mb}MB GPU memory")
        return False

    def _acquire_lock(self) -> bool:
        """Acquire exclusive file lock for GPU access."""
        try:
            LOCK_FILE.touch(exist_ok=True)
            self._lock_fd = open(LOCK_FILE, 'w')
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (IOError, OSError):
            if self._lock_fd:
                self._lock_fd.close()
                self._lock_fd = None
            return False

    def _release_lock(self):
        """Release the GPU access lock."""
        if self._lock_fd:
            try:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                self._lock_fd.close()
            except:
                pass
            self._lock_fd = None

    class GPUContext:
        """Async context manager for GPU access."""

        def __init__(
            self,
            coordinator: "GPUCoordinator",
            service: GPUService,
            required_mb: int,
            max_wait: float,
        ):
            self.coordinator = coordinator
            self.service = service
            self.required_mb = required_mb
            self.max_wait = max_wait
            self.acquired = False

        async def __aenter__(self):
            # Wait for lock (another heavy GPU operation might be running)
            start = time.time()
            while time.time() - start < self.max_wait:
                if self.coordinator._acquire_lock():
                    break
                await asyncio.sleep(1.0)
            else:
                raise TimeoutError("Timed out waiting for GPU lock")

            # Now ensure we have enough memory
            if not await self.coordinator.ensure_memory_available(
                self.required_mb, self.service, self.max_wait
            ):
                self.coordinator._release_lock()
                raise MemoryError(f"Could not get {self.required_mb}MB GPU memory")

            self.acquired = True
            return self

        async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
            if self.acquired:
                self.coordinator._release_lock()
            return False

    def request_gpu(
        self,
        service: GPUService,
        required_mb: Optional[int] = None,
        max_wait: float = 120.0,
    ) -> GPUContext:
        """
        Request exclusive GPU access for a service.

        Args:
            service: The service requesting GPU access
            required_mb: Memory needed (defaults to service requirement)
            max_wait: Max seconds to wait for GPU access

        Returns:
            Async context manager that ensures GPU access

        Usage:
            async with coordinator.request_gpu(GPUService.ACESTEP):
                await generate_music(...)
        """
        if required_mb is None:
            required_mb = SERVICE_MEMORY_REQUIREMENTS.get(service, 8000)

        return self.GPUContext(self, service, required_mb, max_wait)


# Singleton instance
_coordinator: Optional[GPUCoordinator] = None


def get_gpu_coordinator() -> GPUCoordinator:
    """Get or create the GPU coordinator singleton."""
    global _coordinator
    if _coordinator is None:
        _coordinator = GPUCoordinator()
    return _coordinator
