"""Classes for controlling QuickSet pan tilt mounts.

This module contains classes for controlling QuickSet pan tilt mounts. It
implements the basic move commands and some other common commands. All the
move commands are blocking---that is, they don't return until the move is done.

Typical usage:
    import from quickset_pan_tilt import controller, protocol

    # Create the pan tilt controller object. The first argument is the protocol
    # object that your particular pan tilt mount uses (check the pan tilt mount
    # datasheet to determine this).
    pan_tilt = controller.ControllerSerial(protocol.PTCR20(), 'COM4')

    # Move the pan tilt mount as desired.
    pan_tilt.move_absolute(-50, 13.5)
"""

import serial
import time
import warnings
from abc import ABC, abstractmethod

from quickset_pan_tilt import protocol

# Always print warnings every time they occur instead of only the first time.
warnings.simplefilter("always")


# TODO: we could probably just name this Controller instead of QuicksetController since quickset is the module name
class QuicksetController(ABC):
    """Abstract base class for QuickSet pan tilt mount controllers.

    Attributes:
        pan: The current pan coordinate, in degrees.
        tilt: The current tilt coordinate, in degrees.
        pan_destination: The last pan destination coordinate, in degrees.
        tilt_destination: The last tilt destination coordinate, in degrees.

    Args:
        protocol:
            A QuicksetProtocol instance. This instance must be the correct
            protocol type for the pan tilt mount being used.
    """

    @abstractmethod
    def __init__(self, protocol: protocol.QuicksetProtocol):
        self._protocol = protocol

        # These internal attributes should be accessed with the "public"
        # read-only properties defined by the associated @property decorators.
        self._pan = None
        self._tilt = None
        self._pan_destination = None
        self._tilt_destination = None

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
    def communication_timeout(self) -> int:
        """Get the pan tilt mount's communication timeout.

        Returns:
            communication_timeout: The timeout value, in seconds.
        """
        CMD_NAME = "get_communication_timeout"

        packet = self._protocol.assemble_packet(CMD_NAME)
        self._send(packet)

        rx = self._receive()
        communication_timeout = self._protocol.parse_packet(CMD_NAME, rx)

        return communication_timeout

    @communication_timeout.setter
    def communication_timeout(self, timeout: int):
        """Set the pan tilt mount's communication timeout.

        Args:
            timeout: The desired timeout value, in seconds.
        """
        CMD_NAME = "set_communication_timeout"

        # Send the desired timeout to the pan-tilt controller
        packet = self._protocol.assemble_packet(CMD_NAME, timeout)
        self._send(packet)

        # Read back the response from the pan-tilt controller to make sure the
        # timeout was actually set.
        rx = self._receive()
        actual_timeout = self._protocol.parse_packet(CMD_NAME, rx)

        if timeout != actual_timeout:
            warnings.warn(
                "Communication timeout was not set successfully."
                f" Desired value: {timeout}, actual value: {actual_timeout}"
            )

    def home(self) -> bool:
        """Move to (0,0).

        Returns:
            was_move_successful:
                Boolean indicating whether or not the move was successful
        """
        was_move_successful = self._execute_move_command("home")
        return was_move_successful

    def move_delta(self, pan, tilt) -> bool:
        """Move by specific pan and tilt increments.

        Args:
            pan:
                The pan increment, in degrees.
            tilt:
                The tilt increment, in degrees.

        Returns:
            was_move_successful:
                Boolean indicating whether or not the move was successful
        """
        was_move_successful = self._execute_move_command("move_delta", pan, tilt)
        return was_move_successful

    def move_absolute(self, pan, tilt) -> bool:
        """Move to absolute pan and tilt coordinates.

        Args:
            pan:
                The destination pan coordinate, in degrees.
            tilt:
                The destination tilt coordinate, in degrees.

        Returns:
            was_move_successful:
                Boolean indicating whether or not the move was successful
        """
        was_move_successful = self._execute_move_command("move_absolute", pan, tilt)
        return was_move_successful

    def _execute_move_command(self, cmd: str, *args) -> bool:
        """Send a move command and wait until it is done.

        This method is intended to be called from the public move commands,
        such as home() or move_delta(). It is the method that handles all
        the logistics of actually performing the move.

        This method is blocking and will not return until the move is completed.

        Args:
            cmd:
                The move command name
            *args:
                Additional positional arguments for the associated move command.

        Returns:
            was_move_successful:
                Boolean indicating whether or not the move was successful
        """

        was_move_successful = False

        packet = self._protocol.assemble_packet(cmd, *args)
        self._send(packet)

        # Check that the controller received and acknowledged the command
        rx = self._receive()
        while rx is None:
            # Ack was not received... retry the command until it was Ack'd
            self._send(packet)
            rx = self._receive()

        # Parse the return status from the move command; this is primarily to
        # get the destination coordinates from the pan-tilt mount.
        status = self._protocol.parse_packet(cmd, rx)
        self._set_pan_tilt_coordinate_properties(status)

        # Keep checking the status until the move is done
        done = False
        while not done:
            status = self.get_status()

            hard_faults, soft_faults = self.check_for_faults(status)

            # The EXEC bit will be cleared when there is a hard fault, so we
            # need to check for faults and break out of the loop before checking
            # the EXEC bit to see if the move is done. Indeed, when a fault
            # occurs, all motion will stop, so the move is done, but that does
            # not indicate a *successful* move.
            if hard_faults or soft_faults:
                break

            if not status.gen_status.EXEC:
                # EXEC bit is 0, so the move is done
                done = True
                was_move_successful = True

        return was_move_successful

    def fault_reset(self) -> bool:
        """Clear any hard faults.

        Returns:
            were_faults_cleared:
                A boolean indicating whether the hard faults were cleared.

        Warnings:
            UserWarning:
                Raised if the hard faults were not successfully cleared.
        """
        CMD_NAME = "fault_reset"

        packet = self._protocol.assemble_packet(CMD_NAME)
        self._send(packet)

        rx = self._receive()
        status = self._protocol.parse_packet(CMD_NAME, rx)

        # See if all the hard faults were cleared
        hard_faults, soft_faults = self.check_for_faults(status)

        if hard_faults:
            warnings.warn("Hard faults were not successfully cleared.")
            were_faults_cleared = False
        else:
            were_faults_cleared = True

        return were_faults_cleared

    def get_status(self):
        """Get the pan-tilt mount's status.

        Returns:
            status:
                A StatusResponse tuple for the particular protocol being used.
                See the StatusResponse documentation for the pan-tilt protocol
                you are using for details.
        """
        CMD_NAME = "get_status"

        packet = self._protocol.assemble_packet(CMD_NAME)
        self._send(packet)

        rx = self._receive()
        status = self._protocol.parse_packet(CMD_NAME, rx)

        self._set_pan_tilt_coordinate_properties(status)

        return status

    def _set_pan_tilt_coordinate_properties(self, status):
        """Set the instance's pan and tilt coordinate properties.

        The object's pan and tilt properties are just copies that can be accessed
        without querying the pan-tilt mount.

        Args:
            status:
                A StatusResponse tuple for the particular protocol being used.
        """

        # NOTE: The DES (destination) bit should always be set in the response
        # following a "move to" command; the destination bit will likely never
        # be set in the response from a "get status" command.
        if status.gen_status.DES:
            self._pan_destination = status.pan
            self._tilt_destination = status.tilt
        else:
            self._pan = status.pan
            self._tilt = status.tilt

    def check_for_faults(self, status) -> tuple:
        """Check for hard and soft faults.

        Given a StatusResponse, as returned by get_status(), this method
        checks if the pan tilt mount has any active faults.

        Args:
            status:
                A StatusResponse tuple that was returned from get_status().

        Returns:
            hard_faults:
                A tuple of the active hard faults.
            soft_faults:
                A tuple of the active soft faults.

        Warnings:
            UserWarning:
                Raised for each fault that is active.
        """
        hard_faults = self._protocol.check_for_hard_faults(
            status.pan_status, status.tilt_status
        )

        soft_faults = self._protocol.check_for_soft_faults(
            status.pan_status, status.tilt_status
        )

        # Let the user know of any active faults by issuing a warning. This is
        # for interactive usage. If a consumer wants to automatically do
        # do something when a fault is active, they need to do something
        # with the return values from this function.
        for fault in hard_faults:
            warnings.warn(f"{fault} fault is active.")

        for fault in soft_faults:
            warnings.warn(f"{fault} fault is active.")

        return hard_faults, soft_faults

    def _wait_for_initialization(self):
        """Request the controller's status until initialization is complete.

        The controller takes a while to respond on power up; this is probably
        just due to boot and initialization time of the controller's
        microcontroller.
        """

        has_controller_responded = False

        # We need to explicitly flush the stdout buffer because the default
        # behavior is to flush after each newline character.
        print("Waiting for controller to initialize", end="", flush=True)

        while not has_controller_responded:
            try:
                status = self.get_status()
            except TypeError:
                # We expect a TypeError to be raised from protocol.parse_packet
                # when the controller isn't responding; this is because the
                # serial port read will timeout when the controller isn't
                # responding, which results in the received packet being None.
                print(".", end="", flush=True)
                # pass
            else:
                # Print a newline once initialization is done because the
                # dots after "waiting for controller to initialize" don't have
                # a newline at the end
                print()
                has_controller_responded = True

    @abstractmethod
    def _send(self, packet: bytearray):
        """Send a command to the pan tilt mount.

        Args:
            packet:
                The command bytes to send.
        """
        pass

    @abstractmethod
    def _receive(self) -> bytearray:
        """Receive a response from the pan tilt mount.

        Returns:
            packet:
                The received packet from the pan tilt mount.
        """
        pass


