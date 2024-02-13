from PTC_Class import PTC_Controller
import time

c = PTC_Controller()
while True:
    c.send_data('31', None)
    time.sleep(0.5)
    #read data sent back and print
    c.read(2)


