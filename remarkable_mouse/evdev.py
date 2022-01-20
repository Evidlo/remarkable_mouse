import logging
import struct
import subprocess
from screeninfo import get_monitors
import time
from itertools import cycle
from socket import timeout as TimeoutError
import libevdev
from libevdev import EV_SYN, EV_KEY, EV_ABS

from .common import get_monitor, remap, wacom_width, wacom_height

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

# Maximum value that can be reported by the Wacom driver for the X axis
MAX_ABS_X = 20967

# Maximum value that can be reported by the Wacom driver for the Y axis
MAX_ABS_Y = 15725

# Maximum value that can be reported by the cyttsp5_mt driver for the X axis
MT_MAX_ABS_X = 767

# Maximum value that can be reported by the cyttsp5_mt driver for the Y axis
MT_MAX_ABS_Y = 1023

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

    # ----- Buttons -----

    # Enable buttons supported by the digitizer
    device.enable(libevdev.EV_KEY.BTN_TOOL_PEN)
    device.enable(libevdev.EV_KEY.BTN_TOOL_RUBBER)
    device.enable(libevdev.EV_KEY.BTN_TOUCH)
    device.enable(libevdev.EV_KEY.BTN_STYLUS)
    device.enable(libevdev.EV_KEY.BTN_STYLUS2)
    device.enable(libevdev.EV_KEY.BTN_0)
    device.enable(libevdev.EV_KEY.BTN_1)
    device.enable(libevdev.EV_KEY.BTN_2)

    # ----- Touch -----

    # Enable Touch input
    device.enable(
        libevdev.EV_ABS.ABS_MT_POSITION_X,
        libevdev.InputAbsInfo(minimum=0, maximum=MT_MAX_ABS_X, resolution=2531) # resolution correct?
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_POSITION_Y,
        libevdev.InputAbsInfo(minimum=0, maximum=MT_MAX_ABS_Y, resolution=2531) # resolution correct?
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_PRESSURE,
        libevdev.InputAbsInfo(minimum=0, maximum=255)
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TOUCH_MAJOR,
        libevdev.InputAbsInfo(minimum=0, maximum=255)
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TOUCH_MINOR,
        libevdev.InputAbsInfo(minimum=0, maximum=255)
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_ORIENTATION,
        libevdev.InputAbsInfo(minimum=-127, maximum=127)
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_SLOT,
        libevdev.InputAbsInfo(minimum=0, maximum=31)
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TOOL_TYPE,
        libevdev.InputAbsInfo(minimum=0, maximum=1)
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TRACKING_ID,
        libevdev.InputAbsInfo(minimum=0, maximum=65535)
    )

    # ----- Pen -----

    # Enable pen input, tilt and pressure
    device.enable(
        libevdev.EV_ABS.ABS_X,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=MAX_ABS_X,
            resolution=2531
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_Y,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=MAX_ABS_Y,
            resolution=2531
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_PRESSURE,
        libevdev.InputAbsInfo(minimum=0, maximum=4095)
    )
    device.enable(
        libevdev.EV_ABS.ABS_DISTANCE,
        libevdev.InputAbsInfo(minimum=0, maximum=255)
    )
    device.enable(
        libevdev.EV_ABS.ABS_TILT_X,
        libevdev.InputAbsInfo(minimum=-9000, maximum=9000)
    )
    device.enable(
        libevdev.EV_ABS.ABS_TILT_Y,
        libevdev.InputAbsInfo(minimum=-9000, maximum=9000)
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

    monitor = get_monitor(region, monitor_num, orientation)

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

        e_bit = libevdev.evbit(e_type, e_code)
        e = libevdev.InputEvent(e_bit, value=e_value)

        local_device.send_events([e])

        if e.matches(EV_ABS):

            # handle x direction
            if e.matches(EV_ABS.ABS_Y):
                x = e.value

            # handle y direction
            if e.matches(EV_ABS.ABS_X):
                y = e.value

        elif e.matches(EV_SYN):
            mapped_x, mapped_y = remap(
                x, y,
                wacom_width, wacom_height,
                monitor.width, monitor.height,
                mode, orientation
            )
            local_device.send_events([e])

        else:
            local_device.send_events([e])

        # While debug mode is active, we log events grouped together between
        # SYN_REPORT events. Pending events for the next log are stored here
        if log.level == logging.DEBUG:
            if e_bit == libevdev.EV_SYN.SYN_REPORT:
                event_repr = ', '.join(
                    '{} = {}'.format(
                        e.code.name,
                        e.value
                    ) for event in pending_events
                )
                log.debug('{}.{:0>6} - {}'.format(e_time, e_millis, event_repr))
                pending_events = []
            else:
                pending_events.append(event)

