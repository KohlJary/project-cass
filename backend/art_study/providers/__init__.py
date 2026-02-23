"""
Art Study Providers

Pluggable providers for fetching artwork data from various sources.
"""

from .base import ArtProvider, ArtworkData
from .met_museum import MetMuseumProvider
from .wikiart import WikiArtProvider

# Available providers
PROVIDERS = {
    "met": MetMuseumProvider,
    "wikiart": WikiArtProvider,
}

# Default provider
DEFAULT_PROVIDER = "met"


def get_provider(name: str | None = None) -> ArtProvider:
    """Get an art provider by name."""
    provider_name = name or DEFAULT_PROVIDER
    if provider_name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(PROVIDERS.keys())}")
    return PROVIDERS[provider_name]()


__all__ = [
    "ArtProvider",
    "ArtworkData",
    "MetMuseumProvider",
    "WikiArtProvider",
    "PROVIDERS",
    "DEFAULT_PROVIDER",
    "get_provider",
]
