import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .core import DOMAIN
from .core.device import Device, EmptyModel, UnsupportedModel, get_machine

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor", "button", "number", "select", "switch", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    devices = hass.data.setdefault(DOMAIN, {})

    @callback
    def update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        _LOGGER.debug(f"{change} {service_info.advertisement}")

        if device := devices.get(entry.entry_id):
            device.update_ble(service_info.advertisement)
            return

        try:
            manufacturer_data = service_info.advertisement.manufacturer_data[171]
            # First byte is the encryption key
            encryption_key = manufacturer_data[0]
            machine = get_machine(manufacturer_data)
        except EmptyModel:
            return
        except UnsupportedModel as e:
            _LOGGER.error("Unsupported model: %s", *e.args)
            return

        alerts = machine.get("alerts", [])

        devices[entry.entry_id] = device = Device(
            entry.title, machine["model"], machine["products"], service_info.device, encryption_key, alerts
        )
        device.update_ble(service_info.advertisement)

        hass.create_task(
            hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        )

    # https://developers.home-assistant.io/docs/core/bluetooth/api/
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            update_ble,
            {"address": entry.data["mac"],
                "manufacturer_id": 171, "connectable": True},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if entry.entry_id in hass.data[DOMAIN]:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True
