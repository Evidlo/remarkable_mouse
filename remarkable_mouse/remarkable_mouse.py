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

mouse = Controller()
logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)


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


def open_eventfile(args, file='/dev/input/event0'):
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
    print("Connected to {}".format(args.address))

    # Start reading events
    _, stdout, _ = client.exec_command('cat ' + file)

    return stdout


def read_tablet(args):
    """Loop forever and map evdev events to mouse"""

    new_x = new_y = False

    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))

    stdout = open_eventfile(args)

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
                    mouse.press(Button.left)
                else:
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
