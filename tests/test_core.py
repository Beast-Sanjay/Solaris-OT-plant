import importlib.util
from pathlib import Path
import struct
import unittest

SRC = Path(__file__).resolve().parents[1]/'services'


class ModbusTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('plc',SRC/'plc.py')
        self.plc=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.plc)

    def test_read_holding_registers(self):
        pdu = self.plc.modbus_response(struct.pack('!BHH', 3, 0, 6))
        self.assertEqual(pdu[:2], bytes([3,12]))
        self.assertEqual(len(pdu), 14)

    def test_reject_out_of_bounds(self):
        self.assertEqual(self.plc.modbus_response(struct.pack('!BHH', 3, 5, 4)), b'\x83\x02')

    def test_write_only_setpoint_register(self):
        self.assertEqual(self.plc.modbus_response(struct.pack('!BHH', 6, 2, 22)), b'\x86\x02')
        good=struct.pack('!BHH',6,4,60)
        self.assertEqual(self.plc.modbus_response(good), good)
        self.assertEqual(self.plc.registers()[4],60)

    def test_reject_unknown_function(self):
        self.assertEqual(self.plc.modbus_response(b'\x10'), b'\x90\x01')


if __name__=='__main__': unittest.main()
