from PTC_Class import PTC_Controller
import time

c = PTC_Controller()
while True:
    #print(f"LRC?: {c.calculate_lrc_hex(['31','01','00','00','00','00'])}")
    #break
    c.move_to(0,100)
    time.sleep(5)
    c.fault_reset()
    time.sleep(0.5)
    c.move_to_abs_0()
    time.sleep(5)
    c.fault_reset()
    time.sleep(0.5)
    
    #read data sent back and print
    #c.read(2)


