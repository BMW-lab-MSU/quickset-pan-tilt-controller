import serial
import time
import warnings
from abc import ABC, abstractmethod

from quickset_pan_tilt import protocol

# TODO: we could probably just name this Controller instead of QuicksetController since quickset is the module name
class QuicksetController(ABC):
    @abstractmethod
    def __init__(self):
        # These internal attributes should be accessed with the "public"
        # read-only properties defined by the associated @property decorators.
        # TODO: maybe we should implement setters for pan and tilt that will
        # call the move_absolute method under the hood.
        self._pan = None
        self._tilt = None
        self._pan_destination = None
        self._tilt_destination = None

        self.protocol = None

    @property
    def pan(self):
        return self._pan

    @property
    def tilt(self):
        return self._tilt

    @property
    def pan_destination(self):
        return self._pan_destination

    @property
    def tilt_destination(self):
        return self._tilt_destination

    @property
    def communication_timeout(self):
        CMD_NAME = 'get_communication_timeout'

        packet = self.protocol.assemble_packet(CMD_NAME)
        self._send(packet)

        rx = self._receive()
        communication_timeout = self.protocol.parse_packet(CMD_NAME, rx)

        return communication_timeout

    @communication_timeout.setter
    def communication_timeout(self, timeout):
        CMD_NAME = 'set_communication_timeout'

        # Send the desired timeout to the pan-tilt controller
        packet = self.protocol.assemble_packet(CMD_NAME, timeout)
        self._send(packet)

        # Read back the response from the pan-tilt controller to make sure the
        # timeout was actually set.
        rx = self._receive()
        actual_timeout = self.protocol.parse_packet(CMD_NAME, rx)

        if timeout != actual_timeout:
            warnings.warn("Communication timeout was not set successfully."
                f" Desired value: {timeout}, actual value: {actual_timeout}")

    def home(self):
        packet = self.protocol.assemble_packet('home')
        self._send(packet)

        rx = self._receive()
        # self.protocol.parse_packet(rx)

    def move_delta(self, pan, tilt):
        packet = self.protocol.assemble_packet('move_delta', pan, tilt)
        self._send(packet)

        rx = self._receive()
        # self.protocol.parse_packet(rx)

    def move_absolute(self, pan, tilt):
        packet = self.protocol.assemble_packet('move_absolute', pan, tilt)
        self._send(packet)

        rx = self._receive()
        # self.protocol.parse_packet(rx)

    def fault_reset(self):
        """Clear any hard faults."""
        CMD_NAME = 'fault_reset'

        packet = self.protocol.assemble_packet(CMD_NAME)
        self._send(packet)

        rx = self._receive()
        status = self.protocol.parse_packet(CMD_NAME, rx)

        # See if all the hard faults were cleared
        hard_faults_exist = self.protocol.status_has_hard_faults(status.pan_status,
                                                            status.tilt_status)
        if hard_faults_exist:
            warnings.warn("Hard fault was not successfully cleared.")


    def get_status(self):
        """Get pan-tilt mount status.

        Returns:
            status:
                A StatusResponse tuple for the particular protocol being used.
                See the StatusResponse documentation for the pan-tilt protocol
                you are using for details.
        """
        CMD_NAME = 'get_status'
        packet = self.protocol.assemble_packet(CMD_NAME)
        self._send(packet)

        rx = self._receive()
        status = self.protocol.parse_packet(CMD_NAME, rx)

        if status.gen_status.DES:
            self._pan_destination = status.pan
            self._tilt_destination = status.tilt
        else:
            self._pan = status.pan
            self._tilt = status.tilt

        return status

    @abstractmethod
    def _send(self, packet):
        pass

    @abstractmethod
    def _receive(self) -> bytearray:
        pass

class ControllerSerial(QuicksetController):
    @abstractmethod
    def __init__(self, port, timeout=1, baud=9600):
        super().__init__()
        self.serial = serial.Serial(port=port, timeout=timeout, baudrate=baud)

    def _send(self, packet: bytearray):
        self.serial.write(packet)
        # TODO: should we make sure we actually sent something?

    def _receive(self) -> bytearray:
        rx = bytearray()
        recv_byte = None
        ACK_WAIT_TIME = 10

        # Wait for ACK. If we never receive ACK, we should return and resend the command.
        # TODO: do we need to bother with looping a set number of times until we receive ACK?
        for i in range(ACK_WAIT_TIME):
            recv_byte = self.serial.read(1)
            if len(recv_byte) == 0:
                # The pan-tilt didn't return anything after the read timeout,
                # so most likely nothing is in the buffer / being sent.
                return None

            elif recv_byte == self.protocol.CONTROL_CHARS.ACK.to_bytes():
                rx.extend(recv_byte)
                break;

            elif i == (ACK_WAIT_TIME - 1):
                # We didn't receive an ACK character yet, so we're assuming
                # that the transmission is corrupt and should start over.
                return None

        # Read bytes until we hit ETX
        while recv_byte != self.protocol.CONTROL_CHARS.ETX.to_bytes():
            recv_byte = self.serial.read(1)
            rx.extend(recv_byte)

        return rx

class QPT20Serial(ControllerSerial):
    def __init__(self, port, timeout=1, baud=9600):
        super().__init__(port, timeout, baud)
        self.protocol = protocol.PTCR20()
