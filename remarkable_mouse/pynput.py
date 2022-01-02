import logging
import struct
import threading
from screeninfo import get_monitors
from pynput.mouse import Button, Controller
from queue import Empty, LifoQueue

from remarkable_mouse.ft5406 import TouchEvent, Touchscreen, TS_MOVE, TS_PRESS, TS_RELEASE
from datetime import datetime

MONITORS = get_monitors()

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


def read_tablet(rm_inputs, *, orientation, monitor_idx, threshold, mode):
    """Loop forever and map evdev events to mouse

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor (int): monitor number to map to
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    monitor = MONITORS[monitor_idx]
    log.debug('Chose monitor: {}'.format(monitor))
    q = LifoQueue()

    mouse = threading.Thread(target=handle_touch, args=(rm_inputs, orientation, monitor, mode, q))
    gesture = threading.Thread(target=handle_pen, args=(rm_inputs, orientation, monitor, threshold, mode, q))
    mouse.daemon = True
    gesture.daemon = True
    mouse.start()
    gesture.start()
    mouse.join()
    gesture.join()

def clean_queue(q):
    while not q.empty():
        try:
            q.get(False)
        except Empty:
            continue
        q.task_done()


def get_or_none(q):
    msg = None
    try:
        msg = q.get(False)
        q.task_done()
    except Empty:
        pass
    clean_queue(q) # ignore old ones and keep the queue clean
    return msg

def get_current_monitor():
    global every
    mouse = Controller()
    for x, _monitor in enumerate(MONITORS):
        if _monitor.x < mouse.position[0] < _monitor.x+_monitor.width and _monitor.y < mouse.position[1] < -_monitor.y+_monitor.height:
            return _monitor



def handle_touch(rm_inputs, orientation, monitor, mode, q):
    mouse = Controller()
    import signal
    speed = 10
    
    ts = Touchscreen(rm_inputs['touch'].channel, rm_inputs['touch'])

    def handle_event(event, touch, touchscreen: Touchscreen, raw_event: TouchEvent):
        touchscreen.update_timestamp(event)
        fingers = touchscreen.fingers
        from_pen = get_or_none(q) # get the last one
        delta_t = 10 # set high delay in case no message has been recieved


        if from_pen:
            delta_t = raw_event.timestamp-from_pen.timestamp

        if event == TS_PRESS:
            touch.last_x, touch.last_y = touch.position
        
        if 0 < (touch.releasetime - touch.presstime) < 0.2:
            mouse.press(Button.left)
            mouse.release(Button.left)


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

        dx = px-lpx
        dy = py-lpy

        dt = touchscreen.get_delta_time(event)

        if fingers == 2 and delta_t > 1:
            mouse.scroll(dx, dy)

        if fingers == 1 and delta_t > 1:
            mouse.move(speed*dx, speed*dy)

        log.debug(
            f'{["Release","Press","Move"][event]}\t'+
            f'{px}\t{lpx}\t{py}\t{lpy}\t{fingers}\t{touch.slot}\t'+
            f'{dx}\t{dy}\t{dt}\t'
            f'{mouse.position}\t{get_current_monitor()}'
        )




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
    
                
def handle_pen(rm_inputs, orientation, monitor, threshold, mode, q):
    mouse = Controller()
    lifted = True
    new_x = new_y = False

    while True:
        tv_sec, tv_usec, e_type, e_code, e_value = struct.unpack('2IHHi', rm_inputs['pen'].read(16))
        q.put(TouchEvent(tv_sec + (tv_usec / 1000000), e_type, e_code, e_value))

        _monitor = get_current_monitor()
        if _monitor and _monitor != monitor:
            monitor = _monitor

        if e_type == e_type_abs:
            # handle x direction
            if e_code == e_code_stylus_xpos:
                x = e_value
                new_x = True

            # handle y direction
            if e_code == e_code_stylus_ypos:
                y = e_value
                new_y = True

            # handle draw
            if e_code == e_code_stylus_pressure:
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



