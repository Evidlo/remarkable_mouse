# Evan Widloski - 2019-02-23
# Use reMarkable as mouse input

import argparse
import logging
import os
import sys
import struct
from getpass import getpass

import paramiko
import paramiko.agent

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')


def open_rm_inputs(args):
    """
    Open a remote input device via SSH.

    Args:
        args: argparse arguments
        file (str): path to the input device on the device
    Returns:
        (paramiko.ChannelFile): read-only stream of pen events
        (paramiko.ChannelFile): read-only stream of touch events
        (paramiko.ChannelFile): read-only stream of button events
    """
    log.debug("Connecting to input '{}'".format(args.address))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = None
    password = None

    agent = paramiko.agent.Agent()

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
    elif not agent.get_keys():
        password = getpass(
            "Password for '{}': ".format(args.address)
        )
        pkey = None

    client.connect(
        args.address,
        username='root',
        password=password,
        pkey=pkey,
        look_for_keys=False
    )

    session = client.get_transport().open_session()

    paramiko.agent.AgentRequestHandler(session)

    pen_file =client.exec_command(
        'readlink -f /dev/input/touchscreen0'
    )[1].read().decode('utf8').rstrip('\n')

    # handle both reMarkable versions
    # https://github.com/Eeems/oxide/issues/48#issuecomment-690830572
    if pen_file == '/dev/input/event0':
        # rM 1
        touch_file = '/dev/input/event1'
        button_file = '/dev/input/event2'
    else:
        # rM 2
        touch_file = '/dev/input/event2'
        button_file = '/dev/input/event0'

    log.debug('Pen:{}\nTouch:{}\nButton:{}'.format(pen_file, touch_file, button_file))

    # Start reading events
    pen = client.exec_command('dd bs=16 if=' + pen_file, bufsize=16, timeout=0)[1]
    touch = client.exec_command('dd bs=16 if=' + touch_file, bufsize=16, timeout=0)[1]
    button = client.exec_command('dd bs=16 if=' + button_file, bufsize=16, timeout=0)[1]
    # Skip to next input if no data available
    # pen.channel.setblocking(0)
    # touch.channel.setblocking(0)
    # button.channel.setblocking(0)

    print("Connected to", args.address)

    return pen, touch, button


def main():
    try:
        parser = argparse.ArgumentParser(description="use reMarkable tablet as a mouse input")
        parser.add_argument('--debug', action='store_true', default=False, help="enable debug messages")
        parser.add_argument('--key', type=str, metavar='PATH', help="ssh private key")
        parser.add_argument('--password', default=None, type=str, help="ssh password")
        parser.add_argument('--address', default='10.11.99.1', type=str, help="device address")
        parser.add_argument('--mode', default='fill', choices=['fit', 'fill'], help="scale setting")
        parser.add_argument('--orientation', default='right', choices=['top', 'left', 'right', 'bottom'], help="position of tablet buttons")
        parser.add_argument('--monitor', default=0, type=int, metavar='NUM', help="monitor to output to")
        parser.add_argument('--threshold', metavar='THRESH', default=600, type=int, help="stylus pressure threshold (default 600)")
        parser.add_argument('--evdev', action='store_true', default=False, help="use evdev to support pen pressure (requires root, Linux only)")

        args = parser.parse_args()

        if args.debug:
            log.setLevel(logging.DEBUG)
            print('Debugging enabled...')
        else:
            log.setLevel(logging.INFO)

        rm_inputs = open_rm_inputs(args)

        if args.evdev:
            from remarkable_mouse.evdev import create_local_device, configure_xinput, read_tablet

            try:
                local_device = create_local_device()
                log.info("Created virtual input device '{}'".format(local_device.devnode))
            except PermissionError:
                log.error('Insufficient permissions for creating a virtual input device')
                log.error('Make sure you run this program as root')
                sys.exit(1)

            configure_xinput(args)
            read_tablet(args, rm_inputs, local_device)

        else:
            from remarkable_mouse.pynput import read_tablet
            read_tablet(args, rm_inputs)

    except KeyboardInterrupt:
        pass
    except EOFError:
        pass

if __name__ == '__main__':
    main()
