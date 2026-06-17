"""Config flow for beste.schule."""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .api import BesteSchuleApi, BesteSchuleApiError, BesteSchuleAuthError
from .const import (
    CONF_ENABLE_ABSENCE_CALENDAR,
    CONF_ENABLE_EXAM_CALENDAR,
    CONF_ENABLE_HOMEWORK_CALENDAR,
    CONF_ENABLE_HOMEWORK_TODO,
    CONF_ENABLE_TIMETABLE_CALENDAR,
    CONF_TOKEN,
    DEFAULT_API_URL,
    DEFAULT_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
)


OPTION_KEYS = (
    CONF_ENABLE_TIMETABLE_CALENDAR,
    CONF_ENABLE_ABSENCE_CALENDAR,
    CONF_ENABLE_HOMEWORK_CALENDAR,
    CONF_ENABLE_EXAM_CALENDAR,
    CONF_ENABLE_HOMEWORK_TODO,
)


def _options_schema(options: dict[str, bool]) -> vol.Schema:
    """Return the shared feature options schema."""
    return vol.Schema(
        {
            vol.Required(key, default=options[key]): bool
            for key in OPTION_KEYS
        }
    )


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


def _token_unique_id(token: str) -> str:
    """Return a stable unique id for one token without storing it in plain text."""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"token_{digest}"


def _token_already_configured(
    entries: list[config_entries.ConfigEntry],
    token: str,
) -> bool:
    """Return whether this exact token is already configured."""
    return any(entry.data.get(CONF_TOKEN) == token for entry in entries)


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Validate the entered token."""
    api = BesteSchuleApi(hass, DEFAULT_API_URL, data[CONF_TOKEN])
    await api.validate_token()
    return _first_name_from_data(await api.fetch_suggested_name_data()) or DEFAULT_NAME


class BesteSchuleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for beste.schule."""

    VERSION = 1

    _token: str
    _title: str

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return BesteSchuleOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN]
            try:
                title = await _validate_input(self.hass, user_input)
            except BesteSchuleAuthError:
                errors["base"] = "invalid_auth"
            except BesteSchuleApiError:
                errors["base"] = "cannot_connect"
            else:
                if _token_already_configured(self._async_current_entries(), token):
                    return self.async_abort(reason="already_configured")
                await self.async_set_unique_id(_token_unique_id(token))
                self._abort_if_unique_id_configured()
                self._token = token
                self._title = title
                return await self.async_step_features()

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

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user choose optional entities during setup."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._title,
                data={CONF_TOKEN: self._token},
                options=user_input,
            )

        return self.async_show_form(
            step_id="features",
            data_schema=_options_schema(DEFAULT_OPTIONS),
        )


class BesteSchuleOptionsFlow(config_entries.OptionsFlow):
    """Handle options for beste.schule."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage beste.schule options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {**DEFAULT_OPTIONS, **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(options),
        )
