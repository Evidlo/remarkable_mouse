import logging
import struct
import subprocess
from screeninfo import get_monitors
import time
from socket import timeout

logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)

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

    # Enable buttons supported by the digitizer
    device.enable(libevdev.EV_KEY.BTN_TOOL_PEN)
    device.enable(libevdev.EV_KEY.BTN_TOOL_RUBBER)
    device.enable(libevdev.EV_KEY.BTN_TOUCH)
    device.enable(libevdev.EV_KEY.BTN_STYLUS)
    device.enable(libevdev.EV_KEY.BTN_STYLUS2)
    device.enable(libevdev.EV_KEY.KEY_POWER)
    device.enable(libevdev.EV_KEY.KEY_LEFT)
    device.enable(libevdev.EV_KEY.KEY_RIGHT)
    device.enable(libevdev.EV_KEY.KEY_HOME)
    
    # Enable Touch input
    device.enable(
        libevdev.EV_ABS.ABS_MT_POSITION_X,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=MT_MAX_ABS_X,
            resolution=2531 #?
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_POSITION_Y,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=MT_MAX_ABS_Y,
            resolution=2531 #?
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_PRESSURE,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=255
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TOUCH_MAJOR,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=255
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TOUCH_MINOR,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=255
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_ORIENTATION,
        libevdev.InputAbsInfo(
            minimum=-127,
            maximum=127
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_SLOT,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=31
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TOOL_TYPE,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=1
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_MT_TRACKING_ID,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=65535
        )
    )

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
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=4095
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_DISTANCE,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=255
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_TILT_X,
        libevdev.InputAbsInfo(
            minimum=-9000,
            maximum=9000
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_TILT_Y,
        libevdev.InputAbsInfo(
            minimum=-9000,
            maximum=9000
        )
    )

    return device.create_uinput_device()


# remap screen coordinates to wacom coordinates
def remap(x, y, wacom_width, wacom_height, monitor_width,
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

# remap screen coordinates to touch coordinates
def remapTouch(x, y, touch_width, touch_height, monitor_width,
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

def pipe_device(args, remote_device, local_device):
    """
    Pipe events from a remote device to a local device.

    Args:
        args: argparse arguments
        remote_device (paramiko.ChannelFile): read-only stream of input events
        local_device: local virtual input device to write events to
    """

    # give time for virtual device creation before running xinput commands
    time.sleep(1)

    # set orientation with xinput
    orientation = {'left': 0, 'bottom': 1, 'top': 2, 'right': 3}[args.orientation]
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen stylus" "Wacom Rotation" {}'.format(orientation),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting orientation: %s", result.stderr)

    # set monitor to use
    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))
    result = subprocess.run(
        'xinput --map-to-output "reMarkable pen stylus" {}'.format(monitor.name),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting monitor: %s", result.stderr)

    # set stylus pressure
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen stylus" "Wacom Pressure Threshold" {}'.format(args.threshold),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting pressure threshold: %s", result.stderr)

    # set fitting mode
    min_x, min_y = remap(
        0, 0,
        MAX_ABS_X, MAX_ABS_Y, monitor.width, monitor.height,
        args.mode,
        args.orientation
    )
    max_x, max_y = remap(
        monitor.width, monitor.height,
        MAX_ABS_X, MAX_ABS_Y, monitor.width, monitor.height,
        args.mode,
        args.orientation
    )
    log.debug("Wacom tablet area: {} {} {} {}".format(min_x, min_y, max_x, max_y))
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen stylus" "Wacom Tablet Area" \
        {} {} {} {}'.format(min_x, min_y, max_x, max_y),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting fit: %s", result.stderr)
    
    
    # set monitor to use
    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))
    result = subprocess.run(
        'xinput --map-to-output "reMarkable pen touch" {}'.format(monitor.name),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting monitor: %s", result.stderr)
    # Set touch fitting mode
    mt_min_x, mt_min_y = remapTouch(
        0, 0,
        MT_MAX_ABS_X, MT_MAX_ABS_Y, monitor.width, monitor.height,
        args.mode,
        args.orientation
    )
    mt_max_x, mt_max_y = remapTouch(
        monitor.width, monitor.height,
        MT_MAX_ABS_X, MT_MAX_ABS_Y, monitor.width, monitor.height,
        args.mode,
        args.orientation
    )
    log.debug("Multi-touch area: {} {} {} {}".format(mt_min_x, mt_min_y, mt_max_x, mt_max_y))
    result = subprocess.run(
        'xinput --set-prop "reMarkable pen touch" "Wacom Tablet Area" \
        {} {} {} {}'.format(mt_min_x, mt_min_y, mt_max_x, mt_max_y),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting fit: %s", result.stderr)
    result = subprocess.run( # Just need to rotate the touchscreen -90 so that it matches the wacom sensor.
        'xinput --set-prop "reMarkable pen touch" "Coordinate Transformation Matrix" \
        0 1 0 -1 0 1 0 0 1',
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting orientation: %s", result.stderr)


    import libevdev

    # While debug mode is active, we log events grouped together between
    # SYN_REPORT events. Pending events for the next log are stored here
    pending_events = []
    pen_down = 0

    while True:
        for device in remote_device:
            ev = 0
            try:
                ev = device.read(16)
            except timeout:
                continue

            e_time, e_millis, e_type, e_code, e_value = struct.unpack('2IHHi', ev)
            e_bit = libevdev.evbit(e_type, e_code)
            event = libevdev.InputEvent(e_bit, value=e_value)
            
            if e_bit == libevdev.EV_KEY.BTN_TOOL_PEN:
                pen_down = e_value

            if pen_down and 'ABS_MT' in event.code.name: # Palm rejection
                pass
            else:
                local_device.send_events([event])

            if args.debug:
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
                    pending_events += [event]
