"""
Support for Geo Solo II energy monitor.

Configuration:
To use the Solo II sensors you will need to add something like the following
to your config/configuration.yaml

sensor:
    platform: solo2
    mount_point: '/media/SoloII'
    monitored_variables:
        - name: Power
            integration_count: 1
            type: consumption
            unit: Kw
        - name: Outdoor temp
            integration_count: 1
            type: temp2
            unit: C
        - name: 'Consumption 24h'
            integration_count: 96
            type: consumption
            unit: Kwh
        - name: Outdoor temp
            integration_count: 96
            type: temp2
            unit: C
Variables:
    intergation_count: 1 == 15 min, 2 == 30min, 96 == 1 day and so on

NOTE: Works only on Linux currently
You need following line to /etc/fstab:
 '/dev/disk/by-label/SoloII /media/SoloII
   vfat ro,noexec,noauto,user,async,nofail'
"""

import logging
import subprocess
import mmap
import collections
import struct
import time
from math import floor
from threading import Lock

from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    TEMP_CELCIUS, TEMP_FAHRENHEIT)
#    STATE_ON, STATE_OFF)

_LOGGER = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)


SENSOR_TYPES = [
    'consumption',
    'cost',
    'temp1',
    'temp2',
]
LAST_READ_TIME = 0
RECORDS = dict()
DEVICE = None
LOCK = Lock()


def setup_platform(hass, config, add_devices, discovery_info=None):
    """ Read config and create Solo II device"""
    sensors = []
    global DEVICE
    DEVICE = Solo2Device(config.get("mount_point", '/media/SoloII'))
    for variable in config['monitored_variables']:
        if 'integration_count' not in variable:
            variable['integration_count'] = 1
        if variable['type'] not in SENSOR_TYPES:
            _LOGGER.error('Sensor type: "%s" does not exist', variable)
        else:
            RECORDS[variable['integration_count']] = None
            _LOGGER.info('Adding sensor "%s"', variable['name'])
            sensors.append(Solo2Sensor(variable['name'],
                                       variable['integration_count'],
                                       variable['type'],
                                       variable['unit']))

    add_devices(sensors)


def _update_records():
    """Update module variable RECORDS that was asked by config"""
    global LAST_READ_TIME
    with LOCK:
        now = time.time()
        if abs(now - LAST_READ_TIME) < 840:
            return

        local_now = time.localtime(now)
        tmp_min = local_now.tm_min % 15
        if tmp_min > 10 or tmp_min < 5:
            return

        _LOGGER.info('Updating records')
        LAST_READ_TIME = now
        with DEVICE:
            for count in RECORDS.keys():
                RECORDS[count] = DEVICE.get_last_records(now, count)


class Solo2Sensor(Entity):
    # pylint: disable=too-many-arguments
    """ Represents a Solo II Sensor"""

    def __init__(self, name, count, val_type, unit):
        self._name = name
        if unit == "C":
            self._unit = TEMP_CELCIUS
        elif unit == "F":
            self._unit = TEMP_FAHRENHEIT
        else:
            self._unit = unit

        self._count = count
        self._val_type = val_type

    def __str__(self):
        return "%s: %s %s" % (self.name, self.state, self.unit_of_measurement)

    @property
    def should_poll(self):
        """ We should poll, because slaves are not allowed to
            initiate communication on Modbus networks"""
        return True

    @property
    def unique_id(self):
        """ Returns a unique id. """
        return "SOLO2-SENSOR-{}-{}-{}".format(DEVICE.mount_point,
                                              self._val_type, self._count)

    @property
    def state(self):
        """ Returns the state of the sensor. """
        if RECORDS[self._count] is None:
            _LOGGER.warning('RECORDS["%d"] is None', self._count)
            return None

        result = None
        if self._val_type == 'consumption':
            if self._unit == 'Kwh':
                consumption = RECORDS[self._count].consumption
                if consumption < 20:
                    return round(consumption, 2)
                elif consumption < 1000:
                    result = round(consumption, 1)
                else:
                    result = round(consumption)
            elif self._unit == 'Kw':
                power = (RECORDS[self._count].consumption/self._count)*4
                result = round(power, 2)

        elif self._val_type == 'temp2':
            result = round(RECORDS[self._count].temp2, 1)

        elif self._val_type == 'temp1':
            result = round(RECORDS[self._count].temp1, 1)

        elif self._val_type == 'cost':
            result = round(RECORDS[self._count].cost, 2)

        return result

    @property
    def name(self):
        """ Get the name of the sensor. """
        return self._name

    @property
    def unit_of_measurement(self):
        """ Unit of measurement of this entity, if any. """
        return self._unit

    def update(self):
        _update_records()


