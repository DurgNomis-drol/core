"""Support for International Space Station binary sensor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.iss import ISSDataObject
from homeassistant.components.iss.const import (
    ATTR_ISS_NEXT_RISE,
    ATTR_ISS_NUMBER_PEOPLE_SPACE,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_NAME,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_NAME,
    CONF_SHOW_ON_MAP,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SHOW_ON_MAP, default=False): cv.boolean,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import ISS configuration from yaml."""
    _LOGGER.warning(
        "Configuration of the iss platform in YAML is deprecated and will be "
        "removed in Home Assistant 2022.4; Your existing configuration "
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
    show_on_map = entry.data.get(CONF_SHOW_ON_MAP, False)

    coordinator = hass.data[DOMAIN]

    async_add_entities(
        [
            IssBinarySensor(
                coordinator,
                entry.entry_id,
                show_on_map,
                BinarySensorEntityDescription(
                    key="iss",
                    name=name,
                    icon="mdi:space-station",
                    device_class=DEFAULT_DEVICE_CLASS,
                ),
            ),
        ]
    )


class IssBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Implementation of the ISS binary sensor."""

    _iss_data: ISSDataObject | None = None

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        show_on_map: bool,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize a Launch Library entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._show_on_map = show_on_map

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self._iss_data is None:
            return None
        return self._iss_data.is_above

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        return super().available and self._iss_data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the attributes of the sensor."""
        if self._iss_data is None:
            return None
        attrs = {
            ATTR_ISS_NUMBER_PEOPLE_SPACE: self._iss_data.number_of_people_in_space,
            ATTR_ISS_NEXT_RISE: self._iss_data.next_rise,
        }
        if self._show_on_map:
            attrs[ATTR_LONGITUDE] = self._iss_data.position.get("longitude")
            attrs[ATTR_LATITUDE] = self._iss_data.position.get("latitude")
        else:
            attrs["long"] = self._iss_data.position.get("longitude")
            attrs["lat"] = self._iss_data.position.get("latitude")

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._iss_data = self.coordinator.data
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
