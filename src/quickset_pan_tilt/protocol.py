import bitfield
import struct
import warnings
import numpy as np
from abc import ABC, abstractmethod
from collections import namedtuple
from ctypes import c_bool, c_uint8

ControlCharacters = namedtuple('ControlCharacters',
                               ('STX', 'ETX', 'ACK', 'NACK', 'ESC'))

# TODO: we could probably just name this Protocol instead of QuicksetProtocol since quickset is the module name
class QuicksetProtocol(ABC):

    CONTROL_CHARS = ControlCharacters(STX=0x02, ETX=0x03, ACK=0x06, NACK=0x15,
                                      ESC=0x1b)

    # The pan/tilt angle resolution in 0.1 degrees, but the pan/tilt angles are
    # specified as integers, so the actual angles are multiplied by 10.
    _ANGLE_MULTIPLIER = 10

    @staticmethod
    def int_to_bytes(integer: int) -> bytearray:
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
    def bytes_to_int(two_bytes: bytes) -> int:
        """Convert two little-endian bytes into an integer.

        Args:
            two_bytes: The bytes to convert. This must have a length of 2.

        Returns:
            integer: The converted integer.
        """
        # Unpack the little-endian bytes as a signed two's complement integer.
        # '<' is for little-endian, and 'h' is for 'short'
        # (i.e., a signed two-byte integer).
        unpacked = struct.unpack('<h', two_bytes)

        # struct.unpack always returns a tuple, but we want to have an int,
        # so we index into the tuple.
        integer = unpacked[0]

        return integer

    @staticmethod
    def compute_lrc(byte_array: bytes) -> bytearray:
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

    # TODO: I think we need better names for the escape sequence functions.
    #       The names are currently very similar and it is unclear which one
    #       will have a for loop and which won't. It's possible that we should
    #       maybe just absorb `insert_escape_sequence` into the for loop of
    #       `escape_control_chars`
    @staticmethod
    def escape_control_chars(packet: bytearray) -> bytearray:
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
    def insert_escape_sequence(byte: int) -> bytearray:
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
        # NOTE: Bit indexing starts at 0 in the QuickSet documentation.
        byte |= 0b1000_0000

        # Insert the escape character prior to the conflicting byte.
        return bytearray((QuicksetProtocol.CONTROL_CHARS.ESC, byte))

    @staticmethod
    def remove_escape_sequences(packet: bytearray) -> bytearray:
        """Remove escape sequences from the received packet.

        Args:
            packet: The received packet to check for escape sequences in.

        Returns:
            new_packet:
                The received packet without escape sequences. If no escape
                sequences were present, this is the same as the original packet.
        """
        new_packet = bytearray()
        found_esc = False

        for byte in packet:
            if byte == QuicksetProtocol.CONTROL_CHARS.ESC:
                # Throw out the ESC character and set a flag so we know to
                # unescape the next byte.
                found_esc = True
                continue
            else:
                if found_esc:
                    # Clear bit 7 of the escaped byte
                    byte &= 0b0111_1111

                    # Clear the ESC flag so we don't think the next byte was
                    # preceded by an ESC character.
                    found_esc = False

                new_packet.append(byte)

        return new_packet

    def __init__(self):

        # NOTE: the PTHR90 and PTCR20 protocols use most of the same command
        # numbers. Most of the PTHR90 command numbers are the same in the PTCR20;
        # the main difference is that the PTCR20 defines additional commands.
        # Thus we put the common commands into the base class and can add any
        # additional unique commands to the subclasses.
        self._COMMANDS = {
            'get_status': {
                'assemble': self._assemble_get_status,
                'parse': self._parse_get_status,
                'number': 0x31,
            },
            'move_absolute': {
                'assemble': self._assemble_move_to_entered,
                'parse': self._parse_move_to_entered,
                'number': 0x33,
            },
            'move_delta': {
                'assemble': self._assemble_move_to_delta,
                'parse': self._parse_move_to_delta,
                'number': 0x34,
            },
            # The home/move to (0,0) command doesn't need any data, so we don't
            # need a method to prepare the data, hence why we use an anonymous
            # function that doesn't nothing.
            'home': {
                'assemble': lambda: None,
                'parse': lambda: None,
                'number': 0x35,
            },
            'fault_reset': {
                'assemble': self._assemble_fault_reset,
                # The fault reset command is just a particular case of the
                # "get status" command, so we can use the "get status" parser.
                'parse': self._parse_get_status,
                'number': 0x31,
            },
            'get_communication_timeout': {
                'assemble': self._assemble_get_communication_timeout,
                'parse': self._parse_communication_timeout,
                'number': 0x96,
            },
            'set_communication_timeout': {
                'assemble': self._assemble_set_communication_timeout,
                'parse': self._parse_communication_timeout,
                'number': 0x96,
            },
        }

        self.COMMAND_NAMES = set(self._COMMANDS.keys())

    def status_has_hard_faults(self, pan_status, tilt_status) -> bool:
        """Check whether the pan and tilt status have hard faults.
        
        Args:
            pan_status: PanStatus BitField
            tilt_status: TiltStatus BitField

        Returns:
            hard_fault_exists: Whether or not a hard fault is present.
        """
        pan_hard_faults_exist = (pan_status.TO | pan_status.DE | pan_status.OL)
        tilt_hard_faults_exist = (tilt_status.TO | tilt_status.DE | tilt_status.OL)

        if pan_hard_faults_exist or tilt_hard_faults_exist:
            return True
        else:
            return False

    def assemble_packet(self, cmd_name: str, *data) -> bytearray:
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
        packet = self._assemble_cmd_data_lrc(cmd_name, *data)

        # Add the identity byte if the protocol requires it, otherwise leave
        # the packet as is.
        self._add_identity_byte(packet)

        packet = self.escape_control_chars(packet)

        packet.insert(0, self.CONTROL_CHARS.STX)
        packet.append(self.CONTROL_CHARS.ETX)

        return packet

    def _assemble_cmd_data_lrc(self, cmd_name: str, *data) -> bytearray:
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

        # cmd_bytes needs to be a bytearray so we can support mutable sequence
        # operations like extend and insert.
        cmd_bytes = bytearray(self._COMMANDS[cmd_name]['number'].to_bytes())

        # Call the command-specific function to prepare the data bytes.
        data_bytes = self._COMMANDS[cmd_name]['assemble'](*data)

        # Some commands don't require any data bytes; thus data_bytes will be
        # empty and should not be included in the command packet.
        if data_bytes is not None:
            packet = cmd_bytes + data_bytes
        else:
            packet = cmd_bytes

        lrc = self.compute_lrc(packet)

        packet.extend(lrc)

        return packet

    def parse_packet(self, cmd_name: str, packet: bytearray) -> tuple | None:
        """Parse a received communication packet.

        Args:
            cmd_name:
                The name of the command that was received and needs to be
                parsed. This command name must match a command name defined
                in COMMAND_NAMES.
            packet:
                The packet to be parsed.

        Returns:
            data:
                The returned data varies based upon the command, so the caller
                must know how to parse the returned data.

        Raises:
            RuntimeException:
                A RuntimeException is raised if the packet is invalid, the packet
                is corrupted (i.e., the LRC doesn't match), or if the received
                packet does not match the command defined by `cmd_name`.
        """
        # TODO: what do we do if we receive a NACK?

        # Create a local copy of the packet because we don't want to modify the
        # original packet; the calling function would likely be surprised that
        # the packet they passed to us has been modified.
        local_packet = packet[:]

        # In general, we already know that ACK will be the first byte
        # because the controller won't receive a packet unless there is an ACK
        # at the beginning and an ETC at the end. Therefore, the packet we
        # receive should generally be valid; however, we will check anyway
        # just in case.
        ack_received = local_packet[0] == self.CONTROL_CHARS.ACK
        etx_received = local_packet[-1] == self.CONTROL_CHARS.ETX
        if ack_received and etx_received:
            packet_valid = True
        else:
            packet_valid = False
            raise RuntimeError("Packet is invalid")

        # Remove the ack and etx bytes so we don't have to worry about them
        # down the line when computing the LRC or parsing the data bytes.
        del local_packet[0]
        del local_packet[-1]

        # Escape sequences must be removed before parsing anything.
        local_packet = self.remove_escape_sequences(local_packet)

        # If the protocol uses an identity byte, remove it; otherwise, the
        # packet will be left unaltered.
        # TODO: there might be a better name for this function. I'd have to
        # check if there are other "preamble" bytes in some of the other
        # Quickset protocols; if there are, this function could maybe handle
        # all the preamble stuff that is specific to a particular protocol.
        self._remove_identity_byte(local_packet)

        # Computing the LRC of the cmd, data, and received LRC will return 0
        # if the nothing is corrupted; this is because the LRC of the cmd and
        # data will be the same as the LRC byte, and xor'ing the cmd/data LRC
        # with an identical LRC byte will return 0. We want the returned LRC to
        # be an integer instead of a bytearray this time so we can compare to
        # an int, so we index into the byte array to return the underlying int.
        lrc = self.compute_lrc(local_packet)[0]
        if lrc != 0:
            raise RuntimeError("LRC does not match. Packet was corrupted."
                               f" Received packet = {packet.hex()}")

        # We don't need the lrc packet anymore
        del local_packet[-1]

        # Make sure the command number we received is actually the command we
        # are expecting. If this is not the case, that most likely means the
        # caller passed the wrong command name to us.
        cmd_number = local_packet[0]
        expected_cmd_number = self._COMMANDS[cmd_name]['number']
        if expected_cmd_number != cmd_number:
            raise RuntimeError(f"Received command number {cmd_number} does"
                               " not mach expected command number {expected_cmd_number}.")

        # We don't need the command packet anymore
        del local_packet[0]

        # Packet is good so far, so now we can actually handle parsing the data.
        data = self._COMMANDS[cmd_name]['parse'](local_packet)

        # The data tuple can vary depending on the command, so the caller must
        # know how to parse the data appropriately. We simply return the tuple.
        return data

    def _add_identity_byte(self, packet: bytearray):
        """Add the identity byte in-place if it is part of the packet protocol.

        Some Quickset protocols include an identity byte for the pan-tilt
        controller, while others do not. If the protocol includes the identity
        byte, this function will add that byte; otherwise, the packet will
        remain unaltered.

        Args:
            packet: The input packet to add the identity byte to.
            new_packet: The input packet with the identity byte removed.

        Returns:
            None: The array is modified in-place.
        """
        # NOTE: by default, we will assume that the protocol does not include
        # an identity byte. If it does, the subclass can override this method.
        pass

    def _remove_identity_byte(self, packet: bytearray):
        """Remove the identity byte in-place if it is part of the packet protocol.

        Some Quickset protocols include an identity byte for the pan-tilt
        controller, while others do not. If the protocol includes the identity
        byte, this function will remove that byte; otherwise, the packet will
        remain unaltered.

        It is expected and required that the first byte in the input packet is
        the identity byte.

        Args:
            packet: The input packet to remove the identity byte from.

        Returns:
            None: The array is modified in-place.
        """
        # NOTE: by default, we will assume that the protocol does not include
        # an identity byte. If it does, the subclass can override this method.
        pass

    @abstractmethod
    def _assemble_get_status(self) -> bytearray:
        """Assemble a packet to get the pan-tilt's status

        Returns:
            packet: Get status command and data bytes.
        """
        pass

    @abstractmethod
    def _parse_get_status(self, status):
        """Parse the status packet returned by the pan-tilt.

        Args:
            status:
                A StatusReponse namedtuple. The exact fields of the tuple
                differ for different protocols.
            
        """
        pass

    def _assemble_fault_reset(self) -> bytearray:
        """Assemble a packet to clear any hard faults.

        Possible hard faults are timeout, direction error, and current overload.

        Returns:
            packet: A "get status" packet with the reset bit set.
        """
        # Set the reset bit high
        status_cmd = GetStatusCmd()
        status_cmd.RES = 1

        # Set all jog speeds to 0
        pan_jog = 0
        tilt_jog = 0
        zoom_jog = 0
        focus_jog = 0

        # Return a bytearray because we need to support mutable sequence
        # operations like extend and insert.
        data_bytes = bytearray((status_cmd.base, pan_jog, tilt_jog, zoom_jog, 
                              focus_jog))

        return data_bytes

    def _assemble_get_communication_timeout(self) -> bytearray:
        """Assemble a packet to get the current value of the communication timeout.

        Returns:
            byte: The timeout command byte to send to the pan-tilt controller.
        """
        # Set the query bit (bit 7) to 1.
        # NOTE: Bit indexing starts at 0 in the QuickSet documentation.
        byte = (0b1000_0000).to_bytes()

        # Return a bytearray because we need to support mutable sequence
        # operations like extend and insert.
        return bytearray(byte)

    def _parse_communication_timeout(self, packet: bytearray) -> int:
        """Parse the current communication timeout value.

        Args:
            packet: The data byte associated with the "get communication
            timeout" packet sent by the pan-tilt controller.

        Returns:
            timeout: The pan-tilt controller's communication timeout, in seconds.
        """
        if len(packet) > 1:
            raise RuntimeError("Packet is too long."
                               " It should only have one byte, but it has"
                               f" {len(packet)} bytes.")

        # The timeout value is in bits 6--0 of the data packet, so we mask
        # those bits.
        timeout = packet[0] & 0b0111_1111

        return timeout

    def _assemble_set_communication_timeout(self, timeout: int) -> bytearray:
        """Set the communication timeout.

        Args:
            timeout:
                The timeout value to set. Must be an integer between 0 and 120
                seconds. A value of 0 disables the communication timeout.

        Returns:
            byte:
                The timeout command byte to send to the pan-tilt controller.
        """
        if timeout > 120 or timeout < 0:
            warnings.warn("Timeout value must be between 0 and 120 seconds."
                          + " Timeout will not be set.")
            return None

        # Return a bytearray because we need to support mutable sequence
        # operations like extend and insert.
        return bytearray(timeout.to_bytes())

    def _assemble_move_to_entered(self,
                                  pan: float | None = None,
                                  tilt: float | None = None) -> bytearray:
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
        pan = int(pan * self._ANGLE_MULTIPLIER)
        tilt = int(tilt * self._ANGLE_MULTIPLIER)

        pan_bytes = self.int_to_bytes(pan)
        tilt_bytes = self.int_to_bytes(tilt)

        # Concatenate the bytes together
        data_bytes = pan_bytes + tilt_bytes

        return data_bytes

    def _parse_move_to_entered(self):
        pass

    def _assemble_move_to_delta(self,
                                pan: float | None = None,
                                tilt: float | None = None) -> bytearray:
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

    def _parse_move_to_delta(self):
        pass


