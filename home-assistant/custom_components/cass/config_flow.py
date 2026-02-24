"""Config flow for Cass integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import httpx

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)


async def validate_connection(host: str, port: int) -> dict[str, Any]:
    """Validate the connection to Cass backend."""
    url = f"http://{host}:{port}/health"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            return {"title": "Cass"}
    except httpx.ConnectError:
        raise CannotConnect
    except httpx.TimeoutException:
        raise CannotConnect
    except Exception as err:
        _LOGGER.error("Unexpected error connecting to Cass: %s", err)
        raise CannotConnect


class CassConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cass."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_connection(
                    user_input[CONF_HOST],
                    user_input[CONF_PORT]
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
