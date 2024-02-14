import serial
import time
def calculate_lrc(data):
    lrc = 0b00000000  # Initialize LRC value to zero
    for byte in data:
        print("BYTE: ", bin(byte)[2:].zfill(8))  # Print binary representation of each byte
        lrc ^= byte
    print("DATA: ", data)
    print("LRC: ", bin(lrc)[2:].zfill(8))  # Print binary representation of the final LRC value
    return bytes([lrc])  # Return LRC value as a byte


def send_data(ser, command, data=None):
    STX =      bytes.fromhex('02') #start of text character
    ETX =      bytes.fromhex('03') #end of text character
    Identity = bytes.fromhex('00') #identity if only one device 


    ser.write(STX)
    ser.write(Identity) 

    if data is not None:
        command = bytes.fromhex(command)
        data = bytes.fromhex(data)
        ser.write(command)
        ser.write(data)
        ser.write(calculate_lrc(command + data))
    else:
        command = bytes.fromhex(command)
        ser.write(command)
        ser.write(calculate_lrc(command))

    ser.write(ETX)
    time.sleep(0.005)

com_port = 'COM6' # change to your COM port number
ser = serial.Serial(com_port, baudrate=9600, timeout=1)

while True:
    send_data(ser, '33', None)
    time.sleep(0.5)
    #read data sent back and print
    data = ser.read(2)

    # hex_value = 'AA'
    # byte_value = bytes.fromhex(hex_value)

    # for byte in byte_value:
    #     print("BITS: ", bin(byte)[2:].zfill(8))  # Print binary representation of each byte
    #     print("BYTE: " , byte)
    # ser.write(byte_value)
    # time.sleep(0.005)


    