class PTCR20(QuicksetProtocol):

    GenStatus = bitfield.make_bf(name='GenStatus', basetype=c_uint8,
                                 fields=[
                                     ('DWNM', c_bool, 1),
                                     ('UPM', c_bool, 1),
                                     ('CCWM', c_bool, 1),
                                     ('CWM', c_bool, 1),
                                     ('OSLR', c_bool, 1),
                                     ('DES', c_bool, 1),
                                     ('EXEC', c_bool, 1),
                                     ('ENC', c_bool, 1),
                                 ])
    GenStatus.__doc__ = """\
    General status bit set.

    From LSB to MSB, the bits are:
    - DWNM: Down axis moving.
    - UPM: Up axis moving.
    - CCWM: Counter-clockwise axis moving.
    - CWM: Clockwise axis moving.
    - OSLR: Controller is in soft limit override mode.
    - DES: Whether the returned coordinates are destination coordinates.
    - EXEC: Whether a move is currently executing.
    - ENC: Pan-tilt mount is encoder-based and soft/hard limits are ignored.
    """

    StatusResponse = namedtuple('StatusResponse',
                                ('pan', 'tilt', 'pan_status', 'tilt_status', 
                                 'gen_status', 'zoom','focus', 'n_cameras',
                                 'camera_data')
            )
    StatusResponse.__doc__ = """\
    PTCR20 Status response tuple.    

    Attributes:
        pan: Pan coordinate.
        tilt: Tilt coordinate.
        pan_status: Pan status bitset from the PanStatus BitField.
        tilt_status: Tilt status bitset from the TiltStatus BitField.
        gen_status: General status bitset from the GenStatus BitField.
        zoom: Zoom coordinate.
        focus: Focus coordinate.
        n_cameras: Number of cameras installed.
        camera_data: Any camera data associated with the installed cameras.
    """

    def __init__(self, identity=0):
        super().__init__()
        self.identity = identity

    def _add_identity_byte(self, packet: bytearray):
        packet.insert(0, self.identity)

    def _remove_identity_byte(self, packet: bytearray):
        # The identity byte is assumed to be the first byte since the ACK byte
        # will have been removed before this is called.
        del packet[0]

    def _assemble_get_status(self):
        """Assemble a basic 'get status' packet.
        
        The format of the get status packet, from MSB to LSB is:
        1. status bitset
        2. pan jog
        3. tilt jog
        4. zoom jog
        5. focus jog

        Since this particular get status command is only intended to
        get the status, all of the bytes are set to 0.

        Returns:
            packet: The get status packet to send to the pan-tilt controller.
        """
        cmd = GetStatusCmd();

        pan_jog = 0
        tilt_jog = 0
        zoom_jog = 0
        focus_jog = 0

        return bytearray((cmd.base, pan_jog, tilt_jog, zoom_jog, focus_jog))


    def _parse_get_status(self, packet: bytearray):
        """Parse a status response from the pan-tilt mount.

        Args:
            packet: The status response to parse.

        Returns:
            status:
                A StatusReponse namedtuple containing the following fields:
                - pan: the pan coordinate
                - tilt: the tilt coordinate
                - pan_status: pan status bits
                - tilt_status: tilt status bits
                - gen_status: general status bits
                - zoom: zoom coordinate
                - focus: focus coordinate
                - n_cameras: number of cameras
                - camera_data: camera data; None if no cameras are attached
        """
        
        pan = self.bytes_to_int(packet[0:2]) / self._ANGLE_MULTIPLIER
        tilt = self.bytes_to_int(packet[2:4]) / self._ANGLE_MULTIPLIER

        # In the following, we have to assign the status integer to the base
        # property of the BitField object. This was not obvious from the
        # bitfield documentation.
        pan_status = PanStatus()
        pan_status.base = packet[4]

        tilt_status = TiltStatus()
        tilt_status.base = packet[5]

        gen_status = self.GenStatus()
        gen_status.base = packet[6]

        zoom = packet[7]
        focus = packet[8]

        n_cameras = packet[9]

        # If a camera is present, the rest of the packet will be camera data
        if len(packet) > 10:
            camera_data = packet[10:]
        else:
            camera_data = None

        return self.StatusResponse(pan, tilt, pan_status, tilt_status, gen_status,
                              zoom, focus, n_cameras, camera_data)


