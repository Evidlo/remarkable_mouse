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


def open_remote_device(args, file='/dev/input/event0'):
    """
    Open a remote input device via SSH.

    Args:
        args: argparse arguments
        file (str): path to the input device on the device
    Returns:
        (paramiko.ChannelFile): read-only stream of input events
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

    print("connected to", args.address)

    return stdout


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
        parser.add_argument('--evdev', action='store_true', default=False, help="use evdev to support pen tilt (requires root, no OSX support)")

        args = parser.parse_args()

        remote_device = open_remote_device(args)

        if args.debug:
            logging.getLogger('').setLevel(logging.DEBUG)
            log.setLevel(logging.DEBUG)
            log.info('Debugging enabled...')
        else:
            log.setLevel(logging.INFO)

        if args.evdev:
            from remarkable_mouse.evdev import create_local_device, pipe_device

            try:
                local_device = create_local_device()
                log.info("Created virtual input device '{}'".format(local_device.devnode))
            except PermissionError:
                log.error('Insufficient permissions for creating a virtual input device')
                log.error('Make sure you run this program as root')
                sys.exit(1)

            pipe_device(args, remote_device, local_device)

        else:
            from remarkable_mouse.pynput import read_tablet
            read_tablet(args, remote_device)

    except KeyboardInterrupt:
        pass
    except EOFError:
        pass

if __name__ == '__main__':
    main()
