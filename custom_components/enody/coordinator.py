"""Coordinator for the Enody integration."""

import asyncio
from contextlib import suppress
from datetime import timedelta
from logging import getLogger

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EnodyClient, EnodyDependencyError, EnodyDeviceInfo, EnodyError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

LOGGER = getLogger(__name__)


class EnodyCoordinator(DataUpdateCoordinator[EnodyDeviceInfo]):
    """Refresh Enody device metadata and availability."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EnodyClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
            always_update=False,
        )
        self.client = client
        self._stopping = False
        self._recovery_task: asyncio.Task[None] | None = None

    @callback
    def async_command_failed(self, err: EnodyError) -> None:
        """Report failure and schedule one prompt, serialized health refresh."""
        if self._stopping:
            return
        self.async_set_update_error(err)
        if self._recovery_task is None or self._recovery_task.done():
            LOGGER.debug("Scheduling Enody recovery after command failure")
            # Bypass the request-refresh cooldown. SDK work still uses the same
            # client lock as polls/commands; only the read-only health is retried.
            self._recovery_task = self.hass.async_create_task(
                self.async_refresh(), "Enody command failure recovery"
            )

    async def async_shutdown(self) -> None:
        """Stop scheduled recovery before the client is disconnected."""
        self._stopping = True
        await super().async_shutdown()
        if self._recovery_task is not None:
            self._recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._recovery_task
            self._recovery_task = None

    async def _async_update_data(self) -> EnodyDeviceInfo:
        """Fetch current device metadata."""
        if self._stopping:
            raise UpdateFailed("Enody is shutting down")
        try:
            return await self.client.async_get_info()
        except EnodyDependencyError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="dependency_error",
            ) from err
        except EnodyError as err:
            raise UpdateFailed("Unable to communicate with the Enody device") from err
