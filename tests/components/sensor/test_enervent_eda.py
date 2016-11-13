"""
tests.components.sensor.test_enervet_eda
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests enervent_eda sensor.
"""
import unittest

import homeassistant.core as ha
import homeassistant.components.sensor as sensor
import homeassistant.components.sensor.enervent_eda as eda
from homeassistant.const import (
     ATTR_ENTITY_PICTURE)
from unittest.mock import MagicMock
from unittest.mock import call
from unittest.mock import ANY

from unittest.mock import patch
#import homeassistant.components.modbus as modbus


class TestSensorEnerventSensor(unittest.TestCase):
    """ Test the Enervent sensor. """

    def setUp(self):  # pylint: disable=invalid-name
        self.hass = ha.HomeAssistant()

    def tearDown(self):  # pylint: disable=invalid-name
        """ Stop down stuff we started. """
        self.hass.stop()

    def test_setup(self):
        self.assertTrue(sensor.setup(self.hass, {
            'sensor': {
                'platform': 'enervent_eda',
                'slave': '1',
                'name': 'testname',
            }
        }))
        state = self.hass.states.get('sensor.testname')

        self.assertEqual('None', state.state)
        self.assertEqual(None,
                         state.attributes.get('unit_of_measurement'))

    def test_setup_platform(self):
        mock = MagicMock()
        eda.setup_platform(self.hass, {
                'platform': 'enervent_eda',
                'slave': '1',
                'name': 'testname',
            }, mock)
        assert mock.called
        kall = mock.call_args
        args, kwargs = kall
        eda_sensor = args[0]

class TestSensorEDASensor(unittest.TestCase):
    """ Test EDASensor class """

    def setUp(self):  # pylint: disable=invalid-name
        self.hass = ha.HomeAssistant()
        mock = MagicMock()
        eda.setup_platform(self.hass, {
                'platform': 'enervent_eda',
                'slave': '6',
                'name': 'testname',
                'sync_time': True
            }, mock)
        assert mock.called
        args = mock.call_args[0]
        self.eda_sensor = args[0][0]
        assert self.eda_sensor

    def tearDown(self):  # pylint: disable=invalid-name
        """ Stop down stuff we started. """
        self.hass.stop()

    def test_state_attributes(self):
        self.assertEqual('/static/images/eda/eda_heat_recovery.png' ,self.eda_sensor.state_attributes[ATTR_ENTITY_PICTURE])

    def test_update(self):
        # trigger mocks
        eda.modbus.NETWORK = MagicMock()
        result_registers = MagicMock()
        # registers 44, 45
        result_registers.registers = [2048, 4]
        eda.modbus.HUB.read_holding_registers = MagicMock(return_value=result_registers)
        result_coils = MagicMock();
        # coils 41, 42
        result_coils.bits = [False, True, False, False, False, False, False, False]
        eda.modbus.HUB.read_coils = MagicMock(return_value=result_coils)
        with patch.object(self.eda_sensor, '_check_time') as mock_check_time:
            # execute unit test
            self.eda_sensor.update()

        # assert expectations
        expected = [call(unit=6, address=44, count=2)]
        self.assertEqual(eda.modbus.HUB.read_holding_registers.mock_calls, expected)

        expected = [call(unit=6, address=41, count=2)]
        self.assertEqual(eda.modbus.HUB.read_coils.mock_calls, expected)

        assert mock_check_time.called

        self.assertEqual('Liesituuletin + !B', self.eda_sensor.state)

    def test__check_time(self):
        # trigger mocks
        eda.modbus.NETWORK = MagicMock()
        result_registers = MagicMock()
        # registers 37 - 42
        result_registers.registers = [59, 59, 23, 31, 12, 14]
        eda.modbus.HUB.read_holding_registers = MagicMock(return_value=result_registers)

        # execute unit test
        self.eda_sensor._check_time()

        # assert expectations
        #expected = [call(unit=6, address=37, count=6)]
        #self.assertEqual(eda.modbus.HUB.read_holding_registers.mock_calls, expected)

        #expected = [call(unit=6, address=582, values=ANY)]
        #self.assertEqual(eda.modbus.HUB.write_registers.mock_calls, expected)

