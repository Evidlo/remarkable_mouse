import logging
import struct

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

stylus_width = 15725
stylus_height = 20951
# finger_width = 767
# finger_height = 1023


# remap wacom coordinates in various orientations
def fit(x, y, stylus_width, stylus_height, monitor, orientation):

    if orientation == "vertical":
        y = stylus_height - y
    elif orientation == "right":
        x, y = y, x
        stylus_width, stylus_height = stylus_height, stylus_width
    elif orientation == "left":
        x, y = stylus_height - y, stylus_width - x
        stylus_width, stylus_height = stylus_height, stylus_width

    ratio_width, ratio_height = (
        monitor.width / stylus_width,
        monitor.height / stylus_height,
    )
    scaling = ratio_width if ratio_width > ratio_height else ratio_height

    return (
        scaling * (x - (stylus_width - monitor.width / scaling) / 2),
        scaling * (y - (stylus_height - monitor.height / scaling) / 2),
    )


def get_monitor(monitor_number):
    from screeninfo import get_monitors, Monitor
    import sys

    if sys.platform == "darwin":
        from AppKit import NSScreen

    for s in NSScreen.screens():
        if sys.platform == "darwin":
            screens = [
                (
                    s.frame().origin.x,
                    s.frame().origin.y,
                    s.frame().size.width,
                    s.frame().size.height,
                )
                for s in NSScreen.screens()
            ]

            monitor = Monitor(
                x=screens[monitor_number][0],
                y=screens[monitor_number][1],
                width=screens[monitor_number][2],
                height=screens[monitor_number][3],
            )
        else:
            monitor = get_monitors()[args.monitor]

    return monitor


def read_tablet(args, remote_device):
    """Loop forever and map evdev events to mouse"""

    from pynput.mouse import Button, Controller

    lifted = True
    new_x = new_y = False

    mouse = Controller()

    monitor = get_monitor(args.monitor)
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
                mapped_x, mapped_y = fit(x, y, stylus_width, stylus_height, monitor, args.orientation)
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )
                new_x = new_y = False
