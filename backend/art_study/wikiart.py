"""
Art Import Module

Fetch artworks from external sources (Met Museum, WikiArt, etc.)
to populate the art study system.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Artwork
from . import persistence
from .providers import get_provider, PROVIDERS, DEFAULT_PROVIDER

logger = logging.getLogger(__name__)

# Where to store downloaded artwork images
ARTWORK_IMAGE_DIR = Path("data/art_study/images")


async def import_artist_from_provider(
    artist_id: str,
    max_works: int = 10,
    provider_name: str | None = None,
    search_name: str | None = None,
) -> dict:
    """
    Import artworks for an existing artist from an external provider.

    Args:
        artist_id: ID of the artist in our database
        max_works: Maximum number of works to import
        provider_name: Which provider to use (default: met)
        search_name: Override name to use when searching (for artists with alternate names)

    Returns:
        Dict with status and counts
    """
    artist = persistence.get_artist(artist_id)
    if not artist:
        return {"status": "error", "message": "Artist not found"}

    # Get the provider
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    # Use override search name if provided, otherwise use artist's name
    name_to_search = search_name or artist.name
    logger.info(f"Fetching artworks for {name_to_search} from {provider.display_name}")

    # Fetch artworks
    artworks_data = await provider.get_artworks_by_artist(name_to_search, limit=max_works)

    if not artworks_data:
        return {
            "status": "error",
            "message": f"No artworks found for {artist.name} on {provider.display_name}. "
                      f"Try checking the artist name spelling.",
            "provider": provider.name,
        }

    imported = 0
    skipped = 0
    failed = 0

    # Ensure image directory exists
    ARTWORK_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    for artwork_data in artworks_data:
        # Check if we already have this artwork
        existing_artworks = persistence.list_artworks_for_artist(artist_id)
        if any(a.title.lower() == artwork_data.title.lower() for a in existing_artworks):
            skipped += 1
            continue

        # Create artwork record
        artwork_id = str(uuid.uuid4())
        artwork = Artwork(
            id=artwork_id,
            artist_id=artist_id,
            title=artwork_data.title,
            year=artwork_data.year,
            medium=artwork_data.medium,
            dimensions=artwork_data.dimensions,
            image_url=artwork_data.image_url,
            public_domain=True,
            created_at=datetime.utcnow().isoformat(),
        )

        # Download the image if we have a URL
        if artwork_data.image_url:
            ext = ".jpg"
            if ".png" in artwork_data.image_url.lower():
                ext = ".png"
            local_path = ARTWORK_IMAGE_DIR / f"{artwork_id}{ext}"

            success = await provider.download_image(artwork_data.image_url, str(local_path))
            if success:
                artwork.image_path = str(local_path)
                logger.info(f"Downloaded: {artwork_data.title}")
            else:
                logger.warning(f"Failed to download image for: {artwork_data.title}")
                failed += 1
                continue

        # Save the artwork
        persistence.save_artwork(artwork)
        imported += 1

    return {
        "status": "success",
        "provider": provider.name,
        "provider_name": provider.display_name,
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "message": f"Imported {imported} artworks from {provider.display_name}, "
                  f"skipped {skipped} duplicates, {failed} failed"
    }


async def get_provider_url_for_artist(
    artist_name: str,
    provider_name: str | None = None,
) -> Optional[str]:
    """Get the URL to view an artist on a provider's site."""
    provider = get_provider(provider_name)
    return await provider.get_artist_url(artist_name)


def list_providers() -> list[dict]:
    """List available art providers."""
    return [
        {
            "id": name,
            "name": PROVIDERS[name]().display_name,
            "is_default": name == DEFAULT_PROVIDER,
        }
        for name in PROVIDERS
    ]


# Aliases for backwards compatibility
import_artist_from_wikiart = import_artist_from_provider
get_wikiart_url_for_artist = get_provider_url_for_artist
