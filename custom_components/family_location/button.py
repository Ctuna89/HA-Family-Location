"""Per-member buttons: «Check in» (tell everyone where I am) and «Ask for help» (SOS)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FamilyLocationConfigEntry
from .entity import MemberEntity


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLocationConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    engine = entry.runtime_data
    for member in engine.members.values():
        async_add_entities([CheckInButton(engine, member), SosButton(engine, member)],
                           config_subentry_id=member.id)


class CheckInButton(MemberEntity, ButtonEntity):
    _attr_icon = "mdi:map-marker-check"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "check_in")

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.engine.async_check_in(self.member.id)


class SosButton(MemberEntity, ButtonEntity):
    _attr_icon = "mdi:alarm-light"

    def __init__(self, engine: Any, member: Any) -> None:
        super().__init__(engine, member, "sos")

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.engine.async_check_in(self.member.id, sos=True)
