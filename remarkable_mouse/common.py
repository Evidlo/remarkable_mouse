#!/usr/bin/env python

from collections import namedtuple
import logging
import sys
from screeninfo import get_monitors, Monitor

from .codes import codes, types

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

# ev settings
ev = namedtuple('ev_setting', ['min', 'max', 'res'])

class reMarkable1:
    """Class holding some input settings for a reMarkable tablet

    Args:
        client (Paramiko SSH client, optional): an active SSH connection to the
            device for reading pen/touch/button inputs
    """

    r"""Coordinate systems

        PEN          TOUCH
    +---------+   +---------+
    | X       |   |       Y |
    | |       |   |       | |
    | |       |   |       | |
    | +--- Y  |   |  X ---+ |
    |         |   |         |
    |---------|   |---------|
    | USB PORT|   | USB PORT|
    +---------+   +---------+
    """

    # evdev input file
    pen_file = '/dev/input/event0'
    touch_file = '/dev/input/event2'
    button_file = '/dev/input/event1'

    # stylus evdev settings (min, max, resolution)
    touch_x = ev(0, 20967, 100) # touchscreen X coordinate (ABS_MT_POSITION_X)
    touch_y = ev(0, 15725, 100) # touchscreen Y coordinate (ABS_MT_POSITION_Y)
    touch_pressure = ev(0, 4095, None) # touchscreen pressure (ABS_MT_PRESSURE)
    touch_major = ev(0, 255, None) # touch area major axis (ABS_MT_TOUCH_MAJOR)
    touch_minor = ev(0, 255, None) # touch area minor axis (ABS_MT_TOUCH_MINOR)
    touch_orient = ev(-127, 127, None) # touch orientation (ABS_MT_ORIENTATION)
    touch_slot = ev(0, 31, None) # tool slot ID (ABS_MT_SLOT)
    touch_tool = ev(0, 1, None) # tool type (ABS_MT_TOOL_TYPE)
    touch_trackid = ev(0, 65535, None) # tool tracking id (ABS_MT_TRACKING_ID)

    # pen evdev settings (min, max, resolution)
    pen_x = ev(0, 20967, 100) # pen X coordinate (ABS_X)
    pen_y = ev(0, 15725, 100) # pen Y coordinate (ABS_Y)
    pen_pressure = ev(0, 4095, None) # pen pressure (ABS_PRESSURE)
    pen_distance = ev(0, 255, None) # pen distance from screen (ABS_DISTANCE)
    pen_tilt_x = ev(-6400, 6400, 6400) # pen tilt angle (ABS_TILT_X)
    pen_tilt_y = ev(-6400, 6400, 6400) # pen tilt angle (ABS_TILT_Y)

    def __init__(self, client=None):
        self.client = client

    @property
    def pen(self):
        """(paramiko.ChannelFile) pen stream"""
        cmd = f'dd bs=16 if={self.pen_file}'
        return self.client.exec_command(cmd, bufsize=16, timeout=0)[1]

    @property
    def touch(self):
        """(paramiko.ChannelFile) touch stream"""
        cmd = f'dd bs=16 if={self.touch_file}'
        return self.client.exec_command(cmd, bufsize=16, timeout=0)[1]

    @property
    def button(self):
        """(paramiko.ChannelFile) button stream"""
        cmd = f'dd bs=16 if={self.button_file}'
        return self.client.exec_command(cmd, bufsize=16, timeout=0)[1]

class reMarkable2(reMarkable1):
    pen_file = '/dev/input/event1'
    touch_file = '/dev/input/event2'
    button_file = '/dev/input/event0'

class reMarkablePro(reMarkable1):
    pen_file = '/dev/input/event2'
    touch_file = '/dev/input/event3'
    button_file = '/dev/input/event0'
    # stylus evdev settings (min, max, resolution)
    touch_x = ev(0, 2064, 2064) # touchscreen X coordinate (ABS_MT_POSITION_X)
    touch_y = ev(0, 2832, 2832) # touchscreen Y coordinate (ABS_MT_POSITION_Y)
    touch_pressure = ev(0, 255, None) # touchscreen pressure (ABS_MT_PRESSURE)
    touch_orient = ev(-127, 127, None) # touch orientation (ABS_MT_ORIENTATION)
    touch_slot = ev(0, 9, None) # tool slot ID (ABS_MT_SLOT)
    touch_tool = ev(0, 2, None) # tool type (ABS_MT_TOOL_TYPE)


