import logging
import struct
import threading
from screeninfo import get_monitors
from pynput.mouse import Button, Controller

from remarkable_mouse.ft5406 import Touchscreen, TS_MOVE, TS_PRESS, TS_RELEASE


logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

# see https://github.com/canselcik/libremarkable/blob/master/src/input/ecodes.rs

# evtype_sync = 0
# evtype_key = 1
e_type_abs = 3

# evcode_stylus_distance = 25
# evcode_stylus_xtilt = 26
# evcode_stylus_ytilt = 27
e_code_stylus_xpos = 1
e_code_stylus_ypos = 0
e_code_stylus_pressure = 24
evcode_finger_xpos = 53
evcode_finger_ypos = 54
evcode_finger_pressure = 58 
evcode_finger_count = 57  

# wacom digitizer dimensions
wacom_width = 15725
wacom_height = 20967
# touchscreen dimensions
# finger_width = 767
# finger_height = 1023


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
        scaling = max(ratio_width, ratio_height)
    elif mode == 'fit':
        scaling = min(ratio_width, ratio_height)
    else:
        raise NotImplementedError

    return (
        scaling * (x - (wacom_width - monitor_width / scaling) / 2),
        scaling * (y - (wacom_height - monitor_height / scaling) / 2)
    )


def read_tablet(rm_inputs, *, orientation, monitor, threshold, mode):
    """Loop forever and map evdev events to mouse

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor (int): monitor number to map to
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    monitor = get_monitors()[monitor]
    log.debug('Chose monitor: {}'.format(monitor))

    mouse = threading.Thread(target=move_mouse, args=(rm_inputs, orientation, monitor, threshold, mode))
    gesture = threading.Thread(target=do_gesture, args=(rm_inputs, orientation, monitor, threshold, mode))
    mouse.daemon = True
    gesture.daemon = True
    mouse.start()
    gesture.start()
    mouse.join()
    gesture.join()

def do_gesture(rm_inputs, orientation, monitor, threshold, mode):
    mouse = Controller()
    import signal

    ts = Touchscreen("pt_mt", rm_inputs['touch'].channel, rm_inputs['touch'])

    def handle_event(event, touch, fingers):
        px, py = remap(
                *touch.position,
                wacom_width, wacom_height,
                monitor.width, monitor.height,
                mode, orientation
            )
        lpx, lpy = remap(
                *touch.last_position,
                wacom_width, wacom_height,
                monitor.width, monitor.height,
                mode, orientation
            )

        if touch.slot == 0 and fingers == 2:
            mouse.scroll(px-lpx, py-lpy)

    for touch in ts.touches:
        touch.on_press = handle_event
        touch.on_release = handle_event
        touch.on_move = handle_event

    ts.run()

    try:
        signal.pause()
    except KeyboardInterrupt:
        print("Stopping thread...")
        ts.stop()
        exit()
    
                

def move_mouse(rm_inputs, orientation, monitor, threshold, mode):
    lifted = True
    new_x = new_y = False

    mouse = Controller()

    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', rm_inputs['pen'].read(16))
        log.debug(f'PEN: {e_type:02x} {e_code:02x} {e_value:02x} \t###\t {e_type} {e_code} {e_value}')

        if e_type == e_type_abs:
            # handle x direction
            if e_code == e_code_stylus_xpos:
                #log.debug(e_value)
                x = e_value
                new_x = True

            # handle y direction
            if e_code == e_code_stylus_ypos:
                #log.debug('\t{}'.format(e_value))
                y = e_value
                new_y = True

            # handle draw
            if e_code == e_code_stylus_pressure:
                #log.debug('\t\t{}'.format(e_value))
                if e_value > threshold:
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
                    mode, orientation
                )
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )
                new_x = new_y = False



