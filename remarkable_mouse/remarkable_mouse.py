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
import paramiko.config

from .common import reMarkable1, reMarkable2, reMarkablePro

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

default_key = os.path.expanduser('~/.ssh/remarkable')
config_path = os.path.expanduser('~/.ssh/config')


def connect_rm(*, address, key, password):
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

    # lookup "remarkable" in ssh config
    config_entry = {}
    if os.path.exists(config_path):
        config = paramiko.config.SSHConfig.from_path(config_path)
        config_entry = config.lookup('remarkable')

    # open key at provided path
    def use_key(key):
        for key_type in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
            try:
                pkey = key_type.from_private_key_file(os.path.expanduser(key))
                break
            except paramiko.ssh_exception.PasswordRequiredException:
                passphrase = getpass(
                    "Enter passphrase for key '{}': ".format(os.path.expanduser(key))
                )
                # try to read the file again, this time with the password
                for key_type in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
                    try:
                        pkey = key_type.from_private_key_file(os.path.expanduser(key), password=passphrase)
                        break
                    except paramiko.ssh_exception.SSHException:
                        continue
                break
            except paramiko.ssh_exception.SSHException:
                continue
        return pkey

    # use provided key
    if key is not None:
        password = None
        pkey = use_key(key)
    # fallback to "remarkable" entry in ssh config
    elif 'identityfile' in config_entry and len(config_entry['identityfile']) > 0:
        password = None
        pkey = use_key(config_entry['identityfile'][0])
    # fallback to user-provided password
    elif password is not None:
        pkey = None
    # fallback to default pubkey location
    elif os.path.exists(default_key):
        password = None
        pkey = use_key(default_key)
    # finally prompt user for password
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

    # detect reMarkable version
    # https://github.com/Eeems/oxide/issues/48#issuecomment-690830572
    if pen_file == '/dev/input/event0':
        # rM 1
        rm = reMarkable1(client)
    elif pen_file == '/dev/input/event1':
        # rM 2
        rm = reMarkable2(client)
    elif pen_file == '/dev/input/event3' or pen_file == '/dev/input/event2':# keep checking event2 to support software before 3.16
        # rM Pro
        rm = reMarkablePro(client)
    else:
        raise ValueError(f"Could not detect reMarkable version. {pen_file}")

    log.debug(f"Detected {type(rm).__name__}")
    log.debug(f'Pen:{rm.pen_file}\nTouch:{rm.touch_file}\nButton:{rm.button_file}')

    return rm

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

        rm = connect_rm(
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
            rm,
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
