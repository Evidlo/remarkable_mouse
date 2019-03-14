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
# e_code_stylus_xpos = 1
# e_code_stylus_ypos = 0
# e_code_stylus_pressure = 24
e_code_finger_xpos = 53
e_code_finger_ypos = 54
e_code_finger_pressure = 58
e_code_finger_touch = 57
e_value_finger_up = -1

# stylus_width = 15725
# stylus_height = 20951
finger_width = 767
finger_height = 1023

mouse = Controller()
logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)


# remap wacom coordinates in various orientations
def fit(x, y, finger_width, finger_height, monitor, orientation):

    if orientation == 'vertical':
        y = finger_height - y
    elif orientation == 'right':
        x, y = y, x
        finger_width, finger_height = finger_height, finger_width
    elif orientation == 'left':
        x, y = finger_height - y, x
        finger_width, finger_height = finger_height, finger_width

    ratio_width, ratio_height = monitor.width / finger_width, monitor.height / finger_height
    scaling = ratio_width if ratio_width > ratio_height else ratio_height

    return (
        scaling * (x - (finger_width - monitor.width / scaling) / 2),
        scaling * (y - (finger_height - monitor.height / scaling) / 2)
    )


def open_eventfile(args):
    """ssh to reMarkable and open event1"""

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
    _, stdout, _ = client.exec_command('cat /dev/input/event1')

    return stdout


def read_tablet(args):
    """Loop forever and map evdev events to mouse"""

    new_x = new_y = False
    last_x = last_y = None
    x = y = temp_x = temp_y = 0
    moved = False

    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))

    stdout = open_eventfile(args)

    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', stdout.read(16))


        if e_type == e_type_abs:

            # handle x direction
            if e_code == e_code_finger_xpos:
                log.debug(f'{e_value}')
                x = e_value
                new_x = True
                if last_x is not None:
                    temp_x += x - last_x
                last_x = x

            # handle y direction
            elif e_code == e_code_finger_ypos:
                log.debug(f'\t{e_value}')
                y = e_value
                new_y = True
                if last_y is not None:
                    temp_y += y - last_y
                    print(last_y, y, temp_y)
                    moved = True
                else:
                    print(' . ', y, temp_y)
                last_y = y

            # handle draw
            elif e_code == e_code_finger_pressure:
                log.debug(f'\t\t{e_value}')
                if e_value > args.threshold:
                    mouse.press(Button.left)
                else:
                    mouse.release(Button.left)

            elif e_code == e_code_finger_touch:
                log.debug('\t\t\tup')
                if e_value == e_value_finger_up:
                    last_x = None
                    last_y = None
                    # if the mouse hasn't moved since the last finger lift, send a click
                    print(' . ', x, temp_x, moved, 'u')
                    if not moved:
                        mouse.press(Button.left)
                        mouse.release(Button.left)

                    moved = False


            # only move when x and y are updated for smoother mouse
            if new_y or new_x:
                mapped_x, mapped_y = fit(
                    temp_x, temp_y,
                    finger_width, finger_height,
                    monitor,
                    args.orientation
                )
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )

                new_x = new_y = False
                # last_x, last_y = x, y

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
