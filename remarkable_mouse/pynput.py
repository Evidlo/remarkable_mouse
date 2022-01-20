import logging
import struct
from screeninfo import get_monitors
import libevdev
from libevdev import EV_SYN, EV_KEY, EV_ABS

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

        e_bit = libevdev.evbit(e_type, e_code)
        e = libevdev.InputEvent(e_bit, value=e_value)

        if e.matches(EV_ABS):

            # handle x direction
            if e.matches(EV_ABS.ABS_Y):
                log.debug(e.value)
                x = e.value

            # handle y direction
            if e.matches(EV_ABS.ABS_X):
                log.debug('\t{}'.format(e.value))
                y = e.value

        # handle draw
        if e.matches(EV_KEY.BTN_TOUCH):
            log.debug('\t\t{}'.format(e.value))
            if e.value == 1:
                log.debug('PRESS')
                mouse.press(Button.left)
            else:
                log.debug('RELEASE')
                mouse.release(Button.left)

        if e.matches(EV_SYN):
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
