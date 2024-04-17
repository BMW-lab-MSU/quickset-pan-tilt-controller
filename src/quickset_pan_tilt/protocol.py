import struct
import numpy as np
from abc import ABC, abstractmethod
from collections import namedtuple

ControlCharacters = namedtuple('ControlCharacters',
                               ('STX', 'ETX', 'ACK', 'NACK', 'ESC'))


class QuicksetProtocol(ABC):

    CONTROL_CHARS = ControlCharacters(STX=0x02, ETX=0x03, ACK=0x06, NACK=0x15,
                                      ESC=0x1b)

    @staticmethod
    def int_to_bytes(integer):
        """Convert an integer into little-endian bytes.

        The Quickset pan-tilt mount protocols format integers as 16-bit
        signed two's-complement little endian integers.

        Args:
            integer: The integer to convert.

        Returns:
            bytes: The converted little-endian bytes array.
        """
        int_bytes = integer.to_bytes(length=2, byteorder='little', signed=True)

        # Return a bytearray because it is mutable. We need to be able to
        # modify the byte array later on, particularly if we need to insert
        # and escape sequence.
        return bytearray(int_bytes)

    @staticmethod
    def compute_lrc(byte_array):
        """Calculate the xor-based longitudinal redundancy check.

        Args:
            byte_array: 
                Array of bytes to compute the LRC on. This should start with
                the command byte and end with the last data byte.

        Returns:
            lrc: The checksum.
        """
        lrc = 0

        # bytes objects don't support the xor operator, so we need to convert
        # to integers to perform the xor.
        ints = [int(byte) for byte in byte_array]

        for byte in ints:
            lrc ^= byte

        return bytearray((lrc).to_bytes(length=1, signed=False))

    @staticmethod
    def escape_control_chars(packet):
        """Escape bytes that match a control character.

        When a byte matches a control character, it must be escaped by
        1. inserting an escape character before the byte
        2. modifying the original byte so it no longer matches the
           control character.

        Args:
            packet:
                The packet of bytes to check for control characters in. 

        Returns:
            new_packet:
                The new packet with any control characters removed. If no
                control characters were present, this is the same as the
                original packet.
        """
        new_packet = bytearray()

        for byte in packet:
            if byte in QuicksetProtocol.CONTROL_CHARS:
                new_packet.extend(
                    QuicksetProtocol.insert_escape_sequence(byte))
            else:
                new_packet.append(byte)

        return new_packet

    @staticmethod
    def insert_escape_sequence(byte):
        """Insert an escape sequence.

        Args:
            byte:
                The byte to escape. 

        Returns:
            escape_sequence: 
                An array of bytes containing the escape byte followed by the
                modified original byte.
        """
        # Set bit 7 of the conflicting byte.
        byte |= 0b0100_0000

        # Insert the escape character prior to the conflicting byte.
        return bytearray((QuicksetProtocol.CONTROL_CHARS.ESC, byte))

    def __init__(self):
        # NOTE: the PTHR90 and PTCR20 protocols use most of the same command
        # numbers. Most of the PTHR90 command numbers are the same in the PTCR20;
        # the main difference is that the PTCR20 defines additional commands.
        # Thus we put the common commands into the base class and can add any
        # additional unique commands to the subclasses.
        self._COMMANDS = {
            'get_status': {'func': self._get_status, 'number': 0x31},
            'move_absolute': {'func': self._move_to_entered, 'number': 0x33},
            'move_delta': {'func': self._move_to_delta, 'number': 0x34},
            # The home/move to (0,0) command doesn't need any data, so we don't
            # need a method to prepare the data, hence why we use an anonymous
            # function that doesn't nothing.
            'home': {'func': lambda: None, 'number': 0x35},
            'fault_reset': {'func': self._fault_reset, 'number': 0x31},
        }

        self.COMMAND_NAMES = set(self._COMMANDS.keys())

    @abstractmethod
    def assemble_packet(self, cmd_name, *data):
        """Assemble the communication packet for a command.

        Some commands require input data, such as the pan and tilt coordinates.
        These inputs need to be passed as additional positional arguments.

        Args:
            cmd_name:
                The name of the desired command. This command name must match a
                command name defined in COMMAND_NAMES. 
            *data:
                Additional positional arguments for the desired command.

        Returns:
            packet:
                The communication packet as a bytes object.
        """
        pass

    def _prepare_cmd_and_lrc_packets(self, cmd_name, *data):
        """Create the command, data, and lrc bytes for the communication packet.

        This method dispatches preparing the data for the command to a
        command-specific data-preparation method. The required data depends on
        the specific command, thus any number of additional positional
        arguments can be passed in after the `cmd_name`. 

        All other packet preparation is common to all commands, and thus
        doesn't need to be dispatched.

        Args:
            cmd_name:
                The name of the desired command. This command name must match a
                command name defined in COMMAND_NAMES. 
            *data:
                Additional positional arguments for the desired command.

        Returns:
            packet: 
                The command, data bytes, and LRC for the desired command.
        """

        if cmd_name not in self.COMMAND_NAMES:
            raise NotImplementedError(
                f'Command "{cmd_name}" is not implemented.')

        cmd_bytes = self._COMMANDS[cmd_name]['number'].to_bytes()

        # Call the command-specific function to prepare the data bytes.
        data_bytes = self._COMMANDS[cmd_name]['func'](*data)

        # Some commands don't require any data bytes; thus data_bytes will be
        # empty and should not be included in the command packet.
        if data_bytes is not None:
            packet = cmd_bytes + data_bytes
        else:
            packet = cmd_bytes

        lrc = self.compute_lrc(packet)

        packet.extend(lrc)

        return packet

    @abstractmethod
    def _get_status(self):
        pass

    def _fault_reset(self):
        """Clear any hard faults.

        Possible hard faults are timeout, direction error, and current overload.
        """
        # Set the reset bit high
        reset_cmd = (0b00000001).to_bytes()

        # Set all jog speeds to 0
        pan_jog_cmd = (0).to_bytes()
        tilt_jog_cmd = (0).to_bytes()
        zoom_jog_cmd = (0).to_bytes()
        focus_jog_cmd = (0).to_bytes()

        data_bytes = (reset_cmd + pan_jog_cmd + tilt_jog_cmd + zoom_jog_cmd
                      + focus_jog_cmd)

        return data_bytes

    def _move_to_entered(self, pan=None, tilt=None):
        """Move to entered coordinate.

        Args:
            pan: 
                Pan coordinate in degrees, between -360.0 and 360.0.
                Coordinate precision is 0.1 degrees. Passing 999.9 or None will
                keep the pan position stationary.

            tilt:
                Tilt coordinate in degrees, between -180.0 and 180.0.
                Coordinate precision is 0.1 degrees. Passing 999.9 or None will
                keep the tilt coordinate stationary.

        Returns:
            data_bytes: 
                Bytes representing the pan and tilt coordinates. The first two
                bytes are the little-endian representation of the pan
                coordinate, and the last two bytes are little-endian
                representation of the tilt coordinate.
        """
        if pan is None:
            pan = 999.9
        if tilt is None:
            tilt = 999.9

        # Pan and tilt coordinates need to be sent as integers, so we have to
        # multiply by 10 to get the coordinates in the right range.
        pan = int(pan * 10)
        tilt = int(tilt * 10)

        pan_bytes = self.int_to_bytes(pan)
        tilt_bytes = self.int_to_bytes(tilt)

        # Concatenate the bytes together
        data_bytes = pan_bytes + tilt_bytes

        return data_bytes

    def _move_to_delta(self, pan=None, tilt=None):
        """Move to delta coordinates.

        Move specified pan and tilt angles away from the current coordinate.

        Args:
            pan: 
                Pan coordinate in degrees, between -360.0 and 360.0.
                Coordinate precision is 0.1 degrees. Passing 0 or None will
                keep the pan position stationary.

            tilt:
                Tilt coordinate in degrees, between -180.0 and 180.0.
                Coordinate precision is 0.1 degrees. Passing 0 or None will
                keep the tilt coordinate stationary.

        Returns:
            data_bytes: 
                Bytes representing the pan and tilt coordinates. The first two
                bytes are the little-endian representation of the pan
                coordinate, and the last two bytes are little-endian
                representation of the tilt coordinate.
        """

        if pan is None:
            pan = 0
        if tilt is None:
            tilt = 0

        # Pan and tilt coordinates need to be sent as integers, so we have to
        # multiply by 10 to get the coordinates in the right range.
        pan = int(pan * 10)
        tilt = int(tilt * 10)

        pan_bytes = self.int_to_bytes(pan)
        tilt_bytes = self.int_to_bytes(tilt)

        # Concatenate the bytes together
        data_bytes = pan_bytes + tilt_bytes

        return data_bytes


class PTCR20(QuicksetProtocol):

    def __init__(self, identity=0):
        super().__init__()
        self.identity = identity

    def assemble_packet(self, cmd_name, *data):
        packet = self._prepare_cmd_and_lrc_packets(cmd_name, *data)

        packet.insert(0, self.identity)

        packet = self.escape_control_chars(packet)

        packet.insert(0, self.CONTROL_CHARS.STX)
        packet.append(self.CONTROL_CHARS.ETX)

        return packet

    def _get_status(self):
        pass


class PTHR90(QuicksetProtocol):

    def __init__(self):
        super().__init__()

    def assemble_packet(self, cmd_name, *data):
        packet = self._prepare_cmd_and_lrc_packets(cmd_name, *data)

        packet = self.escape_control_chars(packet)

        packet.insert(0, self.CONTROL_CHARS.STX)
        packet.append(self.CONTROL_CHARS.ETX)

        return packet

    def _get_status(self):
        pass
