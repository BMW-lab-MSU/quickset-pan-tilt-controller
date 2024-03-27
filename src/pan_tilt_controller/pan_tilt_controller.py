import serial
import time

class PanTiltController:
    def __init__(self, ID):
        self.ID: str = ID
        self.fwVersion = None
        self.softLimits = []
        self.CommandList = set()
    
    def home(self):
        self.send(33, 0, 0)
    
    def moveDelta(self, pan, tilt):
        self.send(31, pan, tilt)
    
    def moveAbsolute(self,pan,tilt):
        self.send(33, pan, tilt)
        
    def getStatus(self):
        Status = self.send(30)
        return Status
    
    def calcLRC(self, data):
        lrc = bytes.fromhex('00')  # Initialize LRC value to zero
        print(f"DATA: {data}")
        bytedata = [int(d) for d in data]
        print(f"INT DATA: {bytedata}")
        for byte in bytedata:
            print(f"BYTE: {(byte)[2:].zfill(8)} for byte: {byte}")  # Print binary representation of each byte
            lrc ^= byte
        print(f"LRC: {bin(lrc)[2:].zfill(8)}")  # Print binary representation of the final LRC value
        return bytes([lrc])  # Return LRC value as a byte

    def send(self, cmd):
        
        self.serial.write(bytes.fromhex('02')) # Send Start
        self.serial.write(bytes.fromhex(self.ID)) # Send ID

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