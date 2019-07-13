#!/bin/env python
# Evan Widloski - 2019-02-23
# Use reMarkable as mouse input

import argparse
import logging
import os
import sys
import struct
from getpass import getpass

import paramiko

logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)

# Maximum value that can be reported by the Wacom driver for the X axis
MAX_ABS_X = 20967

# Maximum value that can be reported by the Wacom driver for the Y axis
MAX_ABS_Y = 15725


# evtype_sync = 0
# evtype_key = 1
e_type_abs = 3

# evcode_stylus_distance = 25
# evcode_stylus_xtilt = 26
# evcode_stylus_ytilt = 27
e_code_stylus_xpos = 1
e_code_stylus_ypos = 0
e_code_stylus_pressure = 24
# evcode_finger_xpos = 53
# evcode_finger_ypos = 54
# evcode_finger_pressure = 58

stylus_width = 15725
stylus_height = 20951
# finger_width = 767
# finger_height = 1023


# remap wacom coordinates in various orientations
def fit(x, y, stylus_width, stylus_height, monitor, orientation):

    if orientation == 'vertical':
        y = stylus_height - y
    elif orientation == 'right':
        x, y = y, x
        stylus_width, stylus_height = stylus_height, stylus_width
    elif orientation == 'left':
        x, y = stylus_height - y, stylus_width - x
        stylus_width, stylus_height = stylus_height, stylus_width

    ratio_width, ratio_height = monitor.width / stylus_width, monitor.height / stylus_height
    scaling = ratio_width if ratio_width > ratio_height else ratio_height

    return (
        scaling * (x - (stylus_width - monitor.width / scaling) / 2),
        scaling * (y - (stylus_height - monitor.height / scaling) / 2)
    )


def create_local_device():
    """
    Create a virtual input device on this host that has the same
    characteristics as a Wacom tablet.

    :returns: virtual input device
    """
    import libevdev
    device = libevdev.Device()

    # Set device properties to emulate those of Wacom tablets
    device.name = 'reMarkable tablet'
    device.id = {
        'bustype': 24,
        'vendor': 1386,
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

def open_remote_device(args, file='/dev/input/event0'):
    """
    Open a remote input device via SSH.

    :param args: command-line arguments
    :param file: path to the input device on the device
    :returns: read-only stream of input events
    """
    log.info("Connecting to input '{}' on '{}'".format(file, args.address))

    if args.key is not None:
        password = None
        try:
            pkey = paramiko.RSAKey.from_private_key_file(os.path.expanduser(args.key))
        except paramiko.ssh_exception.PasswordRequiredException:
            passphrase = getpass(
                "Enter passphrase for key '{}': ".format(os.path.expanduser(args.key))
            )
            pkey = paramiko.RSAKey.from_private_key_file(
                os.path.expanduser(args.key),
                password=passphrase
            )
    elif args.password:
        password = args.password
        pkey = None
    else:
        password = getpass(
            "Password for '{}': ".format(args.address)
        )
        pkey = None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.address,
        username='root',
        password=password,
        pkey=pkey,
        look_for_keys=False
    )

    # Start reading events
    _, stdout, _ = client.exec_command('cat ' + file)

    return stdout

def pipe_device(args, remote_device, local_device):
    """
    Pipe events from a remote device to a local device.

    :param args: command-line arguments
    :param remote_device: stream of events to read from
    :param local_device: local virtual device to write events to
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


def read_tablet(args):
    """Loop forever and map evdev events to mouse"""

    from screeninfo import get_monitors
    from pynput.mouse import Button, Controller

    lifted = True
    new_x = new_y = False

    mouse = Controller()

    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))

    stdout = open_remote_device(args)

    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', stdout.read(16))

        if e_type == e_type_abs:

            # handle x direction
            if e_code == e_code_stylus_xpos:
                log.debug(e_value)
                x = e_value
                new_x = True

            # handle y direction
            if e_code == e_code_stylus_ypos:
                log.debug('\t{}'.format(e_value))
                y = e_value
                new_y = True

            # handle draw
            if e_code == e_code_stylus_pressure:
                log.debug('\t\t{}'.format(e_value))
                if e_value > args.threshold:
                    if lifted:
                        log.debug('PRESS')
                        lifted = False
                        mouse.press(Button.left)
                else:
                    if not lifted:
                        log.debug('RELEASE')
                        lifted = True
                        mouse.release(Button.left)


            # only move when x and y are updated for smoother mouse
            if new_x and new_y:
                mapped_x, mapped_y = fit(x, y, stylus_width, stylus_height, monitor, args.orientation)
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )
                new_x = new_y = False


def main():
    try:
        parser = argparse.ArgumentParser(description="use reMarkable tablet as a mouse input")
        parser.add_argument('--debug', action='store_true', default=False, help="enable debug messages")
        parser.add_argument('--key', type=str, metavar='PATH', help="ssh private key")
        parser.add_argument('--password', default=None, type=str, help="ssh password")
        parser.add_argument('--address', default='10.11.99.1', type=str, help="device address")
        parser.add_argument('--orientation', default='left', choices=['vertical', 'left', 'right'])
        parser.add_argument('--monitor', default=0, type=int, metavar='NUM', help="monitor to use")
        parser.add_argument('--threshold', default=1000, type=int, help="stylus pressure threshold (default 1000)")
        parser.add_argument('--evdev', action='store_true', default=False, help="use evdev to support pen tilt (requires root, libev)")

        args = parser.parse_args()

        if args.debug:
            logging.getLogger('').setLevel(logging.DEBUG)
            log.setLevel(logging.DEBUG)
            log.info('Debugging enabled...')
        else:
            log.setLevel(logging.INFO)

        if args.evdev:
            try:
                local_device = create_local_device()
                log.info("Created virtual input device '{}'".format(local_device.devnode))
            except PermissionError:
                log.error('Insufficient permissions for creating a virtual input device')
                log.error('Make sure you run this program as root')
                sys.exit(1)

            remote_device = open_remote_device(args)
            pipe_device(args, remote_device, local_device)
        else:
            read_tablet(args)
    except KeyboardInterrupt:
        pass
    except EOFError:
        pass

if __name__ == '__main__':
    main()
