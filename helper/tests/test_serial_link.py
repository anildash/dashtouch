from types import SimpleNamespace
from unittest import mock

import pytest

from dashtouch_helper import serial_link


def ports(*devices):
    return [SimpleNamespace(device=d) for d in devices]


def comport(device, vid=None, pid=None, serial_number=None, location=None,
            manufacturer=None, product=None, description="n/a"):
    return SimpleNamespace(device=device, vid=vid, pid=pid,
                           serial_number=serial_number, location=location,
                           manufacturer=manufacturer, product=product,
                           description=description)


def test_usb_ports_skips_ports_that_are_not_usb():
    with mock.patch("serial.tools.list_ports.comports", return_value=[
            comport("/dev/cu.Bluetooth-Incoming-Port"),
            comport("/dev/cu.usbmodem1402", 0x239A, 0x8119, "68:ee", None,
                    "Adafruit", "QT Py ESP32-S3")]):
        ports = serial_link.usb_ports()
    assert [p.device for p in ports] == ["/dev/cu.usbmodem1402"]
    assert ports[0].label == "Adafruit QT Py ESP32-S3"


def test_usb_ports_offers_only_ports_the_helper_would_find():
    # A CH340-style adapter is USB too, but the helper only looks at
    # usbmodem ports, so flashing one would leave a board it never finds.
    with mock.patch("serial.tools.list_ports.comports", return_value=[
            comport("/dev/cu.wchusbserial10", 0x1A86, 0x7523, None, "20-1"),
            comport("/dev/cu.usbmodem101", 0x239A, 0x8119, "68:ee")]):
        ports = serial_link.usb_ports()
    assert [p.device for p in ports] == ["/dev/cu.usbmodem101"]


def test_usb_port_identity_survives_a_new_device_node():
    # A reset can bring the same board back as a different /dev node; with
    # a serial number, it's still recognizably the same board.
    def listing(dev):
        return [comport(dev, 0x239A, 0x8119, "68:ee:8f", "20-1")]
    with mock.patch("serial.tools.list_ports.comports", return_value=listing("/dev/cu.usbmodem1")):
        a = serial_link.usb_ports()[0]
    with mock.patch("serial.tools.list_ports.comports", return_value=listing("/dev/cu.usbmodem2")):
        b = serial_link.usb_ports()[0]
    assert a.identity == b.identity


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
