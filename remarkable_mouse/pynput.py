import logging
import struct
from screeninfo import get_monitors

from .codes import EV_SYN, EV_ABS, ABS_X, ABS_Y, BTN_TOUCH
from .common import get_monitor, remap, wacom_width, wacom_height

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

# wacom digitizer dimensions
# touchscreen dimensions
# finger_width = 767
# finger_height = 1023

def read_tablet(rm_inputs, *, orientation, monitor_num, region, threshold, mode):
    """Loop forever and map evdev events to mouse

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor_num (int): monitor number to map to
        region (boolean): whether to selection mapping region with region tool
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    from pynput.mouse import Button, Controller

    mouse = Controller()

    monitor = get_monitor(region, monitor_num, orientation)
    log.debug('Chose monitor: {}'.format(monitor))

    x = y = 0

    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', rm_inputs['pen'].read(16))

        if e_type == EV_ABS:

            # handle x direction
            if e_code == ABS_Y:
                log.debug(e_value)
                x = e_value

            # handle y direction
            if e_code == ABS_X:
                log.debug('\t{}'.format(e_value))
                y = e_value

        # handle draw
        if e_code == BTN_TOUCH:
            log.debug('\t\t{}'.format(e_value))
            if e_value == 1:
                log.debug('PRESS')
                mouse.press(Button.left)
            else:
                log.debug('RELEASE')
                mouse.release(Button.left)

        if e_type == EV_SYN:
            mapped_x, mapped_y = remap(
                x, y,
                wacom_width, wacom_height,
                monitor.width, monitor.height,
                mode, orientation
            )
            mouse.move(
                monitor.x + mapped_x - mouse.position[0],
                monitor.y + mapped_y - mouse.position[1]
            )
