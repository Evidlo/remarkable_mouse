import logging
import struct
from screeninfo import get_monitors
import time
import math
# from .codes import EV_SYN, EV_ABS, ABS_X, ABS_Y, BTN_TOUCH
from .codes import codes
from .common import get_monitor, remap, wacom_max_x, wacom_max_y, log_event, get_current_monitor_num


# The amount of time waiting for stream.read(16) that counts as the pen becoming out of range
TIMEOUT = 0.2

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')


# wacom digitizer dimensions
# touchscreen dimensions
# finger_width = 767
# finger_height = 1023

def read_tablet(rm_inputs, *, orientation, monitor_num, region, threshold, mode, auto_monitor, monitor_update):
    """Loop forever and map evdev events to mouse

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor_num (int): monitor number to map to
        region (boolean): whether to selection mapping region with region tool
        threshold (int): pressure threshold
        mode (str): mapping mode
        auto_monitor (str)
    """

    from pynput.mouse import Button, Controller

    mouse = Controller()


    monitor, _ = get_monitor(region, monitor_num, orientation)
    
    log.debug('Chose monitor: {}'.format(monitor))

    x = y = 0

    
    stream = rm_inputs['pen'] 
    while True:
        if auto_monitor and monitor_update[0] != monitor_num:
            monitor_num=monitor_update[0]
            monitor, _ = get_monitor(region, monitor_num, orientation)
        
        start = time.time()
        try:
            data = stream.read(16)
        except TimeoutError:
            continue
        
        # time spent waiting for stream.read(). Used to see if pen was lifted for relative tracking since stream.read() will wait until more data comes in
        elapsed = time.time() - start
        
        if elapsed > 0.2:
            print(elapsed)
            lastx_needsupdate=True
            lasty_needsupdate=True

        e_time, e_millis, e_type, e_code, e_value = struct.unpack('2IHHi', data)

        # handle x direction
        if codes[e_type][e_code] == 'ABS_X':
            x = e_value
            
        # handle y direction
        if codes[e_type][e_code] == 'ABS_Y':
            y = e_value        
       
        # handle draw
        if codes[e_type][e_code] == 'BTN_TOUCH':
            if e_value == 1:
                mouse.press(Button.left)
            else:
                mouse.release(Button.left)

        if codes[e_type][e_code] == 'SYN_REPORT':
            mapped_x, mapped_y = remap(
                x, y,
                wacom_max_x, wacom_max_y,
                monitor.width, monitor.height,
                mode, orientation,
            )
            if relative:
                mapped_last_x, mapped_last_y = remap(
                last_x, last_y,
                wacom_max_x, wacom_max_y,
                monitor.width, monitor.height,
                mode, orientation,
            )
                
                
                # print("startx", start_x)
                # print("Mappedx", mapped_x)
                # print("dx", monitor.x + mapped_x - start_x)
                
                print(mapped_x)
                
                mouse.move(
                    monitor.x + mapped_x - mapped_last_x,
                    monitor.y + mapped_y - mapped_last_y
                )
                
            else:
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )
            last_x = x
            last_y = y

        if log.level == logging.DEBUG:
            log_event(e_time, e_millis, e_type, e_code, e_value)