Record = collections.namedtuple('Record',
                                ['time', 'consumption', 'cost',
                                 'generation', 'gain', 'temp1', 'temp2'])


class Solo2Device:
    """Solo II device driver."""
    # Calculate delta between local time and device time in 15 minute units
    _time_delta = time.mktime((2016, 1, 1, 0, 0, 0, 0, 0, -1))/900+16854881

    def __init__(self, mount_point):
        self._file = None
        self.mmap = None
        self.mount_point = mount_point
        self._ref_time = 0

    def __enter__(self):
        """Context enter function will mount the mount point of device and
           mmap SoloII.dat"""
        sts = subprocess.call(['/bin/mount', self.mount_point])
        if sts == 32:
            subprocess.check_call(['/bin/umount', self.mount_point])
            subprocess.check_call(['/bin/mount', self.mount_point])
        elif sts != 0:
            ex = OSError(sts, 'Mount failue')
            ex.filename = self.mount_point
            raise ex

        self._file = open(self.mount_point + '/SoloII.dat', 'rb', 0)
        self.mmap = mmap.mmap(self._file.fileno(), 0,
                              access=mmap.ACCESS_READ, offset=0x1a000)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context exit function will un-mmap SoloII.dat and
           un-mount the mount point of device"""
        self.mmap.close()
        self._file.close()
        subprocess.call(['/bin/umount', self.mount_point])

    def get_record_index(self, index):
        """Get record by ID"""
        index = index % 35832
        btmp = bytes(self.mmap[0x100+0x20*index:0x11a+0x20*index])
        tmp = struct.unpack('iIHHHHIHBBBB', btmp)
        if tmp[0] == -1:
            return None

        record_time = (Solo2Device._time_delta + tmp[0])*900
        generation = tmp[4]/1000
        consumption = tmp[1]/1000
        return Record(record_time,
                      consumption, consumption*(tmp[3]/1000),
                      generation, generation*(tmp[5]/1000),
                      (tmp[10]-60)/2, (tmp[9]-60)/2)

    def get_record_time(self, at_time):
        """Get record by 'at_time'.
           For example get latest record:
           device.get_record_time(time.time())"""
        index = self._get_index_of(at_time)
        return self.get_record_index(index)

    def _get_index_of(self, at_time):
        """Return index value by 'time'"""
        if abs(at_time - self._ref_time) > 31536000:
            self._ref_time = self.get_record_index(0).time

        return floor((at_time - self._ref_time)/900)

    def get_last_records(self, at_time, number_of_records):
        """Get 'number_of_records' number of records before 'time'"""
        if number_of_records < 1:
            return None

        last_index = self._get_index_of(at_time)
        count = 0
        sum_consump = 0
        sum_generation = 0
        generation_gain = 0
        sum_temp1 = 0
        sum_temp2 = 0
        cost = 0
        for i in range(last_index, last_index-number_of_records, -1):
            record = self.get_record_index(i)
            if record:
                cost += record.cost
                sum_consump += record.consumption
                sum_generation += record.generation
                generation_gain += record.gain
                sum_temp1 += record.temp1
                sum_temp2 += record.temp2
                count += 1

        if count == 0:
            return None

        # estimate missing records
        if count < number_of_records:
            missing = number_of_records-count
            ave = sum_consump/count
            sum_consump += ave*missing
            ave = cost/count
            cost += ave*missing
            ave = sum_generation/count
            sum_generation += ave*missing
            ave = generation_gain/count
            generation_gain += ave*missing

        return Record(at_time,
                      sum_consump, cost,
                      sum_generation, generation_gain,
                      sum_temp1/count, sum_temp2/count)
