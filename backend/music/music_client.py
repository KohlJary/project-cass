"""
Music generation client for ACE-Step integration.

Provides Cass with the ability to compose music - both vocal tracks
with lyrics and instrumental pieces (for whistling, ambient, etc).
"""

import asyncio
import httpx
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass
from datetime import datetime
import uuid

# ACE-Step API configuration
ACESTEP_API_URL = "http://localhost:8001"  # Default ACE-Step API port
ACESTEP_TIMEOUT = 300.0  # Music generation can take a while


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


@dataclass
class MusicResult:
    """Result of music generation."""
    task_id: str
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed
    error: Optional[str] = None
    generation_info: Optional[dict] = None


class MusicClient:
    """Client for ACE-Step music generation API."""

    def __init__(self, base_url: str = ACESTEP_API_URL):
        self.base_url = base_url
        self.output_dir = Path(__file__).parent.parent / "data" / "music"
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        task_id = str(uuid.uuid4())[:8]

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
        if not request.lyrics:
            if "instrumental" not in request.prompt.lower():
                api_request["prompt"] = f"{request.prompt}. Instrumental, no vocals."

        try:
            async with httpx.AsyncClient() as client:
                # Submit generation task
                response = await client.post(
                    f"{self.base_url}/release_task",
                    json=api_request,
                    timeout=30.0
                )

                if response.status_code != 200:
                    return MusicResult(
                        task_id=task_id,
                        status="failed",
                        error=f"API error: {response.status_code} - {response.text}"
                    )

                result = response.json()
                server_task_id = result.get("task_id", task_id)

                # Poll for completion
                return await self._poll_task(client, server_task_id)

        except httpx.TimeoutException:
            return MusicResult(
                task_id=task_id,
                status="failed",
                error="Generation timed out"
            )
        except Exception as e:
            return MusicResult(
                task_id=task_id,
                status="failed",
                error=str(e)
            )

    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        max_wait: float = ACESTEP_TIMEOUT
    ) -> MusicResult:
        """Poll for task completion."""
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait:
                return MusicResult(
                    task_id=task_id,
                    status="failed",
                    error=f"Timed out after {max_wait}s"
                )

            try:
                response = await client.post(
                    f"{self.base_url}/query_result",
                    json={"task_ids": [task_id]},
                    timeout=30.0
                )

                if response.status_code != 200:
                    await asyncio.sleep(2.0)
                    continue

                results = response.json()
                if not results or task_id not in results:
                    await asyncio.sleep(2.0)
                    continue

                task_result = results[task_id]
                status = task_result.get("status", "pending")

                if status == "completed":
                    audio_url = task_result.get("audio_url")
                    audio_path = task_result.get("audio_path")

                    # Download audio if URL provided
                    if audio_url and not audio_path:
                        audio_path = await self._download_audio(client, audio_url, task_id)

                    return MusicResult(
                        task_id=task_id,
                        status="completed",
                        audio_path=audio_path,
                        audio_url=audio_url,
                        generation_info=task_result.get("generation_info")
                    )

                elif status == "failed":
                    return MusicResult(
                        task_id=task_id,
                        status="failed",
                        error=task_result.get("error", "Unknown error")
                    )

                # Still processing
                await asyncio.sleep(2.0)

            except Exception as e:
                await asyncio.sleep(2.0)

    async def _download_audio(
        self,
        client: httpx.AsyncClient,
        audio_url: str,
        task_id: str
    ) -> str:
        """Download generated audio to local storage."""
        # Determine file extension from URL or default to mp3
        ext = Path(audio_url).suffix or ".mp3"
        filename = f"cass_composition_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        output_path = self.output_dir / filename

        response = await client.get(audio_url, timeout=60.0)
        if response.status_code == 200:
            output_path.write_bytes(response.content)
            return str(output_path)

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
        prompt = f"{mood} whistle melody, simple and melodic, single instrument like flute or synth lead, easy to hum along. Instrumental, no vocals."

        return await self.compose_music(MusicRequest(
            prompt=prompt,
            lyrics=None,  # Instrumental
            duration=duration,
            bpm=bpm or 100,  # Moderate tempo for whistling
            thinking=True
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
            thinking=True
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
        prompt = f"{mood} ambient soundscape, atmospheric, evolving textures. Instrumental, no vocals."

        return await self.compose_music(MusicRequest(
            prompt=prompt,
            lyrics=None,
            duration=duration,
            thinking=True
        ))


# Singleton instance
_music_client: Optional[MusicClient] = None


def get_music_client() -> MusicClient:
    """Get or create the music client singleton."""
    global _music_client
    if _music_client is None:
        _music_client = MusicClient()
    return _music_client
