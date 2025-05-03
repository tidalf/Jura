"""Sensor platform for Jura integration."""

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .core import DOMAIN
from .core.entity import JuraEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Jura sensor based on a config entry."""
    device = hass.data[DOMAIN][entry.entry_id]

    # Create the total coffees sensor
    entities: list = [JuraTotalCoffeeSensor(device)]

    # Create sensors for each product
    for product in device.products:
        product_name = product["@Name"]
        if product.get("@Active") != "false":
            entities.append(JuraProductCountSensor(device, product_name))

    # Create alert sensors
    entities.append(JuraAlertSensor(device))
    
    # Create maintenance percentage sensors
    entities.append(JuraMaintenancePercentSensor(device))
    
    # Create individual maintenance percentage sensors - these will be populated later
    # after the first data fetch
    device.individual_maintenance_sensors = []

    async_add_entities(entities)

    # Set up automatic refresh
    update_interval = hass.data[DOMAIN].get("update_interval", 60)

    async def refresh_statistics(*_):
        """Refresh statistics regularly."""
        try:
            await device.read_statistics()
            await device.read_alerts()
            await device.read_maintenance_percents()
            
            # Check if we need to create individual maintenance sensors
            if device.maintenance.get("cleaning_percents") and not device.individual_maintenance_sensors:
                _LOGGER.info("Creating individual maintenance sensors")
                individual_sensors = []
                for maint_type, value in device.maintenance.get("cleaning_percents", {}).items():
                    # Skip creating sensors for maintenance types that don't have a proper name
                    if not maint_type or maint_type.lower() == "unknown" or maint_type.lower() == "inconnu":
                        _LOGGER.debug(f"Skipping unnamed maintenance type with value {value}")
                        continue
                    sensor = JuraIndividualMaintenancePercentSensor(device, maint_type)
                    individual_sensors.append(sensor)
                
                if individual_sensors:
                    device.individual_maintenance_sensors = individual_sensors
                    async_add_entities(individual_sensors)
                    _LOGGER.info(f"Added {len(individual_sensors)} individual maintenance sensors")
                
        except Exception as ex:
            # we log as info as this is expected if the device is off
            _LOGGER.info(f"Error refreshing data: {ex}")

    # Schedule regular updates
    entry.async_on_unload(
        async_track_time_interval(
            hass, refresh_statistics, timedelta(seconds=update_interval)
        )
    )

    # Do an initial refresh
    hass.async_create_task(refresh_statistics())


class JuraStatisticsSensor(JuraEntity, SensorEntity):
    """Base class for Jura statistics sensors."""

    def __init__(self, device, attr: str):
        """Initialize the sensor."""
        super().__init__(device, attr)

        # Register for updates on statistics
        device.register_statistics_update(self.internal_update)

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self._get_value()

    def _get_value(self) -> Any:
        """Get the value for this sensor from statistics."""
        raise NotImplementedError("Subclasses must implement this method")

    def internal_update(self):
        """Override parent method to ensure statistics are refreshed."""
        _LOGGER.debug(f"Updating sensor {self._attr_name}")
        if self.hass is not None:
            self.async_write_ha_state()


class JuraTotalCoffeeSensor(JuraStatisticsSensor):
    """Sensor for total coffee count."""

    _attr_icon = "mdi:coffee"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "products"

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device, "total_product")
        self._attr_name = f"{device.name} Total Products"

    def _get_value(self) -> int:
        """Get the total coffee count."""
        value = self.device.statistics.get("total_products", 0)
        _LOGGER.debug(f"Total coffee value: {value}")
        return value


class JuraProductCountSensor(JuraStatisticsSensor):
    """Sensor for individual product count."""

    _attr_icon = "mdi:coffee-outline"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "products"

    def __init__(self, device, product_name: str):
        """Initialize the sensor."""
        self.product_name = product_name
        attr_name = f"product_{product_name.lower().replace(' ', '_')}"
        super().__init__(device, attr_name)
        self._attr_name = f"{device.name} {product_name} Count"

    def _get_value(self) -> int:
        """Get the count for this specific product."""
        value = self.device.statistics.get("product_counts", {}).get(
            self.product_name, None
        )
        _LOGGER.debug(f"Product {self.product_name} count: {value}")
        return value


class JuraAlertSensor(JuraEntity, SensorEntity):
    """Sensor for machine alerts."""

    _attr_icon = "mdi:alert"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "alert"]

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device, "alerts")
        self._attr_name = f"{device.name} Alerts"
        self._attr_extra_state_attributes = {"active_alerts": []}

        # Register for updates on alerts
        device.register_alert_update(self.internal_update)

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return self._get_value()

    def _get_value(self) -> str:
        """Get the alert status."""
        active_alerts = []
        # Filter out specific alert bits that we don't want to show
        filtered_bits = {12, 13, 36, 37, 148, 149, 150, 151}
        for bit, name in self.device.active_alerts.items():
            if bit not in filtered_bits:
                active_alerts.append({"bit": bit, "name": name})
        self._attr_extra_state_attributes["active_alerts"] = active_alerts
        return "alert" if active_alerts else "ok"

    def internal_update(self):
        """Override parent method to ensure alerts are refreshed."""
        _LOGGER.debug(f"Updating alert sensor {self._attr_name}")
        if self.hass is not None:
            self.async_write_ha_state()


class JuraMaintenancePercentSensor(JuraEntity, SensorEntity):
    """Sensor for machine maintenance percentage."""

    _attr_icon = "mdi:wrench"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device):
        """Initialize the sensor."""
        super().__init__(device, "maintenance_percents")
        self._attr_name = f"{device.name} Maintenance Status"
        
        # Register for updates on maintenance percentages
        device.register_maintenance_update(self.internal_update)
        
    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self._get_value()

    def _get_value(self) -> dict:
        """Get all maintenance percentages."""
        self._attr_extra_state_attributes = self.device.maintenance.get("cleaning_percents", {})
        # Return the average of all percentages or None if no data
        percentages = self._attr_extra_state_attributes.values()
        if percentages:
            avg = sum(percentages) / len(percentages)
            return round(avg, 1)
        return None
        
    def internal_update(self):
        """Override parent method to ensure maintenance data is refreshed."""
        _LOGGER.debug(f"Updating maintenance sensor {self._attr_name}")
        if self.hass is not None:
            self.async_write_ha_state()


class JuraIndividualMaintenancePercentSensor(JuraEntity, SensorEntity):
    """Sensor for individual maintenance percentage."""

    _attr_icon = "mdi:wrench"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device, maint_type: str):
        """Initialize the sensor."""
        # Create a safe ID from the maintenance type
        safe_id = maint_type.lower().replace(" ", "_").replace("-", "_")
        super().__init__(device, f"maintenance_percents_{safe_id}")
        self._attr_name = f"{device.name} {maint_type}"
        self.maint_type = maint_type
        
        # Register for updates on maintenance percentages
        device.register_maintenance_update(self.internal_update)
        
    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self._get_value()

    def _get_value(self) -> int:
        """Get the maintenance percentage for the specified type."""
        # Return the percentage for the specified type or None if no data
        return self.device.maintenance.get("cleaning_percents", {}).get(self.maint_type, None)
        
    def internal_update(self):
        """Override parent method to ensure maintenance data is refreshed."""
        _LOGGER.debug(f"Updating maintenance sensor {self._attr_name}")
        if self.hass is not None:
            self.async_write_ha_state()
