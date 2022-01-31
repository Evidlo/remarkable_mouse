# Evan Widloski - 2019-02-23
# Use reMarkable as mouse input

import argparse
import logging
import os
import sys
import struct
from getpass import getpass
from itertools import cycle

import paramiko
import paramiko.agent

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

default_key = os.path.expanduser('~/.ssh/remarkable')


def open_rm_inputs(*, address, key, password):
    """
    Open a remote input device via SSH.

    Args:
        address (str): address to reMarkable
        key (str, optional): path to reMarkable ssh key
        password (str, optional): reMarkable ssh password
    Returns:
        (paramiko.ChannelFile): read-only stream of pen events
        (paramiko.ChannelFile): read-only stream of touch events
        (paramiko.ChannelFile): read-only stream of button events
    """
    log.debug("Connecting to input '{}'".format(address))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = None

    agent = paramiko.agent.Agent()

    def use_key(key):
        for key_type in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
            try:
                pkey = key_type.from_private_key_file(os.path.expanduser(key))
            except paramiko.ssh_exception.SSHException:
                continue
            except paramiko.ssh_exception.PasswordRequiredException:
                passphrase = getpass(
                    "Enter passphrase for key '{}': ".format(os.path.expanduser(key))
                )
                pkey = paramiko.RSAKey.from_private_key_file(
                    os.path.expanduser(key), password=passphrase
                )
                break
        return pkey

    if key is not None:
        password = None
        pkey = use_key(key)
    elif os.path.exists(default_key):
        password = None
        pkey = use_key(default_key)
    elif password is not None:
        pkey = None
    elif not agent.get_keys():
        password = getpass(
            "Password for '{}': ".format(address)
        )
        pkey = None

    client.connect(
        address,
        username='root',
        password=password,
        pkey=pkey,
        look_for_keys=False,
        disabled_algorithms=dict(pubkeys=["rsa-sha2-512", "rsa-sha2-256"])
    )

    session = client.get_transport().open_session()

    paramiko.agent.AgentRequestHandler(session)

    pen_file = client.exec_command(
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
    pen = client.exec_command('cat ' + pen_file)[1]
    touch = client.exec_command('cat ' + touch_file)[1]
    button = client.exec_command('cat ' + button_file)[1]

    return {'pen': pen, 'touch': touch, 'button': button}


def main():
    try:
        parser = argparse.ArgumentParser(description="use reMarkable tablet as a mouse input")
        parser.add_argument('--debug', action='store_true', default=False, help="enable debug messages")
        parser.add_argument('--key', type=str, metavar='PATH', help="ssh private key")
        parser.add_argument('--password', default=None, type=str, help="ssh password")
        parser.add_argument('--address', default='10.11.99.1', type=str, help="device address")
        parser.add_argument('--mode', default='fill', choices=['fit', 'fill', 'stretch'], help="""Scale setting.
        Fit (default): take up the entire tablet, but not necessarily the entire monitor.
        Fill: take up the entire monitor, but not necessarily the entire tablet.
        Stretch: take up both the entire tablet and monitor, but don't maintain aspect ratio.""")
        parser.add_argument('--orientation', default='right', choices=['top', 'left', 'right', 'bottom'], help="position of tablet buttons")
        parser.add_argument('--monitor', default=0, type=int, metavar='NUM', help="monitor to output to")
        parser.add_argument('--region', action='store_true', default=False, help="Use a GUI to position the output area. Overrides --monitor")
        parser.add_argument('--threshold', metavar='THRESH', default=600, type=int, help="stylus pressure threshold (default 600)")
        parser.add_argument('--evdev', action='store_true', default=False, help="use evdev to support pen pressure (requires root, Linux only)")

        args = parser.parse_args()

        if args.debug:
            log.setLevel(logging.DEBUG)
            print('Debugging enabled...')
        else:
            log.setLevel(logging.INFO)

        # ----- Connect to device -----

        rm_inputs = open_rm_inputs(
            address=args.address,
            key=args.key,
            password=args.password,
        )
        print("Connected to", args.address)

        # ----- Handle events -----

        if args.evdev:
            from remarkable_mouse.evdev import read_tablet

        else:
            from remarkable_mouse.pynput import read_tablet

        read_tablet(
            rm_inputs,
            orientation=args.orientation,
            monitor_num=args.monitor,
            region=args.region,
            threshold=args.threshold,
            mode=args.mode,
        )

    except PermissionError:
        log.error('Insufficient permissions for creating a virtual input device')
        log.error('Make sure you run this program as root')
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    except EOFError:
        pass

if __name__ == '__main__':
    main()
