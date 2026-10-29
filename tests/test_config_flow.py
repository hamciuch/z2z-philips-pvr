"""Config flow tests."""

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.z2z_philips_pvr.const import CONF_SOURCE_ENTRY, DOMAIN

from .conftest import HOST, FakeTV

MANUAL = {CONF_HOST: HOST, CONF_USERNAME: "user", CONF_PASSWORD: "pass"}


async def test_manual(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], MANUAL)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "65PUS8857/12"
    assert result["data"] == MANUAL


async def test_manual_invalid_auth(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    fake_tv.auth_ok = False
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], MANUAL)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    fake_tv.auth_ok = True
    result = await hass.config_entries.flow.async_configure(result["flow_id"], MANUAL)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_not_supported(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    async def no_pvr():
        return {"name": "Old TV", "jsonfeatures": {}}

    fake_tv.get_system = no_pvr
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], MANUAL)
    assert result["errors"] == {"base": "not_supported"}


async def test_reuse_philips_js(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    source = MockConfigEntry(
        domain="philips_js",
        title="Salon",
        data={
            CONF_HOST: HOST,
            CONF_USERNAME: "u1",
            CONF_PASSWORD: "p1",
            "api_version": 6,
        },
    )
    source.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reuse"}
    )
    assert result["step_id"] == "reuse"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE_ENTRY: source.entry_id}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_USERNAME: "u1", CONF_PASSWORD: "p1"}


async def test_already_configured(
    hass: HomeAssistant, fake_tv: FakeTV, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], MANUAL)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, fake_tv: FakeTV, setup_integration: MockConfigEntry
) -> None:
    result = await setup_integration.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "new", CONF_PASSWORD: "newpass"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_integration.data[CONF_USERNAME] == "new"
