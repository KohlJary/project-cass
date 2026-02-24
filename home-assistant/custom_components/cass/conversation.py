"""Conversation platform for Cass."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationEntity, ConversationInput, ConversationResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import intent

from .const import DOMAIN, CONF_HOST, CONF_PORT

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cass conversation platform."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([CassConversationEntity(config_entry, config)])


class CassConversationEntity(ConversationEntity):
    """Cass conversation agent."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, config_entry: ConfigEntry, config: dict[str, Any]) -> None:
        """Initialize the Cass conversation entity."""
        self._config_entry = config_entry
        self._host = config[CONF_HOST]
        self._port = config[CONF_PORT]
        self._attr_unique_id = config_entry.entry_id
        self._conversation_id: str | None = None

    @property
    def supported_languages(self) -> list[str]:
        """Return supported languages."""
        return ["en"]  # Cass supports English

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a sentence."""
        url = f"http://{self._host}:{self._port}/api/ha/conversation"

        # Build request payload
        payload = {
            "text": user_input.text,
            "conversation_id": user_input.conversation_id or self._conversation_id,
            "language": user_input.language,
            "device_id": user_input.device_id,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=60.0,  # LLM responses can take a while
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPError as err:
            _LOGGER.error("Error communicating with Cass: %s", err)
            return ConversationResult(
                response=intent.IntentResponse(language=user_input.language),
                conversation_id=user_input.conversation_id,
            )

        # Store conversation ID for continuity
        self._conversation_id = data.get("conversation_id")

        # Build response
        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(data.get("response", ""))

        return ConversationResult(
            response=intent_response,
            conversation_id=self._conversation_id,
        )
