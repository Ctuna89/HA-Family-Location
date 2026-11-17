"""Family Location: a Life360 replacement that runs inside Home Assistant.

Location comes from the Home Assistant Companion app (or any device tracker). Places, trips, speeding and
alerts are computed locally; the location never leaves your Home Assistant except to look up addresses on
OpenStreetMap when that option is enabled.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .engine import CircleEngine

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type FamilyLocationConfigEntry = ConfigEntry[CircleEngine]

ATTR_MESSAGE = "message"
SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Optional(ATTR_MESSAGE, default=""): cv.string,
})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Actions: check in, ask for help, send a message and ask for an ETA."""

    async def _run(call: ServiceCall, sos: bool) -> None:
        entity_id = call.data[ATTR_ENTITY_ID]
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            engine: CircleEngine = entry.runtime_data
            member = engine.member_by_entity(entity_id)
            if member is not None:
                await engine.async_check_in(member.id, call.data[ATTR_MESSAGE], sos=sos)
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_a_member",
            translation_placeholders={"entity_id": entity_id},
        )

    async def check_in(call: ServiceCall) -> None:
        await _run(call, sos=False)

    async def sos(call: ServiceCall) -> None:
        await _run(call, sos=True)

    def _engine_member(entity_id: str) -> tuple[CircleEngine, str]:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            engine: CircleEngine = entry.runtime_data
            if (member := engine.member_by_entity(entity_id)) is not None:
                return engine, member.id
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_a_member",
            translation_placeholders={"entity_id": entity_id},
        )

    async def send_message(call: ServiceCall) -> None:
        engine, member_id = _engine_member(call.data[ATTR_ENTITY_ID])
        await engine.async_send_message(member_id, call.context.user_id, call.data[ATTR_MESSAGE])

    async def ask_eta(call: ServiceCall) -> None:
        engine, member_id = _engine_member(call.data[ATTR_ENTITY_ID])
        await engine.async_ask_eta(member_id, call.context.user_id)

    hass.services.async_register(DOMAIN, "check_in", check_in, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, "sos", sos, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, "send_message", send_message, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, "ask_eta", ask_eta, schema=SERVICE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLocationConfigEntry) -> bool:
    engine = CircleEngine(hass, entry)
    entry.runtime_data = engine
    await engine.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FamilyLocationConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def _reload(hass: HomeAssistant, entry: FamilyLocationConfigEntry) -> None:
    """Options changed, or a member or place was added, edited or removed."""
    await hass.config_entries.async_reload(entry.entry_id)
