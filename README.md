# remarkable_mouse

Use your reMarkable as a graphics tablet.

Special thanks to [canselcik](https://github.com/canselcik/libremarkable) and [LinusCDE](https://github.com/LinusCDE/rmWacomToMouse) for inspiration.

<img src="photo.gif" width=800>

# Quick Start

On the host machine with the tablet plugged in via USB:

``` bash
pip install remarkable-mouse
remouse
```

By default, `10.11.99.1` is used as the address.  Find your password in the reMarkable's [settings menu](https://remarkablewiki.com/tech/ssh).  If you are on Linux using X11, you can use the `--evdev` option for pressure support.

To use the `--region` flag, you may need to install the `python3-tk` or `python3-tkinter` package with your package manager.

# Examples

specify monitor, orientation, password

``` bash
remouse --orientation right --mode fit --monitor 1 --password foobar
```

passwordless login

``` bash
ssh-keygen -m PEM -t rsa -f ~/.ssh/remarkable -N ''
ssh-copy-id -i ~/.ssh/remarkable.pub root@10.11.99.1
remouse
```

running with pressure sensitivity (Linux only)

``` bash
sudo --preserve-env=USER,PATH env remouse --evdev
```

# Usage

```
usage: remouse [-h] [--debug] [--key PATH] [--password PASSWORD] [--address ADDRESS] [--mode {fit,fill,stretch}] [--orientation {top,left,right,bottom}] [--monitor NUM] [--region] [--threshold THRESH]
               [--evdev]

use reMarkable tablet as a mouse input

optional arguments:
  -h, --help            show this help message and exit
  --debug               enable debug messages
  --key PATH            ssh private key
  --password PASSWORD   ssh password
  --address ADDRESS     device address
  --mode {fit,fill,stretch}
                        Scale setting. Fit (default): take up the entire tablet, but not necessarily the entire monitor. Fill: take up the entire monitor, but not necessarily the entire tablet. Stretch:
                        take up both the entire tablet and monitor, but don't maintain aspect ratio.
  --orientation {top,left,right,bottom}
                        position of tablet buttons
  --monitor NUM         monitor to output to
  --region              Use a GUI to position the output area. Overrides --monitor
  --threshold THRESH    stylus pressure threshold (default 600)
  --evdev               use evdev to support pen pressure (requires root, Linux only)
```

