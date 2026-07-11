"""Sensor platform for generac."""
from datetime import datetime
from typing import Any
from typing import Type

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.components.sensor.const import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GeneracDataUpdateCoordinator
from .entity import GeneracEntity
from .models import Item


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup sensor platform."""
    coordinator: GeneracDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    if isinstance(data, dict):
        async_add_entities(
            sensor(coordinator, entry, generator_id, item)
            for generator_id, item in data.items()
            for sensor in sensors(item)
        )


def sensors(item: Item) -> list[Type[GeneracEntity]]:
    lst = [
        StatusSensor,
        RunTimeSensor,
        ProtectionTimeSensor,
        ActivationDateSensor,
        LastSeenSensor,
        ConnectionTimeSensor,
        BatteryVoltageSensor,
        DeviceTypeSensor,
        DealerEmailSensor,
        DealerNameSensor,
        DealerPhoneSensor,
        AddressSensor,
        StatusTextSensor,
        StatusLabelSensor,
        SerialNumberSensor,
        ModelNumberSensor,
        DeviceSsidSensor,
        PanelIDSensor,
    ]
    if get_apparatus_property_value(item, "signalStrength") is not None:
        lst.append(SignalStrengthSensor)
    if get_apparatus_property_value(item, "batteryLevel") is not None:
        lst.append(DeviceBatteryLevelSensor)
    if get_detail_property_value(item, 95) is not None:
        lst.append(ExerciseMinutesSensor)
    if (
        item.apparatusDetail.weather is not None
        and item.apparatusDetail.weather.temperature is not None
        and item.apparatusDetail.weather.temperature.value is not None
    ):
        lst.append(OutdoorTemperatureSensor)
    return lst


def get_detail_property_value(item: Item, property_type: int) -> Any:
    if item.apparatusDetail.properties is None:
        return None
    return next(
        (prop.value for prop in item.apparatusDetail.properties if prop.type == property_type),
        None,
    )


def get_first_detail_property_value(item: Item, property_types: list[int]) -> Any:
    for property_type in property_types:
        value = get_detail_property_value(item, property_type)
        if value is not None:
            return value
    return None


def get_apparatus_property_value(item: Item, field: str) -> Any:
    if item.apparatus.properties is None:
        return None
    for prop in item.apparatus.properties:
        value = prop.value
        if isinstance(value, list) or value is None:
            continue
        attr_value = getattr(value, field, None)
        if attr_value is not None:
            return attr_value
    return None


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value.endswith("%"):
            value = value[:-1].strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parseDatetime(rawStr: str) -> datetime:
    formats = ["%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"]
    ves: list[ValueError] = []
    for fmt in formats:
        try:
            return datetime.strptime(rawStr, fmt)
        except ValueError as ve:
            ves.append(ve)
    raise ValueError(f"No known datetime format for raw string {rawStr}")


class StatusSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_options = [
        "Ready",
        "Running",
        "Exercising",
        "Warning",
        "Stopped",
        "Communication Issue",
        "Unknown",
    ]
    _attr_icon = "mdi:power"
    _attr_device_class = SensorDeviceClass.ENUM

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        options = self.options
        if options is None:
            return None
        if self.aparatus_detail.apparatusStatus is None:
            return options[-1]
        index = self.aparatus_detail.apparatusStatus - 1
        if index < 0 or index > len(options) - 1:
            index = len(options) - 1
        return options[index]


class DeviceTypeSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_options = [
        "Wifi",
        "Ethernet",
        "MobileData",
        "Unknown",
    ]
    _attr_device_class = SensorDeviceClass.ENUM

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        options = self.options
        if options is None:
            return None
        if self.aparatus_detail.deviceType is None:
            return options[-1]
        if self.aparatus_detail.deviceType == "wifi":
            return options[0]
        if self.aparatus_detail.deviceType == "eth":
            return options[1]
        if self.aparatus_detail.deviceType == "lte":
            return options[2]
        if self.aparatus_detail.deviceType == "cdma":
            return options[2]
        return options[-1]


class RunTimeSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "h"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return as_float(get_first_detail_property_value(self.item, [71, 70]))


class ProtectionTimeSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "h"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return as_float(get_first_detail_property_value(self.item, [32, 31]))


class ActivationDateSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.aparatus_detail.activationDate is None:
            return None
        return parseDatetime(self.aparatus_detail.activationDate)


class LastSeenSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.aparatus_detail.lastSeen is None:
            return None
        return parseDatetime(self.aparatus_detail.lastSeen)


class ConnectionTimeSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.aparatus_detail.connectionTimestamp is None:
            return None
        return parseDatetime(self.aparatus_detail.connectionTimestamp)


class BatteryVoltageSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = "V"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return as_float(get_first_detail_property_value(self.item, [70, 69]))


class ExerciseMinutesSensor(GeneracEntity, SensorEntity):
    """Exercise duration reported by Mobile Link."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "min"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return as_float(get_detail_property_value(self.item, 95))


class OutdoorTemperatureSensor(GeneracEntity, SensorEntity):
    """generac Sensor class."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_unit_of_measurement(self):
        if (
            self.aparatus_detail.weather is None
            or self.aparatus_detail.weather.temperature is None
            or self.aparatus_detail.weather.temperature.unit is None
        ):
            return UnitOfTemperature.CELSIUS
        if "f" in self.aparatus_detail.weather.temperature.unit.lower():
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if (
            self.aparatus_detail.weather is None
            or self.aparatus_detail.weather.temperature is None
            or self.aparatus_detail.weather.temperature.value is None
        ):
            return None
        return self.aparatus_detail.weather.temperature.value


class SignalStrengthSensor(GeneracEntity, SensorEntity):
    """Cellular signal strength reported by the Mobile Link device."""

    _attr_icon = "mdi:signal-cellular-2"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return as_float(get_apparatus_property_value(self.item, "signalStrength"))


class DeviceBatteryLevelSensor(GeneracEntity, SensorEntity):
    """Battery level reported by the Mobile Link device."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return as_float(get_apparatus_property_value(self.item, "batteryLevel"))


class SerialNumberSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus.serialNumber


class ModelNumberSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus.modelNumber


class DeviceSsidSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus_detail.deviceSsid


class StatusLabelSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus_detail.statusLabel


class StatusTextSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus_detail.statusText


class AddressSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus.localizedAddress


class DealerNameSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus.preferredDealerName


class DealerEmailSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus.preferredDealerEmail


class DealerPhoneSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus.preferredDealerPhone


class PanelIDSensor(GeneracEntity, SensorEntity):
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.aparatus.panelId
