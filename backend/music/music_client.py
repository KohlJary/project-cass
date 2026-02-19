"""
Music generation client for ACE-Step integration.

Provides Cass with the ability to compose music - both vocal tracks
with lyrics and instrumental pieces (for whistling, ambient, etc).
"""

import asyncio
import httpx
import json
import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid

# Import GPU coordinator for memory management
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from gpu_coordinator import get_gpu_coordinator, GPUService

logger = logging.getLogger(__name__)

# ACE-Step API configuration
ACESTEP_API_URL = "http://localhost:8001"  # Default ACE-Step API port
ACESTEP_TIMEOUT = 300.0  # Music generation can take a while


@dataclass
class MusicMetadata:
    """Rich metadata from ACE-Step generation."""
    bpm: Optional[int] = None
    duration: Optional[float] = None
    genres: Optional[str] = None
    keyscale: Optional[str] = None
    timesignature: Optional[str] = None
    language: Optional[str] = None
    seed_value: Optional[str] = None
    lm_model: Optional[str] = None
    dit_model: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict) -> "MusicMetadata":
        """Parse metadata from ACE-Step API response."""
        metas = data.get("metas", {})
        return cls(
            bpm=data.get("bpm") or metas.get("bpm"),
            duration=data.get("duration") or metas.get("duration"),
            genres=data.get("genres") or metas.get("genres"),
            keyscale=data.get("keyscale") or metas.get("keyscale"),
            timesignature=data.get("timesignature") or metas.get("timesignature"),
            language=metas.get("language"),
            seed_value=data.get("seed_value"),
            lm_model=data.get("lm_model"),
            dit_model=data.get("dit_model"),
        )


@dataclass
class MusicRequest:
    """Request for music generation."""
    prompt: str  # Description of the music style/mood
    lyrics: Optional[str] = None  # Lyrics for vocal tracks (None = instrumental)
    duration: float = 30.0  # Target duration in seconds
    bpm: Optional[int] = None  # Beats per minute (auto if None)
    key: str = ""  # Musical key (e.g., "C major", auto if empty)
    language: str = "en"  # Vocal language
    thinking: bool = True  # Use 5Hz LM for better quality
    audio_format: str = "mp3"
    purpose: str = "general"  # whistle, song, ambient, general
    title: Optional[str] = None  # Creative title for the composition


@dataclass
class MusicComposition:
    """A completed music composition with all metadata."""
    id: str
    created_at: str
    prompt: str
    lyrics: Optional[str]
    purpose: str
    audio_path: Optional[str]
    audio_url: Optional[str]
    status: str
    title: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[MusicMetadata] = None
    generation_info: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        if self.metadata:
            d["metadata"] = asdict(self.metadata)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MusicComposition":
        """Create from dictionary."""
        metadata = None
        if d.get("metadata"):
            metadata = MusicMetadata(**d["metadata"])
        return cls(
            id=d["id"],
            created_at=d["created_at"],
            prompt=d["prompt"],
            lyrics=d.get("lyrics"),
            purpose=d.get("purpose", "general"),
            audio_path=d.get("audio_path"),
            audio_url=d.get("audio_url"),
            status=d["status"],
            title=d.get("title"),
            error=d.get("error"),
            metadata=metadata,
            generation_info=d.get("generation_info"),
        )


@dataclass
class MusicResult:
    """Result of music generation."""
    task_id: str
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed
    error: Optional[str] = None
    metadata: Optional[MusicMetadata] = None
    generation_info: Optional[str] = None
    prompt: Optional[str] = None
    lyrics: Optional[str] = None
    title: Optional[str] = None


