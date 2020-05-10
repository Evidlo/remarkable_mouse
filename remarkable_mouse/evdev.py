import logging
import struct

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

    # Set device properties to emulate those of Wacom tablet.
    # "pen" or "wacom" must be in the name or gdk will treat us as a TOUCHSCREEN device
    # rather than a PEN device.
    #
    # Then "Mutter", which is responsible for doing the input mapping will silently
    # refuse to map our device when requested in gnome-control-center
    #
    # (see https://gitlab.gnome.org/GNOME/gtk/blob/master/gdk/x11/gdkdevicemanager-xi2.c)
    # (See https://gitlab.gnome.org/GNOME/mutter/-/blob/master/src/backends/meta-input-settings.c)
    device.name = 'reMarkable pen' # keep "pen" !
    device.id = {
        'bustype': 0x03,   # usb though this is pretend and only for matching
        'vendor':  0x056a, # wacom since input systems will look for this and match x driver
        'product': 0x04,   # no collision https://www.the-sz.com/products/usbid/index.php?v=0x056A
        'version': 0       # I don't think this matters
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
            maximum=MAX_ABS_X
        )
    )
    device.enable(
        libevdev.EV_ABS.ABS_Y,
        libevdev.InputAbsInfo(
            minimum=0,
            maximum=MAX_ABS_Y
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


def pipe_device(args, remote_device, local_device):
    """
    Pipe events from a remote device to a local device.

    Args:
        args: argparse arguments
        remote_device (paramiko.ChannelFile): read-only stream of input events
        local_device: local virtual input device to write events to
    """
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
