import logging
import struct
import sys
from screeninfo import get_monitors, Monitor

logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)

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

# wacom digitizer dimensions
wacom_width = 15725
wacom_height = 20967
# touchscreen dimensions
# finger_width = 767
# finger_height = 1023


# Pop up a window, ask the user to move the window, and then get the position of the window's contents
def ask_user_for_position(args):
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
    selected_pos = None

    def on_click():
        nonlocal selected_pos
        selected_pos = Monitor(window.winfo_x(), window.winfo_y(), window.winfo_width(), window.winfo_height(),
                               name="Fake monitor from rect selection")
        window.destroy()

    confirm = ttk.Button(window, text="Drag and resize this button to the desired mouse range, then click",
                         command=on_click)
    confirm.grid(column=0, row=0, sticky=(tk.N, tk.S, tk.E, tk.W))

    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)

    window.attributes('-alpha', 0.5)
    window.title("Remarkable Mouse")

    if args.orientation == 'bottom' or args.orientation == 'top':
        window.geometry("702x936")
    else:
        window.geometry("936x702")

    window.mainloop()

    if selected_pos is None:
        log.debug("Window closed without giving mouse range")
        sys.exit(1)

    return selected_pos


# get info of where we want to map the tablet to
def get_screen_info(args):
    if args.rect:
        monitor = ask_user_for_position(args)
    else:
        monitor = get_monitors()[args.monitor]

    return monitor


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


def read_tablet(args, remote_device):
    """Loop forever and map evdev events to mouse"""

    from pynput.mouse import Button, Controller

    lifted = True
    new_x = new_y = False

    mouse = Controller()

    monitor = get_screen_info(args)
    log.debug('Chose monitor: {}'.format(monitor))

    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', remote_device.read(16))

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
                    if lifted:
                        log.debug('PRESS')
                        lifted = False
                        mouse.press(Button.left)
                else:
                    if not lifted:
                        log.debug('RELEASE')
                        lifted = True
                        mouse.release(Button.left)


            # only move when x and y are updated for smoother mouse
            if new_x and new_y:
                mapped_x, mapped_y = remap(
                    x, y,
                    wacom_width, wacom_height,
                    monitor.width, monitor.height,
                    args.mode, args.orientation
                )
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )
                new_x = new_y = False