class PTHR90(QuicksetProtocol):

    GenStatus = bitfield.make_bf(name='GenStatus', basetype=c_uint8,
                                    fields=[
                                        ('DWNM', c_bool, 1),
                                        ('UPM', c_bool, 1),
                                        ('CCWM', c_bool, 1),
                                        ('CWM', c_bool, 1),
                                        ('OSLR', c_bool, 1),
                                        ('DES', c_bool, 1),
                                        ('EXEC', c_bool, 1),
                                        ('HRES', c_bool, 1),
                                    ])

    def __init__(self):
        super().__init__()

    def _assemble_get_status(self):
        pass

    def _parse_get_status(self):
        pass

GetStatusCmd = bitfield.make_bf(name='GetStatusCmd', basetype=c_uint8,
                                fields=[
                                    ('RES', c_bool, 1),
                                    ('STOP', c_bool, 1),
                                    ('OSL', c_bool, 1),
                                    ('RU', c_bool, 1),
                                ])
GetStatusCmd.__doc__ = """\
Bit set for the "Get Status" command.

From LSB to MSB, the fields are:
- RES: Reset/clear any latching/hard faults.
- STOP: Stop an automated move-to command.
- OSL: Override soft limits.
- RU: Return coordinates in resolver units instead of angles.
"""

