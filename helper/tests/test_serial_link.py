from types import SimpleNamespace
from unittest import mock

import pytest

from dashtouch_helper import serial_link


def ports(*devices):
    return [SimpleNamespace(device=d) for d in devices]


def test_find_port_none():
    with mock.patch("serial.tools.list_ports.comports", return_value=ports()):
        assert serial_link.find_port() is None


def test_find_port_single():
    with mock.patch("serial.tools.list_ports.comports",
                    return_value=ports("/dev/cu.usbmodem101", "/dev/cu.Bluetooth")):
        assert serial_link.find_port() == "/dev/cu.usbmodem101"


def test_find_port_ambiguous_raises():
    with mock.patch("serial.tools.list_ports.comports",
                    return_value=ports("/dev/cu.usbmodem101", "/dev/cu.usbmodem102")):
        with pytest.raises(serial_link.AmbiguousPortError):
            serial_link.find_port()


class FakeSerial:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else b""


def test_read_line_decodes_and_strips():
    assert serial_link.read_line(FakeSerial([b"PONG\r\n"])) == "PONG"


def test_read_line_timeout_is_none():
    assert serial_link.read_line(FakeSerial([])) is None
