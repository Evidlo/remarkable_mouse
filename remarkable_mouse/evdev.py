import logging
import struct
import subprocess
from screeninfo import get_monitors
import time
from itertools import cycle
from socket import timeout as TimeoutError
import libevdev

from .codes import codes, types
from .common import get_monitor, remap_evdev, wacom_width, wacom_height, log_event

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

evdev_max_x = 20967
evdev_max_y = 15725

def create_local_device():
    """
    Create a virtual input device on this host that has the same
    characteristics as a Wacom tablet.

    Returns:
        virtual input device
    """
    import libevdev
    device = libevdev.Device()

    # Set device properties to emulate those of Wacom tablets
    device.name = 'reMarkable pen'

    device.id = {
        'bustype': 0x03, # usb
        'vendor': 0x056a, # wacom
        'product': 0,
        'version': 54
    }

    # Enable buttons supported by the digitizer
    device.enable(libevdev.EV_KEY.BTN_TOOL_PEN)
    device.enable(libevdev.EV_KEY.BTN_TOOL_RUBBER)
    device.enable(libevdev.EV_KEY.BTN_TOUCH)
    device.enable(libevdev.EV_KEY.BTN_STYLUS)
    device.enable(libevdev.EV_KEY.BTN_STYLUS2)
    device.enable(libevdev.EV_KEY.BTN_0)
    device.enable(libevdev.EV_KEY.BTN_1)
    device.enable(libevdev.EV_KEY.BTN_2)

    inputs = (
        # touch inputs
        (libevdev.EV_ABS.ABS_MT_POSITION_X,  0,    767,   2531),
        (libevdev.EV_ABS.ABS_MT_POSITION_Y,  0,    1023,  2531),
        (libevdev.EV_ABS.ABS_MT_PRESSURE,    0,    255,   None),
        (libevdev.EV_ABS.ABS_MT_TOUCH_MAJOR, 0,    255,   None),
        (libevdev.EV_ABS.ABS_MT_TOUCH_MINOR, 0,    255,   None),
        (libevdev.EV_ABS.ABS_MT_ORIENTATION, -127, 127,   None),
        (libevdev.EV_ABS.ABS_MT_SLOT,        0,    31,    None),
        (libevdev.EV_ABS.ABS_MT_TOOL_TYPE,   0,    1,     None),
        (libevdev.EV_ABS.ABS_MT_TRACKING_ID, 0,    65535, None),

        # pen inputs
        (libevdev.EV_ABS.ABS_X,        0,     20967,  2531), # cyttps5_mt driver
        (libevdev.EV_ABS.ABS_Y,        0,     15725,  2531), # cyttsp5_mt
        (libevdev.EV_ABS.ABS_PRESSURE, 0,     4095,   None),
        (libevdev.EV_ABS.ABS_DISTANCE, 0,     255,    None),
        (libevdev.EV_ABS.ABS_TILT_X,   -9000, 9000,   None),
        (libevdev.EV_ABS.ABS_TILT_Y,   -9000, 9000,   None)
    )

    for code, minimum, maximum, resolution in inputs:
        device.enable(
            code,
            libevdev.InputAbsInfo(
                minimum=minimum, maximum=maximum, resolution=resolution
            )
        )

    return device.create_uinput_device()


def read_tablet(rm_inputs, *, orientation, monitor_num, region, threshold, mode):
    """Pipe rM evdev events to local device

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor_num (int): monitor number to map to
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    local_device = create_local_device()
    log.debug("Created virtual input device '{}'".format(local_device.devnode))

    monitor, (tot_x, tot_y) = get_monitor(region, monitor_num, orientation)

    mon2wacom_x = wacom_height / tot_x
    mon2wacom_y = wacom_width / tot_y

    pending_events = []

    x = y = 0

    # loop inputs forever
    # for input_name, stream in cycle(rm_inputs.items()):
    stream = rm_inputs['pen']
    while True:
        try:
            data = stream.read(16)
        except TimeoutError:
            continue

        e_time, e_millis, e_type, e_code, e_value = struct.unpack('2IHHi', data)

        # intercept EV_ABS events and modify coordinates
        if types[e_type] == 'EV_ABS':
            # handle x direction
            if codes[e_type][e_code] == 'ABS_Y':
                y = e_value

            # handle y direction
            if codes[e_type][e_code] == 'ABS_X':
                x = e_value

            mapped_x = x / mon2wacom_x
            mapped_y = y / mon2wacom_y

            print(f'x: {x:5.0f}/{wacom_height} → {mapped_x:5.0f}/{tot_x}', end='')
            print(f'   y: {y:5.0f}/{wacom_width} → {mapped_y:5.0f}/{tot_y}')


            mapped_x, mapped_y = remap_evdev(
                mapped_x, mapped_y,
                tot_x, tot_y,
                monitor.x, monitor.y,
                monitor.width, monitor.height,
                mon2wacom_x / mon2wacom_y,
                mode, orientation,
            )

            mapped_x *= mon2wacom_x
            mapped_y *= mon2wacom_y


            # FIXME - something wrong with remapping
            # handle x direction
            if codes[e_type][e_code] == 'ABS_Y':
                e_value = int(mapped_y)

            # handle y direction
            if codes[e_type][e_code] == 'ABS_X':
                e_value = int(mapped_x)

        # pass events directly to libevdev
        e_bit = libevdev.evbit(e_type, e_code)
        e = libevdev.InputEvent(e_bit, value=e_value)
        local_device.send_events([e])

        if log.level == logging.DEBUG:
            log_event(e_time, e_millis, e_type, e_code, e_value)