PanStatus = bitfield.make_bf(name='PanStatus', basetype=c_uint8,
                                fields=[
                                    ('PRF', c_bool, 1),
                                    ('OL', c_bool, 1),
                                    ('DE', c_bool, 1),
                                    ('TO', c_bool, 1),
                                    ('CCWHL', c_bool, 1),
                                    ('CWHL', c_bool, 1),
                                    ('CCWSL', c_bool, 1),
                                    ('CWSL', c_bool, 1),
                                ])
PanStatus.__doc__= """\
Pan status bit set.

From LSB to MSB, the fields are:
- PRF: Pan resolver fault.
- OL: Current overload.
- DE: Direction error.
- TO: Move timeout.
- CCWHL: Counter-clockwise hard limit reached.
- CWHL: Clockwise hard limit reached.
- CCWSL: Counter-clockwise soft limit reached.
- CWSL: Clockwise soft limit reached.
"""

TiltStatus = bitfield.make_bf(name='TiltStatus', basetype=c_uint8,
                                fields=[
                                    ('TRF', c_bool, 1),
                                    ('OL', c_bool, 1),
                                    ('DE', c_bool, 1),
                                    ('TO', c_bool, 1),
                                    ('DHL', c_bool, 1),
                                    ('UHL', c_bool, 1),
                                    ('DSL', c_bool, 1),
                                    ('USL', c_bool, 1),
                                ])
TiltStatus.__doc__= """\
Tilt status bit set.

From LSB to MSB, the fields are:
- TRF: Tilt resolver fault.
- OL: Current overload.
- DE: Direction error.
- TO: Move timeout.
- DHL: Down hard limit reached.
- UHL: Up hard limit reached.
- DSL: Down soft limit reached.
- USL: Up soft limit reached.
"""
