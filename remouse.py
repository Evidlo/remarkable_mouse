import paramiko
import paramiko.agent
from screeninfo import get_monitors
from pynput.mouse import Button, Controller
import struct

# ----- Settings -----

password = ''
assert password, "Set your password in remouse.py"

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

e_type_abs = 3
e_code_stylus_xpos = 1
e_code_stylus_ypos = 0
e_code_stylus_pressure = 24
wacom_width = 15725
wacom_height = 20967

lifted = True
new_x = new_y = False

mouse = Controller()

monitor = get_monitors()[monitor_num]

while True:
    # read one evdev event at a time
    _, _, e_type, e_code, e_value = struct.unpack('2IHHi', stdout.read(16))

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
                    lifted = False
                    mouse.press(Button.left)
            else:
                if not lifted:
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