def get_monitor(region, monitor_num, orientation):
    """ Get info of where we want to map the tablet to

    Args:
        region (boolean): whether to prompt the user to select a region
        monitor_num (int): index of monitor to use.  Implies region=False
        orientation (str): Location of tablet charging port.
            ('top', 'bottom', 'left', 'right')

    Returns:
        screeninfo.Monitor
        (width, height): total size of all screens put together
    """

    # compute size of box encompassing all screens
    max_x, max_y = 0, 0
    for m in get_monitors():
        x = m.x + m.width
        y = m.y + m.height
        max_x = max(x, max_x)
        max_y = max(y, max_y)

    if region:
        x, y, width, height = get_region(orientation)
        monitor = Monitor(
            x, y, width, height,
            name="Fake monitor from region selection"
        )
    else:
        try:
            monitor = get_monitors()[monitor_num]
        except IndexError:
            log.error(f"Monitor {monitor_num} not found.  Only {len(get_monitors())} detected.")

    log.debug(f"Chose monitor: {monitor}")
    log.debug(f"Screen size: ({max_x}, {max_y})")
    return monitor, (max_x, max_y)

def get_region(orientation):
    """ Show tkwindow to user to select mouse bounds

    Args:
        orientation (str): Location of tablet charging port.
            ('top', 'bottom', 'left', 'right')

    Returns:
        x (int), y (int), width (int), height (int)
    """

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print(
            "Unable to import tkinter; please follow the instructions at https://tkdocs.com/tutorial/install.html to install it")
        sys.exit(1)

    window = tk.Tk()

    # A bit of an ugly hack to get this function to run synchronously
    # Ideally would use full async support, but this solution required minimal changes to rest of code
    window_bounds = None

    def on_click():
        nonlocal window_bounds
        window_bounds = (
            window.winfo_x(), window.winfo_y(),
            window.winfo_width(), window.winfo_height()
        )
        window.destroy()

    confirm = ttk.Button(
        window,
        text="Resize and move this window, then click or press Enter",
        command=on_click
    )
    confirm.grid(column=0, row=0, sticky=(tk.N, tk.S, tk.E, tk.W))

    window.bind('<Return>', lambda _: on_click())

    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)

    window.attributes('-alpha', 0.5)
    window.title("Remarkable Mouse")

    if orientation == 'bottom' or orientation == 'top':
        window.geometry("702x936")
    else:
        window.geometry("936x702")

    # block here
    window.mainloop()

    if window_bounds is None:
        log.debug("Window closed without giving mouse range")
        sys.exit(1)

    return window_bounds


# remap wacom coordinates to screen coordinates
def remap(x, y, pen_max_x, pen_max_y, monitor_width,
          monitor_height, mode, orientation):

    if orientation == 'right':
        x, y = pen_max_x - x, pen_max_y - y
    if orientation == 'left':
        pass
    if orientation == 'top':
       x, y = pen_max_y - y, x
       pen_max_x, pen_max_y = pen_max_y, pen_max_x
    if orientation == 'bottom':
       x, y = y, pen_max_x - x
       pen_max_x, pen_max_y = pen_max_y, pen_max_x

    ratio_width, ratio_height = monitor_width / pen_max_x, monitor_height / pen_max_y

    if mode == 'fill':
        scaling_x = max(ratio_width, ratio_height)
        scaling_y = scaling_x
    elif mode == 'fit':
        scaling_x = min(ratio_width, ratio_height)
        scaling_y = scaling_x
    elif mode == 'stretch':
        scaling_x = ratio_width
        scaling_y = ratio_height
    else:
        raise NotImplementedError

    return (
        scaling_x * (x - (pen_max_x - monitor_width / scaling_x) / 2),
        scaling_y * (y - (pen_max_y - monitor_height / scaling_y) / 2)
    )

# log evdev event to console
def log_event(e_time, e_millis, e_type, e_code, e_value):
    log.debug('{}.{:0>6} - {: <9} {: <15} {: >6}'.format(
        e_time,
        e_millis,
        types[e_type],
        codes[e_type][e_code],
        e_value
    ))
