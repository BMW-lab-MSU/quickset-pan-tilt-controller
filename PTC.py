from PTC_Class import PTC_Controller
import time

c = PTC_Controller()
while True:
    c.move_to(500,500)
    time.sleep(5)
    c.fault_reset()
    time.sleep(0.5)
    c.move_to(0,0)
    time.sleep(5)
    c.fault_reset()
    time.sleep(0.5)
    
    #read data sent back and print
    #c.read(2)


