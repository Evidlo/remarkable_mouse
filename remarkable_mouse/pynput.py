import logging
import struct
from screeninfo import get_monitors

# from .codes import EV_SYN, EV_ABS, ABS_X, ABS_Y, BTN_TOUCH
from .codes import codes
from .common import get_monitor, remap, wacom_max_x, wacom_max_y, log_event, get_current_monitor_num

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

# wacom digitizer dimensions
# touchscreen dimensions
# finger_width = 767
# finger_height = 1023

def read_tablet(rm_inputs, *, orientation, monitor_num, region, threshold, mode, auto_monitor, relative):
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
        if auto_monitor:
            new_monitor = get_current_monitor_num()
            if new_monitor != monitor_num:
                monitor_num = new_monitor
                monitor, _ = get_monitor(region, monitor_num, orientation)

        try:
            data = stream.read(16)
        except TimeoutError:
            continue

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
                mouse.move(
                    monitor.x + mapped_x,
                    monitor.y + mapped_y
                )
            else:
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )

        if log.level == logging.DEBUG:
            log_event(e_time, e_millis, e_type, e_code, e_value)
