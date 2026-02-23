"""
Base class for art providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ArtworkData:
    """Standardized artwork data from any provider."""
    title: str
    artist_name: str
    year: Optional[int] = None
    medium: Optional[str] = None
    image_url: Optional[str] = None
    dimensions: Optional[str] = None
    source_id: Optional[str] = None  # ID in the source system
    source_url: Optional[str] = None  # URL to view on source site


class ArtProvider(ABC):
    """Abstract base class for art data providers."""

    name: str = "base"
    display_name: str = "Base Provider"

    @abstractmethod
    async def search_artist(self, artist_name: str) -> Optional[dict]:
        """
        Search for an artist and return basic info.

        Returns dict with at least: name, url (if available)
        """
        pass

    @abstractmethod
    async def get_artworks_by_artist(
        self,
        artist_name: str,
        limit: int = 10,
    ) -> list[ArtworkData]:
        """
        Fetch artworks by an artist.

        Args:
            artist_name: Name of the artist to search for
            limit: Maximum number of artworks to return

        Returns:
            List of ArtworkData objects
        """
        pass

    @abstractmethod
    async def get_artist_url(self, artist_name: str) -> Optional[str]:
        """Get the URL to view an artist on this provider's site."""
        pass

    async def download_image(self, image_url: str, save_path: str) -> bool:
        """
        Download an image from a URL.

        Default implementation uses httpx. Providers can override if needed.
        """
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    image_url,
                    headers={"User-Agent": "CassVessel/1.0 (Art Study System)"},
                    timeout=60,
                    follow_redirects=True,
                )
                if response.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(response.content)
                    return True
        except Exception:
            pass
        return False
