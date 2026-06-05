"""Config flow for beste.schule."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .api import BesteSchuleApi, BesteSchuleApiError, BesteSchuleAuthError
from .const import CONF_TOKEN, DEFAULT_API_URL, DEFAULT_NAME, DOMAIN


def _value_from_keys(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty string value for any key."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_name_from_data(data: Any) -> str | None:
    """Extract a first name from common API response shapes."""
    if isinstance(data, list):
        for item in data:
            name = _first_name_from_data(item)
            if name:
                return name
        return None

    if not isinstance(data, dict):
        return None

    for key in ("data", "student", "child", "pupil", "person", "user", "profile"):
        name = _first_name_from_data(data.get(key))
        if name:
            return name

    first_name = _value_from_keys(
        data,
        (
            "firstName",
            "first_name",
            "firstname",
            "givenName",
            "given_name",
            "givenname",
            "forename",
            "vorname",
        ),
    )
    if first_name:
        return first_name

    full_name = _value_from_keys(
        data,
        ("displayName", "display_name", "fullName", "full_name"),
    )
    if full_name:
        return full_name.split()[0]

    name = _value_from_keys(data, ("name",))
    if name and " " in name:
        return name.split()[0]

    return None


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Validate the entered token."""
    api = BesteSchuleApi(hass, DEFAULT_API_URL, data[CONF_TOKEN])
    await api.validate_token()
    return _first_name_from_data(await api.fetch_suggested_name_data()) or DEFAULT_NAME


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
