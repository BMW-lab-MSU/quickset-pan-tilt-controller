import serial
import time
from abc import ABC


class QuicksetController(ABC):
    def __init__(self, ID, protocol, serial_port, baud_rate=9600):
        self.id: str = ID
        self.fw_version = None
        self.soft_limits = []
        self.CMD_LIST = set()

        self.serial = serial.Serial(port=serial_port, baudrate=baud_rate)

    def home(self):
        self.send(33, 0, 0)

    def move_delta(self, pan, tilt):
        self.send(31, pan, tilt)

    def move_absolute(self, pan, tilt):
        self.send(33, pan, tilt)

    def get_status(self):
        Status = self.send(30)
        return Status

    def calculate_lrc(self, data):
        lrc = bytes.fromhex('00')  # Initialize LRC value to zero
        print(f"DATA: {data}")
        bytedata = [int(d) for d in data]
        print(f"INT DATA: {bytedata}")
        for byte in bytedata:
            # Print binary representation of each byte
            print(f"BYTE: {(byte)[2:].zfill(8)} for byte: {byte}")
            lrc ^= byte
        # Print binary representation of the final LRC value
        print(f"LRC: {bin(lrc)[2:].zfill(8)}")
        return bytes([lrc])  # Return LRC value as a byte

    def send(self, cmd):

        self.serial.write(bytes.fromhex('02'))  # Send Start
        self.serial.write(bytes.fromhex(self.ID))  # Send ID

        if data is not None:
            command = bytes.fromhex(command)
            data = bytes.fromhex(data)
            self.serial.write(command)
            self.serial.write(data)
            self.serial.write(self.calculate_lrc(command + data))
        else:
            command = bytes.fromhex(command)
            self.serial.write(command)
            self.serial.write(self.calculate_lrc(command))

        self.serial.write(self.ETX)
        time.sleep(0.005)
