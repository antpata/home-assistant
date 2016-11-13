"""
Support for Enervent EDA heat recovery unit state.

Configuration:
To use the EDA sensors you will need to add something like the following to
your config/configuration.yaml

sensor:
    platform: enervent_eda
    slave: 1
    name: EDA
    sync_time: True


VARIABLES:

    - "slave" = slave number (ignored and can be omitted if not serial Modbus)

"""

import logging
import time

import homeassistant.components.modbus as modbus
from homeassistant.helpers.entity import Entity
from homeassistant.const import (
     ATTR_ENTITY_PICTURE)
#    TEMP_CELCIUS, TEMP_FAHRENHEIT,
#    STATE_ON, STATE_OFF)

from homeassistant.helpers import config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
DEPENDENCIES = ['modbus']

_STATE_NAMES = ['Kotona', 'Max jäähdytys', 'Max lämmitys', 'Hätäseis', 'Seis',
                'Poissa', 'Pitkään poissa', 'Lämpötila tehostus',
                'CO2 tehostus', 'Rh tehostus', 'Tehostus', 'Ylipaine',
                'Liesituuletin', 'Imuri', 'SLP jäähdytys', 'Kesäyöjäähdytys',
                'LTO sulatus']


def from_alarm_array(array):
    """ return time value from enervent alarm time register array """
    return time.mktime((
        array[0] + 2000,
        array[1],
        array[2],
        array[3],
        array[4],
        0, 0, 0, -1))


def from_rtc_array(array):
    """ return time value from enervent rtc time register array [37 - 42] """
    if len(array) == 5:
        return from_alarm_array(array[::-1])
    else:
        return time.mktime((
            array[5] + 2000,
            array[4],
            array[3],
            array[2],
            array[1],
            array[0],
            0, 0, -1))


def _to_rtc_array(time_val):
    """ return time as enervent register array """
    localt = time.localtime(time_val)
    return (localt.tm_min, localt.tm_hour, localt.tm_mday,
            localt.tm_mon, localt.tm_year-2000)


def _to_alarm_array(time_val):
    """ return time as enervent alarm array """
    return _to_rtc_array(time_val)[::-1]


def setup_platform(hass, config, add_devices, discovery_info=None):
    """ Read config and create EDA device """
    sensors = []
    slave = config.get("slave", None)
#    if modbus.TYPE == "serial" and not slave:
#        _LOGGER.error("No slave number provided for serial Modbus")
#        return False

    sensors.append(EDASensor(config.get("name"), slave, config.get("sync_time", False)))
    add_devices(sensors)

_STATE_NORMAL = 0
_STATE_MAX_COOL = 1
_STATE_MAX_HEAT = 2
_STATE_EMERGENCY_STOP = 4 
_STATE_STOP = 8
_STATE_AWAY = 16
_STATE_LONG_AWAY = 32
_STATE_MAX_HEAT = 64
_STATE_CO2_BOOST = 128
_STATE_H2O_BOOST = 256
_STATE_BOOST = 512
_STATE_OVER_PRESSURE = 1024
_STATE_COOKER_HOOD = 2048
_STATE_VACUUM = 4096
_STATE_HP_COOL = 8192
_STATE_SN_COOL = 16384
_STATE_DE_ICE = 32768

_TEMP_NONE = 0
_TEMP_COOL = 1
_TEMP_HEAT_RECOVERY = 2
_TEMP_HEATING = 4
_TEMP_DELAY = 5
_TEMP_SNCOOLING = 6
_TEMP_START = 7
_TEMP_STOP = 8
_TEMP_RECOVERY_CLEANING = 9
_TEMP_EXT_DE_ICE = 10

