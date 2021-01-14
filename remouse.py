import paramiko
import paramiko.agent
from screeninfo import get_monitors
from pynput.mouse import Button, Controller
import struct
import sys

# run script w/ line_profiler
#     kernprof -l remouse.py password
# view line profiler results
#     python -m line_profiler remouse.py.lprof

# ----- Settings -----

password = sys.argv[1]
assert password, "provide password as first argument"

# rm1
inputfile = '/dev/input/event0'
# rm2
# inputfile = '/dev/input/event1'

monitor_num = 0

# pynput settings
threshold = 600
orientation = 'right'
mode = 'fill'

# ----- Establish SSH -----

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

agent = paramiko.agent.Agent()

client.connect(
    '10.11.99.1',
    username='root',
    password=password,
    look_for_keys=False
)

session = client.get_transport().open_session()

paramiko.agent.AgentRequestHandler(session)

# Start reading events
_, stdout, _ = client.exec_command('cat ' + inputfile)
print("connected")

# ----- screen mapping function -----

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

# ----- pynput loop -----

e_type_sync = 0
e_type_key = 1
e_type_abs = 3
e_code_stylus_xpos = 1
e_code_stylus_ypos = 0
e_code_stylus_pressure = 24
e_code_touch = 330
wacom_width = 15725
wacom_height = 20967

x = y = 0
mouse = Controller()
monitor = get_monitors()[monitor_num]
event_log = []

@profile
def loop():
    global event_log
    while True:
        # read one evdev event at a time
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', stdout.read(16))

        # if sync event, process all previously logged events
        if e_type == e_type_sync:
            for log_type, log_code, log_value in event_log:

                # handle stylus coordinates
                if log_type == e_type_abs:
                    if log_code == e_code_stylus_xpos:
                        x = log_value
                    if log_code == e_code_stylus_ypos:
                        y = log_value
                # handle stylus press/release
                if log_type == e_type_key:
                    if log_code == e_code_touch:
                        if log_value == 1:
                            mouse.press(Button.left)
                        else:
                            mouse.release(Button.left)

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
            event_log = []
        # otherwise, log the event
        else:
            event_log.append((e_type, e_code, e_value))

loop()
