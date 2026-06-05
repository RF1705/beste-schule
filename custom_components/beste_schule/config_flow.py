"""Config flow for beste.schule."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .api import BesteSchuleApi, BesteSchuleApiError
from .const import CONF_API_URL, CONF_TOKEN, DEFAULT_API_URL, DOMAIN


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the entered token."""
    api = BesteSchuleApi(hass, data[CONF_API_URL], data[CONF_TOKEN])
    await api.validate_token()


class BesteSchuleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for beste.schule."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate_input(self.hass, user_input)
            except BesteSchuleApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id("beste_schule")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="beste.schule", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