_ALARM_A = 1
_ALARM_B = 2
class EDASensor(Entity):
    # pylint: disable=too-many-arguments
    """ Represents a EDA Sensor """


    def __init__(self, name, slave, sync_time):
        self._name = name
        self.slave = int(slave) if slave else 1
        self._value = None
        self._time_checked = time.time()
        self._sync_time = sync_time
        self._state = _STATE_NORMAL
        self._temp_control = 0
        self._alarm = 0

    def __str__(self):
        return "%s: %s" % (self.name, self.state)

    @property
    def should_poll(self):
        """ We should poll, because slaves are not allowed to
            initiate communication on Modbus networks"""
        return True

    @property
    def unique_id(self):
        """ Returns a unique id. """
        return "EDA-SENSOR-{}".format(self.slave)

    @property
    def state(self):
        """ Returns the state of the sensor. """
        return self._value

    @property
    def name(self):
        """ Get the name of the sensor. """
        return self._name

    @property
    def unit_of_measurement(self):
        """ Unit of measurement of this entity, if any. """
        return None

    @property
    def state_attributes(self):
        #attr = super().state_attributes
        state_image = '/static/images/eda/eda_heat_recovery.png'
        if (self._temp_control == _TEMP_HEAT_RECOVERY):
            state_image = '/static/images/eda/eda_heat_recovery.png'
        elif (self._temp_control == _TEMP_HEATING):
            state_image = '/static/images/eda/eda_heating.png'
        elif (self._temp_control == _TEMP_SNCOOLING):
            state_image = '/static/images/eda/eda_sommernacht.png'

        if (self._state & _STATE_BOOST):
            state_image = '/static/images/eda/eda_boosting.png'

        if (self._state & _STATE_OVER_PRESSURE):
            state_image = '/static/images/eda/eda_overpressure.png'

        if (self._state & _STATE_COOKER_HOOD):
            state_image = '/static/images/eda/eda_cooker_hood.png'

        if (self._state & _STATE_VACUUM):
            state_image = '/static/images/eda/eda_vacuum.png'

        if (self._alarm != 0):
            state_image = '/static/images/eda/eda_alarms.png'

        if (self._state & _STATE_STOP):
            state_image = '/static/images/eda/eda_stop.png'

        if (self._state & _STATE_EMERGENCY_STOP):
            state_image = '/static/images/eda/eda_emergency_stop.png'

        state_attr = {ATTR_ENTITY_PICTURE: state_image}
        return state_attr

    def update(self):
        result = modbus.HUB.read_holding_registers(unit=self.slave,
                                                       address=44,
                                                       count=2)
        self._state = result.registers[0]
        self._temp_control = result.registers[1]

        result = modbus.HUB.read_coils(unit=self.slave, address=41,
                                           count=2)
        alarm_a = result.bits[0]
        alarm_b = result.bits[1]

        val = 'Kotona'
        test = 1
        for i in range(1, 17):
            if test & self._state != 0:
                val = _STATE_NAMES[i]
            test = test << 1

        if self._state == 0x1800:
            val = 'Liesituuletin2'

        if self._temp_control == 1 or self._temp_control == 6:
            val += ' -'
        elif self._temp_control == 4:
            val += ' +'
        elif self._temp_control == 7:
            val = 'Käynnistys'
#        elif self._temp_control == 8:
#            val = 'Seis'

        tmp_alarm = 0
        if alarm_a or alarm_b:
            val += ' !'
            if alarm_a:
                tmp_alarm |= _ALARM_A
                val += 'A'
            if alarm_b:
                tmp_alarm |= _ALARM_B
                val += 'B'

        self._alarm =tmp_alarm
        self._value = val
        if (self._sync_time):
            self._check_time()

    def _check_time(self):
        """ Check enervent time and update time
            if there is more than 90s difference """
        if abs(self._time_checked - time.time()) < 600:
            return

        result = modbus.HUB.read_holding_registers(unit=self.slave, address=37,
                                                       count=6)
        rtc_t = from_rtc_array(result.registers)
        if abs(time.time() - rtc_t) > 90:
            rtime = _to_rtc_array(time.time())
            _LOGGER.info('Time diff:%ds writing RTC registers:%s',
                         (time.time() - rtc_t), str(rtime))
            modbus.HUB.write_registers(unit=self.slave, address=582, values=rtime)
        self._time_checked = time.time()
