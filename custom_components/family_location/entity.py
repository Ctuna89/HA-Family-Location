"""Base de las entidades: un dispositivo por integrante y otro por lugar."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .engine import CircleEngine, MemberConfig, PlaceConfig
from .tracker import MemberTracker


class FamilyLocationEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, engine: CircleEngine) -> None:
        self.engine = engine

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, self.engine.signal, self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


class MemberEntity(FamilyLocationEntity):
    def __init__(self, engine: CircleEngine, member: MemberConfig, key: str) -> None:
        super().__init__(engine)
        self.member = member
        self._attr_translation_key = key
        self._attr_unique_id = f"{member.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, member.id)},
            name=member.name,
            manufacturer="Family Location",
            model=engine.entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def tracker(self) -> MemberTracker:
        return self.engine.trackers[self.member.id]

    @property
    def available(self) -> bool:
        return self.tracker.initialized


class PlaceEntity(FamilyLocationEntity):
    def __init__(self, engine: CircleEngine, place: PlaceConfig, key: str) -> None:
        super().__init__(engine)
        self.place = place
        self._attr_translation_key = key
        self._attr_unique_id = f"{place.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, place.id)},
            name=place.name,
            manufacturer="Family Location",
            model=engine.entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
