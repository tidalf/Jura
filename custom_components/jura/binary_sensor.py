from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging

from . import DOMAIN
from .core.entity import JuraEntity

_LOGGER = logging.getLogger(__name__)

# Define alert sensors with their expected alert names and configurations
ALERT_SENSORS = [
    # Maintenance alerts (these are normal maintenance operations)
    {
        "name_pattern": "insert tray",
        "type": "insert_tray",
        "display_name": "Insert Tray",
        "icon": "mdi:tray",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "name_pattern": "fill water",
        "type": "fill_water",
        "display_name": "Fill Water",
        "icon": "mdi:water",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "name_pattern": "empty grounds",
        "type": "empty_grounds",
        "display_name": "Empty Grounds",
        "icon": "mdi:delete",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "name_pattern": "empty tray",
        "type": "empty_tray",
        "display_name": "Empty Tray",
        "icon": "mdi:tray-alert",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Service alerts (require cleaning or filter replacement)
    {
        "name_pattern": "cleaning alert",
        "type": "cleaning_alert",
        "display_name": "Cleaning Needed",
        "icon": "mdi:washing-machine",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "name_pattern": "filter alert",
        "type": "filter_alert",
        "display_name": "Filter Change Needed",
        "icon": "mdi:air-filter",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "name_pattern": "cappu rinse alert",
        "type": "cappu_rinse_alert",
        "display_name": "Milk System Rinse Needed",
        "icon": "mdi:cup-water",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "name_pattern": "milk system alert",
        "type": "milk_system_alert",
        "display_name": "Milk System Cleaning Needed",
        "icon": "mdi:cup-water",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
]


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, add_entities: AddEntitiesCallback
):
    device = hass.data[DOMAIN][config_entry.entry_id]

    # Create connection sensor
    entities = [JuraSensor(device, "connection")]

    # Create alert binary sensors
    for alert in ALERT_SENSORS:
        entities.append(JuraAlertBinarySensor(
            device,
            alert["type"],
            alert["name_pattern"],
            alert["display_name"],
            alert["icon"],
            alert.get("device_class", BinarySensorDeviceClass.PROBLEM),
            alert.get("entity_category")
        ))
        _LOGGER.debug(
            f"Added alert sensor: {alert['display_name']} for pattern '{alert['name_pattern']}'")

    add_entities(entities)


class JuraSensor(JuraEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def internal_update(self):
        self._attr_is_on = self.device.connected
        self._attr_extra_state_attributes = self.device.conn_info

        if self.hass:
            self._async_write_ha_state()


class JuraAlertBinarySensor(JuraEntity, BinarySensorEntity):
    """Binary sensor for Jura alerts."""

    def __init__(self, device, alert_type, name_pattern, display_name, icon, device_class=BinarySensorDeviceClass.PROBLEM, entity_category=None):
        """Initialize the sensor."""
        self._name_pattern = name_pattern.lower(
        )  # Store name pattern before calling super().__init__
        super().__init__(device, f"alert_{alert_type}")
        self._attr_name = f"{device.name} {display_name}"
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category

        # Register for updates on alerts
        device.register_alert_update(self.internal_update)

    def internal_update(self):
        """Update the sensor state."""
        # Check if any active alert's name contains our pattern
        self._attr_is_on = any(
            self._name_pattern in alert_name.lower()
            for _, alert_name in self.device.alerts.items()
        )

        if self.hass:
            self._async_write_ha_state()
