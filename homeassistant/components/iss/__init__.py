"""The iss component."""
from __future__ import annotations

import datetime
import logging

import pyiss
import requests
from requests.exceptions import HTTPError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]


class ISSDataObject:
    """Iss Data object."""

    is_above: bool | None = None
    next_rise: str | None = None
    number_of_people_in_space: int | None = None
    position: dict = {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""

    hass.data.setdefault(DOMAIN, {})

    latitude = hass.config.latitude
    longitude = hass.config.longitude

    async def async_update():
        try:
            data = ISSDataObject
            iss = pyiss.ISS()

            data.is_above = iss.is_ISS_above(latitude, longitude)
            data.next_rise = iss.next_rise(latitude, longitude)
            data.number_of_people_in_space = iss.number_of_people_in_space()
            data.position = iss.current_location()

            return data
        except (HTTPError, requests.exceptions.ConnectionError) as ex:
            raise UpdateFailed(ex) from ex

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update,
        update_interval=datetime.timedelta(seconds=60),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN] = coordinator

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        del hass.data[DOMAIN]
    return unload_ok
