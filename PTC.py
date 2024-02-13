from PTC_Class import PTC_Controller
import time

c = PTC_Controller()
while True:
    c.move_to(500,500)
    time.sleep(10)
    c.fault_reset()
    time.sleep(0.5)
    c.move_to(0,0)
    time.sleep(10)
    
    #read data sent back and print
    #c.read(2)