class ControllerSerial(QuicksetController):
    """Class for QuickSet controllers controlled via serial ports.

    This class will work with pan tilt mounts that are configured to use RS-232
    or RS-422 for serial communication.

    Args:
        protocol:
            A QuicksetProtocol instance. This instance must be the correct
            protocol type for the pan tilt mount being used.
        port:
            The serial port to use, e.g., /dev/ttyUSB0 or COM4
        timeout:
            The serial port's read timeout, in seconds. Defaults to 1.
        baud:
            The serial port's baud rate. Defaults to 9600.
    """

    def __init__(
        self,
        protocol: protocol.QuicksetProtocol,
        port: str,
        timeout: int = 1,
        baud: int = 9600,
    ):
        super().__init__(protocol)

        self._serial = serial.Serial(port=port, timeout=timeout, baudrate=baud)

        # The controller takes a while to respond after being powered on.
        self._wait_for_initialization()

    def _send(self, packet: bytearray):
        self._serial.write(packet)
        # TODO: should we make sure we actually sent something?

    def _receive(self) -> bytearray:
        rx = bytearray()
        recv_byte = None
        ACK_WAIT_TIME = 10

        # Wait for ACK. If we never receive ACK, we should return and resend the command.
        # TODO: do we need to bother with looping a set number of times until we receive ACK?
        for i in range(ACK_WAIT_TIME):
            recv_byte = self._serial.read(1)
            if len(recv_byte) == 0:
                # The pan-tilt didn't return anything after the read timeout,
                # so most likely nothing is in the buffer / being sent.
                return None

            elif recv_byte == self._protocol.CONTROL_CHARS.ACK.to_bytes():
                rx.extend(recv_byte)
                break

            elif i == (ACK_WAIT_TIME - 1):
                # We didn't receive an ACK character yet, so we're assuming
                # that the transmission is corrupt and should start over.
                return None

        # Read bytes until we hit ETX
        while recv_byte != self._protocol.CONTROL_CHARS.ETX.to_bytes():
            recv_byte = self._serial.read(1)
            rx.extend(recv_byte)

        return rx
