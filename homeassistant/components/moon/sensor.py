"""Support for tracking the moon phases."""
from __future__ import annotations

import logging

from astral import moon
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    MOON_ICONS,
    STATE_FIRST_QUARTER,
    STATE_FULL_MOON,
    STATE_LAST_QUARTER,
    STATE_NEW_MOON,
    STATE_WANING_CRESCENT,
    STATE_WANING_GIBBOUS,
    STATE_WAXING_CRESCENT,
    STATE_WAXING_GIBBOUS,
)

DEFAULT_NAME = "Moon"

_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string}
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import Moon configuration from yaml."""
    _LOGGER.warning(
        "Configuration of the moon platform in YAML is deprecated and will be "
        "removed in Home Assistant 2022.5; Your existing configuration "
        "has been imported into the UI automatically and can be safely removed "
        "from your configuration.yaml file"
    )
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=config,
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    async_add_entities([MoonSensor(name)], True)


class MoonSensor(SensorEntity):
    """Representation of a Moon sensor."""

    def __init__(self, name):
        """Initialize the moon sensor."""
        self._name = name
        self._state = None

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    @property
    def device_class(self):
        """Return the device class of the entity."""
        return "moon__phase"

    @property
    def native_value(self):
        """Return the state of the device."""
        if self._state < 0.5 or self._state > 27.5:
            return STATE_NEW_MOON
        if self._state < 6.5:
            return STATE_WAXING_CRESCENT
        if self._state < 7.5:
            return STATE_FIRST_QUARTER
        if self._state < 13.5:
            return STATE_WAXING_GIBBOUS
        if self._state < 14.5:
            return STATE_FULL_MOON
        if self._state < 20.5:
            return STATE_WANING_GIBBOUS
        if self._state < 21.5:
            return STATE_LAST_QUARTER
        return STATE_WANING_CRESCENT

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return MOON_ICONS.get(self.state)

    async def async_update(self):
        """Get the time and updates the states."""
        today = dt_util.as_local(dt_util.utcnow()).date()
        self._state = moon.phase(today)