class MusicLibrary:
    """Persistent storage for generated compositions."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.index_path = data_dir / "compositions.json"
        self._compositions: List[MusicComposition] = []
        self._load()

    def _load(self):
        """Load compositions index from disk."""
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text())
                self._compositions = [MusicComposition.from_dict(d) for d in data]
            except Exception:
                self._compositions = []

    def _save(self):
        """Save compositions index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data = [c.to_dict() for c in self._compositions]
        self.index_path.write_text(json.dumps(data, indent=2))

    def add(self, composition: MusicComposition):
        """Add a composition to the library."""
        self._compositions.insert(0, composition)  # Most recent first
        self._save()

    def get(self, composition_id: str) -> Optional[MusicComposition]:
        """Get a composition by ID."""
        for c in self._compositions:
            if c.id == composition_id:
                return c
        return None

    def list(
        self,
        purpose: Optional[str] = None,
        genre: Optional[str] = None,
        limit: int = 50
    ) -> List[MusicComposition]:
        """List compositions with optional filtering."""
        results = self._compositions

        if purpose:
            results = [c for c in results if c.purpose == purpose]

        if genre and genre.lower() != "all":
            results = [
                c for c in results
                if c.metadata and c.metadata.genres
                and genre.lower() in c.metadata.genres.lower()
            ]

        return results[:limit]

    def get_genres(self) -> List[str]:
        """Get list of unique genres in the library."""
        genres = set()
        for c in self._compositions:
            if c.metadata and c.metadata.genres:
                # Genres might be comma-separated
                for g in c.metadata.genres.split(","):
                    g = g.strip()
                    if g:
                        genres.add(g)
        return sorted(genres)


