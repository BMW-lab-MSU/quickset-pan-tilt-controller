import serial
import time

class PTC_Controller:
    
    def __init__(self, name: str = "Pan Tilt Controller Object", Identity: str = bytes.fromhex('00')) -> None :
        self.name: str = name
        self.identity: str = Identity
        com_port = 'COM8' # change to your COM port number
        self.serial = serial.Serial(com_port, baudrate=9600, timeout=1)  
        self.STX = bytes.fromhex('02') #start of text character
        self.ETX = bytes.fromhex('03') #end of text character
        print(f"{self.name} initialized")
    
    def calculate_lrc(self, data):
        lrc = 0b00000000  # Initialize LRC value to zero
        for byte in data:
            print(f"BYTE: {bin(byte)[2:].zfill(8)} for byte: {byte}")  # Print binary representation of each byte
            lrc ^= byte
        print("DATA: ", data)
        print("LRC: ", bin(lrc)[2:].zfill(8))  # Print binary representation of the final LRC value
        return bytes([lrc])  # Return LRC value as a byte
    
    def calculate_lrc_hex(self, data):
        lrc = bytes.fromhex('00')  # Initialize LRC value to zero
        print(f"DATA: {data}")
        bytedata = [int(d) for d in data]
        print(f"INT DATA: {bytedata}")
        for byte in bytedata:
            print(f"BYTE: {(byte)[2:].zfill(8)} for byte: {byte}")  # Print binary representation of each byte
            lrc ^= byte
        print(f"LRC: {bin(lrc)[2:].zfill(8)}")  # Print binary representation of the final LRC value
        return bytes([lrc])  # Return LRC value as a byte
    
    def fault_reset(self):
        self.serial.write(self.STX)             # Send Start
        self.serial.write(self.identity)        # Send ID
        self.serial.write(bytes.fromhex('31'))  # Send Command
        self.serial.write(bytes.fromhex('01'))  # Send Sub-Command
        self.serial.write(bytes.fromhex('00'))  # Send Sub-Command
        self.serial.write(bytes.fromhex('00'))  # Send Sub-Command
        self.serial.write(bytes.fromhex('00'))  # Send Sub-Command
        self.serial.write(bytes.fromhex('00'))  # Send Sub-Command
        self.serial.write(bytes.fromhex('30'))  # Send End Command
        self.serial.write(self.ETX)             # Send End Character
    
    def move_to(self, Pan: int=0, Tilt: int=0):
        self.serial.write(self.STX)             # Send Start
        self.serial.write(self.identity)        # Send ID
        self.serial.write(bytes.fromhex('33'))  # Send Command
        FluffPan = hex(Pan)[2:].zfill(4)
        FluffTilt = hex(Tilt)[2:].zfill(4)
        self.serial.write(bytes.fromhex(FluffPan[2:]))   # Send Sub-Command
        self.serial.write(bytes.fromhex(FluffPan[0:2]))   # Send Sub-Command
        self.serial.write(bytes.fromhex(FluffTilt[2:]))   # Send Sub-Command
        self.serial.write(bytes.fromhex(FluffTilt[0:2]))   # Send Sub-Command
        self.serial.write(bytes.fromhex('33'))  # Send End Command
        self.serial.write(self.ETX)             # Send End Character
    
    def send_data(self, command, data):

        self.serial.write(self.STX)      # Send Start
        self.serial.write(self.identity) # Send ID

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
    
    def read(self, ammount):
        self.data = self.serial.read(ammount)



# c = PTC_Controller()
# print(f"{bytes.fromhex('31')}")
# print(f"{bytes.fromhex('0x31'[2:])}")
# print(f"LRC?: {c.calculate_lrc_hex(['31','01','00','00','00','00'])}")