import logging
import struct
import subprocess
from screeninfo import get_monitors
import time
from itertools import cycle
from socket import timeout as TimeoutError

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


# map computer screen coordinates to rM pen coordinates
def map_comp2pen(x, y, wacom_width, wacom_height, monitor_width,
          monitor_height, mode, orientation=None):

    if orientation in ('bottom', 'top'):
        x, y = y, x
        monitor_width, monitor_height = monitor_height, monitor_width

    ratio_width, ratio_height = wacom_width / monitor_width, wacom_height / monitor_height

    if mode == 'fit':
        scaling = max(ratio_width, ratio_height)
    elif mode == 'fill':
        scaling = min(ratio_width, ratio_height)
    else:
        raise NotImplementedError

    return (
        scaling * (x - (monitor_width - wacom_width / scaling) / 2),
        scaling * (y - (monitor_height - wacom_height / scaling) / 2)
    )

# map computer screen coordinates to rM touch coordinates
def map_comp2touch(x, y, touch_width, touch_height, monitor_width,
          monitor_height, mode, orientation=None):

    if orientation in ('left', 'right'):
        x, y = y, x
        monitor_width, monitor_height = monitor_height, monitor_width

    ratio_width, ratio_height = touch_width / monitor_width, touch_height / monitor_height

    if mode == 'fit':
        scaling = max(ratio_width, ratio_height)
    elif mode == 'fill':
        scaling = min(ratio_width, ratio_height)
    else:
        raise NotImplementedError

    return (
        scaling * (x - (monitor_width - touch_width / scaling) / 2),
        scaling * (y - (monitor_height - touch_height / scaling) / 2)
    )

def configure_xinput(*, orientation, monitor, threshold, mode):
    """
    Configure screen mapping settings from rM to local machine

    Args:
        orientation (str): location of charging port relative to screen
        monitor (int): monitor number to use
        threshold (int): pressure threshold for detecting pen
        mode (str): scaling mode when mapping reMarkable pen coordinates to screen
    """

    # give time for virtual device creation before running xinput commands
    time.sleep(1)

    # ----- Pen -----

    # set orientation with xinput
    orientation = {'left': 0, 'bottom': 1, 'top': 2, 'right': 3}[orientation]
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen stylus" "Wacom Rotation" {}'.format(orientation),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting orientation: %s", result.stderr.decode('utf8'))

    # set monitor to use
    monitor = get_monitors()[monitor]
    log.debug('Chose monitor: {}'.format(monitor))
    result = subprocess.run(
        'xinput --map-to-output "reMarkable pen stylus" {}'.format(monitor.name),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting monitor: %s", result.stderr.decode('utf8'))

    # set stylus pressure
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen stylus" "Wacom Pressure Threshold" {}'.format(threshold),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting pressure threshold: %s", result.stderr.decode('utf8'))

    # set fitting mode
    min_x, min_y = map_comp2pen(
        0, 0,
        MAX_ABS_X, MAX_ABS_Y, monitor.width, monitor.height,
        mode,
        orientation
    )
    max_x, max_y = map_comp2pen(
        monitor.width, monitor.height,
        MAX_ABS_X, MAX_ABS_Y, monitor.width, monitor.height,
        mode,
        orientation
    )
    log.debug("Wacom tablet area: {} {} {} {}".format(min_x, min_y, max_x, max_y))
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen stylus" "Wacom Tablet Area" \
        {} {} {} {}'.format(min_x, min_y, max_x, max_y),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting fit: %s", result.stderr.decode('utf8'))

    # ----- Touch -----

    # Set touch fitting mode
    mt_min_x, mt_min_y = map_comp2touch(
        0, 0,
        MT_MAX_ABS_X, MT_MAX_ABS_Y, monitor.width, monitor.height,
        mode,
        orientation
    )
    mt_max_x, mt_max_y = map_comp2touch(
        monitor.width, monitor.height,
        MT_MAX_ABS_X, MT_MAX_ABS_Y, monitor.width, monitor.height,
        mode,
        orientation
    )
    log.debug("Multi-touch area: {} {} {} {}".format(mt_min_x, mt_min_y, mt_max_x * 2, mt_max_y * 2))
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen touch" "Wacom Tablet Area" \
        {} {} {} {}'.format(mt_min_x, mt_min_y, mt_max_x, mt_max_y),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting fit: %s", result.stderr.decode('utf8'))
    result = subprocess.run( # Just need to rotate the touchscreen -90 so that it matches the wacom sensor.
        'xinput --set-prop "reMarkable pen touch" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1',
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting orientation: %s", result.stderr.decode('utf8'))


def read_tablet(rm_inputs, *, orientation, monitor, threshold, mode):
    """Pipe rM evdev events to local device

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor (int): monitor number to map to
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    local_device = create_local_device()
    log.debug("Created virtual input device '{}'".format(local_device.devnode))

    configure_xinput(
        orientation=orientation,
        monitor=monitor,
        threshold=threshold,
        mode=mode,
    )

    import libevdev

    pending_events = []

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
        event = libevdev.InputEvent(e_bit, value=e_value)

        local_device.send_events([event])

        # While debug mode is active, we log events grouped together between
        # SYN_REPORT events. Pending events for the next log are stored here
        if log.level == logging.DEBUG:
            if e_bit == libevdev.EV_SYN.SYN_REPORT:
                event_repr = ', '.join(
                    '{} = {}'.format(
                        event.code.name,
                        event.value
                    ) for event in pending_events
                )
                log.debug('{}.{:0>6} - {}'.format(e_time, e_millis, event_repr))
                pending_events = []
            else:
                pending_events.append(event)

