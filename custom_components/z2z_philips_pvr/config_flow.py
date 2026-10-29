"""Config flow: reuse the Philips TV integration credentials or enter them manually."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import PhilipsPvrApi, PhilipsPvrAuthError, PhilipsPvrError
from .const import CONF_SOURCE_ENTRY, DOMAIN, PHILIPS_JS_DOMAIN

_LOGGER = logging.getLogger(__name__)


class NotSupported(Exception):
    """TV does not expose the recordings API."""


async def validate(hass: HomeAssistant, data: Mapping[str, Any]) -> str:
    """Check credentials and recordings support. Return a title."""
    api = PhilipsPvrApi(
        get_async_client(hass, verify_ssl=False),
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )
    system = await api.get_system()
    features = (system.get("jsonfeatures") or {}).get("recordings") or []
    if "List" not in features:
        raise NotSupported
    await api.get_recordings()
    return str(system.get("name") or data[CONF_HOST])


class PhilipsPvrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def _philips_entries(self) -> dict[str, Any]:
        return {
            entry.entry_id: entry
            for entry in self.hass.config_entries.async_entries(PHILIPS_JS_DOMAIN)
            if entry.data.get(CONF_USERNAME) and entry.data.get(CONF_PASSWORD)
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer import from the Philips TV integration when it exists."""
        if self._philips_entries():
            return self.async_show_menu(
                step_id="user", menu_options=["reuse", "manual"]
            )
        return await self.async_step_manual()

    async def _create(
        self, step_id: str, data: dict[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        await self.async_set_unique_id(data[CONF_HOST])
        self._abort_if_unique_id_configured(updates=data)
        try:
            title = await validate(self.hass, data)
        except PhilipsPvrAuthError:
            errors["base"] = "invalid_auth"
        except NotSupported:
            errors["base"] = "not_supported"
        except PhilipsPvrError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=title, data=data)
        return None

    async def async_step_reuse(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Copy host and credentials from a Philips TV config entry."""
        entries = self._philips_entries()
        errors: dict[str, str] = {}
        if user_input is not None:
            source = entries.get(user_input[CONF_SOURCE_ENTRY])
            if source is None:
                errors["base"] = "unknown"
            else:
                data = {
                    CONF_HOST: source.data[CONF_HOST],
                    CONF_USERNAME: source.data[CONF_USERNAME],
                    CONF_PASSWORD: source.data[CONF_PASSWORD],
                }
                if result := await self._create("reuse", data, errors):
                    return result
        options = [
            SelectOptionDict(
                value=entry_id, label=f"{entry.title} ({entry.data[CONF_HOST]})"
            )
            for entry_id, entry in entries.items()
        ]
        return self.async_show_form(
            step_id="reuse",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE_ENTRY): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter host and JointSPACE digest credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if result := await self._create("manual", dict(user_input), errors):
                return result
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Credentials stopped working (e.g. the TV was re-paired)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                await validate(self.hass, data)
            except PhilipsPvrAuthError:
                errors["base"] = "invalid_auth"
            except NotSupported:
                errors["base"] = "not_supported"
            except PhilipsPvrError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
            ),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )
