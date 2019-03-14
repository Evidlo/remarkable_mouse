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
from screeninfo import get_monitors
from pynput.mouse import Button, Controller

# EVTYPE_SYNC = 0
# EVTYPE_KEY = 1
EVTYPE_ABS = 3

# WACOM_EVCODE_DISTANCE = 25
# WACOM_EVCODE_XTILT = 26
# WACOM_EVCODE_YTILT = 27
EVCODE_STYLUS_PRESSURE = 24
EVCODE_STYLUS_XPOS = 0
EVCODE_STYLUS_YPOS = 1

wacom_width = 15725
wacom_height = 20951

mouse = Controller()
logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)


# remap wacom coordinates in various orientations
def fit(x, y, wacom_width, wacom_height, monitor, orientation):

    if orientation == 'vertical':
        y = wacom_height - y
    elif orientation == 'right':
        x, y = y, x
        wacom_width, wacom_height = wacom_height, wacom_width
    elif orientation == 'left':
        x, y = wacom_height - y, wacom_width - x
        wacom_width, wacom_height = wacom_height, wacom_width

    ratio_width, ratio_height = monitor.width / wacom_width, monitor.height / wacom_height
    scaling = ratio_width if ratio_width > ratio_height else ratio_height

    return (
        scaling * (x - (wacom_width - monitor.width / scaling) / 2),
        scaling * (y - (wacom_height - monitor.height / scaling) / 2)
    )


def open_eventfile(args):
    """ssh to reMarkable and open event0"""

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
    print("Connected to {}".format(args.address))

    # Start reading events
    _, stdout, _ = client.exec_command('cat /dev/input/event0')

    return stdout


def read_tablet(args):
    """Loop forever and map evdev events to mouse"""

    new_x = new_y = False

    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))

    stdout = open_eventfile(args)

    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', stdout.read(16))

        if e_type == EVTYPE_ABS:

            # handle x direction
            if e_code == WACOM_EVCODE_YPOS:
                log.debug(f'{e_value}')
                x = e_value
                new_x = True

            # handle y direction
            if e_code == WACOM_EVCODE_XPOS:
                log.debug(f'\t{e_value}')
                y = e_value
                new_y = True

            # handle draw
            if e_code == WACOM_EVCODE_PRESSURE:
                log.debug(f'\t\t{e_value}')
                if e_value > args.threshold:
                    mouse.press(Button.left)
                else:
                    mouse.release(Button.left)

            # only move when x and y are updated for smoother mouse
            if new_x and new_y:
                x, y = fit(x, y, wacom_width, wacom_height, monitor, args.orientation)
                mouse.move(
                    monitor.x + x - mouse.position[0],
                    monitor.y + y - mouse.position[1]
                )
                new_x = new_y = False

def main():

    try:
        parser = argparse.ArgumentParser(description="use reMarkable tablet as a mouse input")
        parser.add_argument('--orientation', default='left', choices=['vertical', 'left', 'right'])
        parser.add_argument('--monitor', default=0, type=int, metavar='NUM', help="monitor to use")
        parser.add_argument('--offset', default=(0, 0), type=int, metavar=('x', 'y'), nargs=2, help="offset mapped region on monitor")
        parser.add_argument('--debug', action='store_true', default=False, help="enable debug messages")
        parser.add_argument('--key', type=str, metavar='PATH', help="ssh private key")
        parser.add_argument('--password', default=None, type=str, help="ssh password")
        parser.add_argument('--address', default='10.11.99.1', type=str, help="device address")
        parser.add_argument('--threshold', default=1000, type=int, help="stylus pressure threshold (default 1000)")

        args = parser.parse_args()

        if args.debug:
            print('Debugging enabled...')
            logging.getLogger('').setLevel(logging.DEBUG)
            log.setLevel(logging.DEBUG)

        read_tablet(args)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
