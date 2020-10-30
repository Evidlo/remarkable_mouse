import logging
import struct
import subprocess
from screeninfo import get_monitors
import time

logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)

# Maximum value that can be reported by the Wacom driver for the X axis
MAX_ABS_X = 20967

# Maximum value that can be reported by the Wacom driver for the Y axis
MAX_ABS_Y = 15725


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
    device.name = 'reMarkable tablet'

    device.id = {
        'bustype': 0x18, # i2c
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

    # Enable position, tilt, distance and pressure change events
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
def remap(wacom_width, wacom_height, monitor_width,
          monitor_height, orientation=None):

    min_x = 0
    min_y = 0
    max_x = 0
    max_y = 0
    
    scale = wacom_width
    if orientation in ('top', 'bottom'):
        scale = wacom_height

    ratio = wacom_height / monitor_height
    screen_ratio = monitor_width - scale / ratio
    
    min_scale = ratio * (0 - screen_ratio / 2)
    max_scale = ratio * (monitor_width - screen_ratio / 2)

    min_x = min_scale
    max_x = max_scale
    max_y = wacom_height
    
    if orientation in ('top', 'bottom'):
        min_x = 0
        min_y = min_scale
        max_x = wacom_width
        max_y = max_scale
    
    return (
        min_x,
        min_y,
        max_x,
        max_y
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
        'xinput --set-prop "reMarkable tablet stylus" "Wacom Rotation" {}'.format(orientation),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting orientation: %s", result.stderr)

    # set monitor to use
    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))
    result = subprocess.run(
        'xinput --map-to-output "reMarkable tablet stylus" {}'.format(monitor.name),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting monitor: %s", result.stderr)

    # set stylus pressure
    result = subprocess.run(
        'xinput --set-prop "reMarkable tablet stylus" "Wacom Pressure Threshold" {}'.format(args.threshold),
        capture_output=True,
        shell=True
    )
    if result.returncode != 0:
        log.warning("Error setting pressure threshold: %s", result.stderr)
        
    if args.mode == 'fit':
        coordinates = remap(MAX_ABS_X, MAX_ABS_Y, monitor.width, monitor.height, args.orientation)
        log.debug("Wacom tablet area: {} {} {} {}".format(*coordinates))
        result = subprocess.run(
            'xinput --set-prop "reMarkable tablet stylus" "Wacom Tablet Area" \
            {} {} {} {}'.format(*coordinates),
            capture_output=True,
            shell=True
        
    import libevdev

    # While debug mode is active, we log events grouped together between
    # SYN_REPORT events. Pending events for the next log are stored here
    pending_events = []

    while True:
        e_time, e_millis, e_type, e_code, e_value = struct.unpack('2IHHi', remote_device.read(16))
        e_bit = libevdev.evbit(e_type, e_code)
        event = libevdev.InputEvent(e_bit, value=e_value)

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
