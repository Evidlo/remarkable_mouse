#!/usr/bin/env python

import logging
import sys
from screeninfo import get_monitors, Monitor

from .codes import codes, types

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

wacom_width = 15725
wacom_height = 20967

def get_monitor(region, monitor_num, orientation):
    """ Get info of where we want to map the tablet to

    Args:
        region (boolean): whether to prompt the user to select a region
        monitor_num (int): index of monitor to use.  Implies region=False
        orientation (str): Location of tablet charging port.
            ('top', 'bottom', 'left', 'right')

    Returns:
        screeninfo.Monitor
    """

    if region:
        x, y, width, height = get_region(orientation)
        monitor = Monitor(
            x, y, width, height,
            name="Fake monitor from region selection"
        )
    else:
        monitor = get_monitors()[monitor_num]

    return monitor

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
def remap(x, y, wacom_width, wacom_height, monitor_width,
          monitor_height, mode, orientation):

    if orientation == 'bottom':
        y = wacom_height - y
    elif orientation == 'right':
        x, y = wacom_height - y, wacom_width - x
        wacom_width, wacom_height = wacom_height, wacom_width
    elif orientation == 'left':
        x, y = y, x
        wacom_width, wacom_height = wacom_height, wacom_width
    elif orientation == 'top':
        x = wacom_width - x

    ratio_width, ratio_height = monitor_width / wacom_width, monitor_height / wacom_height

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
        scaling_x * (x - (wacom_width - monitor_width / scaling_x) / 2),
        scaling_y * (y - (wacom_height - monitor_height / scaling_y) / 2)
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