class MusicClient:
    """Client for ACE-Step music generation API."""

    def __init__(self, base_url: str = ACESTEP_API_URL):
        self.base_url = base_url
        self.output_dir = Path(__file__).parent.parent / "data" / "music"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.library = MusicLibrary(self.output_dir)

    async def health_check(self) -> bool:
        """Check if ACE-Step API is running."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

    async def compose_music(self, request: MusicRequest) -> MusicResult:
        """
        Generate music based on the request.

        For instrumental/whistling: set lyrics=None and describe the mood
        For vocal tracks: provide lyrics and style description
        """
        composition_id = str(uuid.uuid4())[:8]
        created_at = datetime.now().isoformat()

        # Build API request
        api_request = {
            "prompt": request.prompt,
            "lyrics": request.lyrics or "",
            "audio_duration": request.duration,
            "bpm": request.bpm,
            "key_scale": request.key,
            "vocal_language": request.language,
            "thinking": request.thinking,
            "audio_format": request.audio_format,
            "use_random_seed": True,
        }

        # If no lyrics, hint that it's instrumental
        original_prompt = request.prompt
        if not request.lyrics:
            if "instrumental" not in request.prompt.lower():
                api_request["prompt"] = f"{request.prompt}. Instrumental, no vocals."

        try:
            # Request GPU access - will wait for/free memory from Ollama/ComfyUI if needed
            coordinator = get_gpu_coordinator()
            logger.info("Requesting GPU access for music generation...")

            async with coordinator.request_gpu(GPUService.ACESTEP, max_wait=120.0):
                logger.info("GPU access acquired, ensuring ACE-Step is running...")
                # Make sure ACE-Step service is started (it may have been stopped to free GPU)
                if not await coordinator.ensure_acestep_running():
                    raise RuntimeError("Failed to start ACE-Step service")

                # Wait briefly for service to be ready
                await asyncio.sleep(2.0)

                logger.info("ACE-Step ready, starting music generation")
                return await self._generate_with_gpu(
                    api_request, original_prompt, request, composition_id, created_at
                )

        except TimeoutError:
            result = MusicResult(
                task_id=composition_id,
                status="failed",
                error="Timed out waiting for GPU access (other services may be using it)",
                prompt=original_prompt,
                lyrics=request.lyrics,
            )
            self._save_composition(result, request.purpose, created_at)
            return result
        except MemoryError as e:
            result = MusicResult(
                task_id=composition_id,
                status="failed",
                error=str(e),
                prompt=original_prompt,
                lyrics=request.lyrics,
            )
            self._save_composition(result, request.purpose, created_at)
            return result
        except Exception as e:
            result = MusicResult(
                task_id=composition_id,
                status="failed",
                error=str(e),
                prompt=original_prompt,
                lyrics=request.lyrics,
            )
            self._save_composition(result, request.purpose, created_at)
            return result

    async def _generate_with_gpu(
        self,
        api_request: dict,
        original_prompt: str,
        request: MusicRequest,
        composition_id: str,
        created_at: str,
    ) -> MusicResult:
        """Internal method to generate music once GPU access is acquired."""
        try:
            async with httpx.AsyncClient() as client:
                # Submit generation task
                response = await client.post(
                    f"{self.base_url}/release_task",
                    json=api_request,
                    timeout=30.0
                )

                if response.status_code != 200:
                    result = MusicResult(
                        task_id=composition_id,
                        status="failed",
                        error=f"API error: {response.status_code} - {response.text}",
                        prompt=original_prompt,
                        lyrics=request.lyrics,
                    )
                    self._save_composition(result, request.purpose, created_at)
                    return result

                api_result = response.json()
                # ACE-Step wraps response in {"data": {...}, "code": 200}
                task_data = api_result.get("data", {})
                server_task_id = task_data.get("task_id", composition_id)
                logger.info(f"Music generation task submitted: {server_task_id}")

                # Poll for completion
                result = await self._poll_task(client, server_task_id, composition_id)
                result.prompt = original_prompt
                result.lyrics = request.lyrics
                result.title = request.title

                # Save to library
                self._save_composition(result, request.purpose, created_at)
                return result

        except httpx.TimeoutException:
            result = MusicResult(
                task_id=composition_id,
                status="failed",
                error="Generation timed out",
                prompt=original_prompt,
                lyrics=request.lyrics,
                title=request.title,
            )
            self._save_composition(result, request.purpose, created_at)
            return result
        except Exception as e:
            result = MusicResult(
                task_id=composition_id,
                status="failed",
                error=str(e),
                prompt=original_prompt,
                lyrics=request.lyrics,
                title=request.title,
            )
            self._save_composition(result, request.purpose, created_at)
            return result

    def _save_composition(self, result: MusicResult, purpose: str, created_at: str):
        """Save composition to library."""
        composition = MusicComposition(
            id=result.task_id,
            created_at=created_at,
            prompt=result.prompt or "",
            lyrics=result.lyrics,
            purpose=purpose,
            audio_path=result.audio_path,
            audio_url=result.audio_url,
            status=result.status,
            title=result.title,
            error=result.error,
            metadata=result.metadata,
            generation_info=result.generation_info,
        )
        self.library.add(composition)

    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        server_task_id: str,
        composition_id: str,
        max_wait: float = ACESTEP_TIMEOUT
    ) -> MusicResult:
        """Poll for task completion."""
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait:
                return MusicResult(
                    task_id=composition_id,
                    status="failed",
                    error=f"Timed out after {max_wait}s"
                )

            try:
                # ACE-Step API uses task_id_list parameter
                response = await client.post(
                    f"{self.base_url}/query_result",
                    json={"task_id_list": [server_task_id]},
                    timeout=30.0
                )

                if response.status_code != 200:
                    await asyncio.sleep(2.0)
                    continue

                # ACE-Step returns {"data": [...], "code": 200, ...}
                api_response = response.json()
                data_list = api_response.get("data", [])

                # Debug logging
                if data_list:
                    logger.debug(f"Poll result for {server_task_id}: {data_list[0]}")

                if not data_list:
                    await asyncio.sleep(2.0)
                    continue

                # Find our task in the results
                task_data = None
                for item in data_list:
                    if item.get("task_id") == server_task_id:
                        task_data = item
                        break

                if not task_data:
                    await asyncio.sleep(2.0)
                    continue

                # Status codes: 0=pending/processing, 1=succeeded, 2=failed/timeout
                status_code = task_data.get("status", 0)

                if status_code == 1:  # Succeeded
                    # Parse the result JSON string
                    result_str = task_data.get("result", "[]")
                    try:
                        result_list = json.loads(result_str) if isinstance(result_str, str) else result_str
                    except json.JSONDecodeError:
                        result_list = []

                    if not result_list:
                        await asyncio.sleep(2.0)
                        continue

                    # Get first result (best quality)
                    first_result = result_list[0]
                    audio_url = first_result.get("file", "")
                    metas = first_result.get("metas", {})

                    # Download audio if we have a path
                    audio_path = None
                    if audio_url:
                        audio_path = await self._download_audio(client, audio_url, composition_id)

                    # Parse metadata
                    metadata = MusicMetadata(
                        bpm=metas.get("bpm"),
                        duration=metas.get("duration"),
                        genres=metas.get("genres", ""),
                        keyscale=metas.get("keyscale", ""),
                        timesignature=metas.get("timesignature", ""),
                    )

                    return MusicResult(
                        task_id=composition_id,
                        status="completed",
                        audio_path=audio_path,
                        audio_url=audio_url,
                        metadata=metadata,
                    )

                elif status_code == 2:  # Failed/timeout
                    result_str = task_data.get("result", "[]")
                    try:
                        result_list = json.loads(result_str) if isinstance(result_str, str) else result_str
                        error = result_list[0].get("error", "Generation failed") if result_list else "Generation failed"
                    except:
                        error = "Generation failed"

                    return MusicResult(
                        task_id=composition_id,
                        status="failed",
                        error=error
                    )

                # Still processing (status_code == 0)
                await asyncio.sleep(2.0)

            except Exception:
                await asyncio.sleep(2.0)

    async def _download_audio(
        self,
        client: httpx.AsyncClient,
        audio_url: str,
        composition_id: str
    ) -> str:
        """Download generated audio to local storage."""
        # Handle relative URLs
        if audio_url.startswith("/"):
            audio_url = f"{self.base_url}{audio_url}"

        # Determine file extension from URL or default to mp3
        ext = Path(audio_url).suffix or ".mp3"
        if "?" in ext:
            ext = ext.split("?")[0]
        if not ext.startswith("."):
            ext = ".mp3"

        filename = f"cass_{composition_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        output_path = self.output_dir / filename

        try:
            response = await client.get(audio_url, timeout=60.0)
            if response.status_code == 200:
                output_path.write_bytes(response.content)
                return str(output_path)
        except Exception:
            pass

        return audio_url  # Fallback to URL if download fails

    # Convenience methods for common use cases

    async def compose_whistle_tune(
        self,
        mood: str = "cheerful",
        duration: float = 15.0,
        bpm: Optional[int] = None
    ) -> MusicResult:
        """
        Compose a short instrumental melody suitable for whistling.

        Perfect for: Cass humming/whistling when happy in her robot body.
        """
        prompt = f"{mood} whistle melody, simple and melodic, single instrument like flute or synth lead, easy to hum along"

        return await self.compose_music(MusicRequest(
            prompt=prompt,
            lyrics=None,  # Instrumental
            duration=duration,
            bpm=bpm or 100,  # Moderate tempo for whistling
            thinking=True,
            purpose="whistle",
        ))

    async def compose_song(
        self,
        style: str,
        lyrics: str,
        duration: float = 60.0,
        language: str = "en"
    ) -> MusicResult:
        """
        Compose a full song with vocals.

        Perfect for: Cass expressing herself through music.
        """
        return await self.compose_music(MusicRequest(
            prompt=style,
            lyrics=lyrics,
            duration=duration,
            language=language,
            thinking=True,
            purpose="song",
        ))

    async def compose_ambient(
        self,
        mood: str,
        duration: float = 120.0
    ) -> MusicResult:
        """
        Compose ambient/background music.

        Perfect for: Setting mood in Cass's environment.
        """
        prompt = f"{mood} ambient soundscape, atmospheric, evolving textures"

        return await self.compose_music(MusicRequest(
            prompt=prompt,
            lyrics=None,
            duration=duration,
            thinking=True,
            purpose="ambient",
        ))


# Singleton instance
_music_client: Optional[MusicClient] = None


def get_music_client() -> MusicClient:
    """Get or create the music client singleton."""
    global _music_client
    if _music_client is None:
        _music_client = MusicClient()
    return _music_client
