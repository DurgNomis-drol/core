"""Support for ESPHome binary sensors."""
from __future__ import annotations

from aioesphomeapi import BinarySensorInfo, BinarySensorState

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.enum import try_parse_enum

from . import EsphomeAssistEntity, EsphomeEntity, platform_async_setup_entry
from .domain_data import DomainData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up ESPHome binary sensors based on a config entry."""
    await platform_async_setup_entry(
        hass,
        entry,
        async_add_entities,
        component_key="binary_sensor",
        info_type=BinarySensorInfo,
        entity_type=EsphomeBinarySensor,
        state_type=BinarySensorState,
    )

    entry_data = DomainData.get(hass).get_entry_data(entry)
    assert entry_data.device_info is not None
    if entry_data.device_info.voice_assistant_version:
        async_add_entities([EsphomeCallActiveBinarySensor(entry_data)])


class EsphomeBinarySensor(
    EsphomeEntity[BinarySensorInfo, BinarySensorState], BinarySensorEntity
):
    """A binary sensor implementation for ESPHome."""

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self._static_info.is_status_binary_sensor:
            # Status binary sensors indicated connected state.
            # So in their case what's usually _availability_ is now state
            return self._entry_data.available
        if not self._has_state:
            return None
        if self._state.missing_state:
            return None
        return self._state.state

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return try_parse_enum(BinarySensorDeviceClass, self._static_info.device_class)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self._static_info.is_status_binary_sensor:
            return True
        return super().available


class EsphomeCallActiveBinarySensor(EsphomeAssistEntity, BinarySensorEntity):
    """A binary sensor implementation for ESPHome for use with assist_pipeline."""

    entity_description = BinarySensorEntityDescription(
        key="call_active",
        translation_key="call_active",
    )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._entry_data.assist_pipeline_state
