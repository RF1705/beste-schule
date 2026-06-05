"""Config flow for beste.schule."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .api import BesteSchuleApi, BesteSchuleApiError, BesteSchuleAuthError
from .const import CONF_TOKEN, DEFAULT_API_URL, DEFAULT_NAME, DOMAIN


def _name_from_data(data: Any) -> str | None:
    """Extract a readable person name from common API response shapes."""
    if isinstance(data, list):
        for item in data:
            name = _name_from_data(item)
            if name:
                return name
        return None

    if not isinstance(data, dict):
        return None

    for key in ("data", "student", "child", "pupil", "person", "user", "profile"):
        name = _name_from_data(data.get(key))
        if name:
            return name

    for key in ("displayName", "display_name", "fullName", "full_name", "name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    first_name = data.get("firstName") or data.get("first_name") or data.get("firstname")
    last_name = data.get("lastName") or data.get("last_name") or data.get("lastname")
    parts = [part.strip() for part in (first_name, last_name) if isinstance(part, str)]
    if parts:
        return " ".join(parts)

    return None


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Validate the entered token."""
    api = BesteSchuleApi(hass, DEFAULT_API_URL, data[CONF_TOKEN])
    await api.validate_token()
    return _name_from_data(await api.fetch_suggested_name_data()) or DEFAULT_NAME


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
                title = await _validate_input(self.hass, user_input)
            except BesteSchuleAuthError:
                errors["base"] = "invalid_auth"
            except BesteSchuleApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id("beste_schule")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title,
                    data={CONF_TOKEN: user_input[CONF_TOKEN]},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
