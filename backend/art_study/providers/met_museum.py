"""
Metropolitan Museum of Art API Provider

Free API with no authentication required.
https://metmuseum.github.io/
"""

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import quote

import httpx

from .base import ArtProvider, ArtworkData

logger = logging.getLogger(__name__)

BASE_URL = "https://collectionapi.metmuseum.org/public/collection/v1"

# Headers to avoid WAF blocking
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


class MetMuseumProvider(ArtProvider):
    """Provider for Metropolitan Museum of Art's Open Access API."""

    name = "met"
    display_name = "Metropolitan Museum of Art"

    async def search_artist(self, artist_name: str) -> Optional[dict]:
        """Search for an artist in the Met's collection."""
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS) as client:
            try:
                # Search with artistOrCulture flag
                url = f"{BASE_URL}/search"
                params = {
                    "artistOrCulture": "true",
                    "q": artist_name,
                    "hasImages": "true",
                }
                response = await client.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("total", 0) > 0:
                        return {
                            "name": artist_name,
                            "total_works": data["total"],
                            "object_ids": data.get("objectIDs", []),
                        }
            except Exception as e:
                logger.error(f"Error searching Met for {artist_name}: {e}")
        return None

    async def get_artworks_by_artist(
        self,
        artist_name: str,
        limit: int = 10,
    ) -> list[ArtworkData]:
        """Fetch artworks by an artist from the Met."""
        artworks = []

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS) as client:
            try:
                # Search for the artist name (general search works better than artistOrCulture)
                search_url = f"{BASE_URL}/search"
                params = {
                    "q": artist_name,
                    "hasImages": "true",
                }
                response = await client.get(search_url, params=params, timeout=30)

                if response.status_code != 200:
                    logger.error(f"Met search failed: {response.status_code}")
                    return []

                data = response.json()
                object_ids = data.get("objectIDs", [])

                if not object_ids:
                    logger.info(f"No artworks found for {artist_name} at Met")
                    return []

                logger.info(f"Found {len(object_ids)} potential works for {artist_name}")

                # Fetch details for each object (with rate limiting)
                # Met allows 80 req/sec, but let's be conservative
                fetched = 0
                for obj_id in object_ids[:limit * 2]:  # Fetch extra in case some aren't by this artist
                    if fetched >= limit:
                        break

                    try:
                        obj_url = f"{BASE_URL}/objects/{obj_id}"
                        obj_response = await client.get(obj_url, timeout=30)

                        if obj_response.status_code == 200:
                            obj_data = obj_response.json()

                            # Verify this is actually by the artist we're looking for
                            obj_artist = obj_data.get("artistDisplayName", "")
                            if not self._artist_matches(artist_name, obj_artist):
                                continue

                            # Only include if there's an image
                            image_url = obj_data.get("primaryImage") or obj_data.get("primaryImageSmall")
                            if not image_url:
                                continue

                            # Parse year from objectDate
                            year = self._parse_year(obj_data.get("objectDate", ""))

                            artwork = ArtworkData(
                                title=obj_data.get("title", "Untitled"),
                                artist_name=obj_artist or artist_name,
                                year=year,
                                medium=obj_data.get("medium"),
                                image_url=image_url,
                                dimensions=obj_data.get("dimensions"),
                                source_id=str(obj_id),
                                source_url=obj_data.get("objectURL"),
                            )
                            artworks.append(artwork)
                            fetched += 1
                            logger.debug(f"Found: {artwork.title}")

                        # Small delay to be nice to the API
                        await asyncio.sleep(0.05)

                    except Exception as e:
                        logger.warning(f"Error fetching object {obj_id}: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error fetching artworks from Met: {e}")

        logger.info(f"Returning {len(artworks)} artworks for {artist_name}")
        return artworks

    async def get_artist_url(self, artist_name: str) -> Optional[str]:
        """Get a Met search URL for an artist."""
        encoded_name = quote(artist_name)
        return f"https://www.metmuseum.org/art/collection/search?artist={encoded_name}"

    def _artist_matches(self, search_name: str, found_name: str) -> bool:
        """Check if the found artist name matches who we're looking for."""
        if not found_name:
            return False

        search_lower = search_name.lower()
        found_lower = found_name.lower()

        # Direct match
        if search_lower in found_lower or found_lower in search_lower:
            return True

        # Check last name match (for "Vincent van Gogh" matching "Gogh, Vincent van")
        search_parts = search_lower.split()
        found_parts = found_lower.replace(",", "").split()

        # Check if all search words appear in found name
        return all(part in found_parts for part in search_parts if len(part) > 2)

    def _parse_year(self, date_str: str) -> Optional[int]:
        """Parse a year from Met's objectDate field."""
        if not date_str:
            return None

        # Try to find a 4-digit year
        match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', date_str)
        if match:
            return int(match.group(1))

        return None
