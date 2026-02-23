"""
WikiArt Provider

Note: WikiArt requires API keys from https://www.wikiart.org/en/App/GetApi
May be rate-limited or unavailable without keys.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx

from .base import ArtProvider, ArtworkData

logger = logging.getLogger(__name__)

WIKIART_BASE = "https://www.wikiart.org/en"


class WikiArtProvider(ArtProvider):
    """Provider for WikiArt.org."""

    name = "wikiart"
    display_name = "WikiArt"

    def __init__(self):
        self.access_key, self.secret_key = self._get_credentials()

    def _get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """Get WikiArt API credentials."""
        # Try environment variables first
        access_key = os.environ.get("WIKIART_ACCESS_KEY")
        secret_key = os.environ.get("WIKIART_SECRET_KEY")

        if access_key and secret_key:
            return access_key, secret_key

        # Try .wiki_api file
        api_file = Path(".wiki_api")
        if api_file.exists():
            lines = api_file.read_text().strip().split("\n")
            if len(lines) >= 2:
                return lines[0].strip(), lines[1].strip()

        return None, None

    def _artist_name_to_slug(self, name: str) -> str:
        """Convert artist name to WikiArt URL slug."""
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        return slug

    async def search_artist(self, artist_name: str) -> Optional[dict]:
        """Search for an artist on WikiArt."""
        async with httpx.AsyncClient() as client:
            params = {}
            if self.access_key and self.secret_key:
                params["accessKey"] = self.access_key
                params["secretKey"] = self.secret_key

            # Try direct lookup
            slug = self._artist_name_to_slug(artist_name)
            url = f"{WIKIART_BASE}/App/Artist/artistName/{slug}"

            try:
                response = await client.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    if data and not data.get("error"):
                        return data
            except Exception as e:
                logger.debug(f"WikiArt direct lookup failed: {e}")

            # Try search
            search_url = f"{WIKIART_BASE}/App/Search/Artists"
            params["term"] = artist_name

            try:
                response = await client.get(search_url, params=params, timeout=30)
                if response.status_code == 200:
                    results = response.json()
                    if results and len(results) > 0:
                        return results[0]
            except Exception as e:
                logger.debug(f"WikiArt search failed: {e}")

        return None

    async def get_artworks_by_artist(
        self,
        artist_name: str,
        limit: int = 10,
    ) -> list[ArtworkData]:
        """Fetch artworks by an artist from WikiArt."""
        artworks = []
        slug = self._artist_name_to_slug(artist_name)

        async with httpx.AsyncClient() as client:
            params = {"json": "2"}
            if self.access_key and self.secret_key:
                params["accessKey"] = self.access_key
                params["secretKey"] = self.secret_key

            params["artistUrl"] = slug
            url = f"{WIKIART_BASE}/App/Painting/PaintingsByArtist"

            try:
                response = await client.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    paintings = []
                    if isinstance(data, list):
                        paintings = data[:limit]
                    elif isinstance(data, dict) and "Paintings" in data:
                        paintings = data["Paintings"][:limit]

                    for p in paintings:
                        title = p.get("title") or p.get("Title") or "Untitled"
                        image_url = p.get("image") or p.get("Image")
                        year_str = p.get("year") or p.get("completitionYear") or p.get("yearAsString")

                        year = None
                        if isinstance(year_str, str):
                            match = re.search(r'\d{4}', year_str)
                            year = int(match.group()) if match else None
                        elif isinstance(year_str, int):
                            year = year_str

                        artwork = ArtworkData(
                            title=title,
                            artist_name=artist_name,
                            year=year,
                            medium=p.get("technique") or p.get("Technique"),
                            image_url=image_url,
                            source_id=p.get("id") or p.get("contentId"),
                            source_url=p.get("url"),
                        )
                        artworks.append(artwork)

            except Exception as e:
                logger.error(f"Error fetching from WikiArt: {e}")

        return artworks

    async def get_artist_url(self, artist_name: str) -> Optional[str]:
        """Get WikiArt URL for an artist."""
        slug = self._artist_name_to_slug(artist_name)
        return f"https://www.wikiart.org/en/{slug}"
