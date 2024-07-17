import logging
import struct
import ctypes
import time
from screeninfo import get_monitors

from .codes import codes, types
from .common import get_monitor, remap, wacom_max_x, wacom_max_y, log_event
from ctypes import *
from ctypes.wintypes import *

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')
log.debug('Using pen injection')

# Constants

MAX_ABS_PRESSURE=4095
MAX_WIN_PRESSURE=1024
MAX_ANGLE=90
MAX_ABS_TILT=6300


# For penMask
PEN_MASK_NONE=            0x00000000 # Default
PEN_MASK_PRESSURE=        0x00000001
PEN_MASK_ORIENTATION=     0x00000002
PEN_MASK_TILT_X=          0x00000004
PEN_MASK_TILT_Y=          0x00000008

# For penFlag
PEN_FLAG_NONE=            0x00000000

# For pointerType
PT_POINTER=               0x00000001 # All
PT_TOUCH=                 0x00000002
PT_PEN=                   0x00000003
PT_MOUSE=                 0x00000004

#For pointerFlags
POINTER_FLAG_NONE=        0x00000000 # Default
POINTER_FLAG_NEW=         0x00000001
POINTER_FLAG_INRANGE=     0x00000002
POINTER_FLAG_INCONTACT=   0x00000004
POINTER_FLAG_FIRSTBUTTON= 0x00000010
POINTER_FLAG_SECONDBUTTON=0x00000020
POINTER_FLAG_THIRDBUTTON= 0x00000040
POINTER_FLAG_FOURTHBUTTON=0x00000080
POINTER_FLAG_FIFTHBUTTON= 0x00000100
POINTER_FLAG_PRIMARY=     0x00002000
POINTER_FLAG_CONFIDENCE=  0x00004000
POINTER_FLAG_CANCELED=    0x00008000
POINTER_FLAG_DOWN=        0x00010000
POINTER_FLAG_UPDATE=      0x00020000
POINTER_FLAG_UP=          0x00040000
POINTER_FLAG_WHEEL=       0x00080000
POINTER_FLAG_HWHEEL=      0x00100000
POINTER_FLAG_CAPTURECHANGED=0x00200000

# Structs Needed
class POINTER_INFO(Structure):
    _fields_=[("pointerType",c_uint32),
              ("pointerId",c_uint32),
              ("frameId",c_uint32),
              ("pointerFlags",c_int),
              ("sourceDevice",HANDLE),
              ("hwndTarget",HWND),
              ("ptPixelLocation",POINT),
              ("ptHimetricLocation",POINT),
              ("ptPixelLocationRaw",POINT),
              ("ptHimetricLocationRaw",POINT),
              ("dwTime",DWORD),
              ("historyCount",c_uint32),
              ("inputData",c_int32),
              ("dwKeyStates",DWORD),
              ("PerformanceCount",c_uint64),
              ("ButtonChangeType",c_int)
              ]
              
class POINTER_PEN_INFO(Structure):
    _fields_=[("pointerInfo",POINTER_INFO),
              ("penFlags",c_int),
              ("penMask",c_int),
              ("pressure", c_uint32),
              ("rotation", c_uint32),
              ("tiltX", c_int32),
              ("tiltY", c_int32)]
              
class DUMMYUNIONNAME(Structure):
   _fields_=[("penInfo",POINTER_PEN_INFO)
              ]

class POINTER_TYPE_INFO(Structure):
   _fields_=[("type",c_uint32),
              ("penInfo",POINTER_PEN_INFO)
              ]

# Initialize Pointer and Touch info
pointerInfo = POINTER_INFO(pointerType=PT_PEN,
                            pointerId=0,
                            ptPixelLocation=POINT(950, 540),
                            pointerFlags=POINTER_FLAG_NEW)
penInfo = POINTER_PEN_INFO(pointerInfo=pointerInfo,
                                penMask=(PEN_MASK_PRESSURE | PEN_MASK_TILT_X | PEN_MASK_TILT_Y),
                                pressure=0,
                                tiltX=0,
                                tiltY=0)

pointerTypeInfo = POINTER_TYPE_INFO(type=PT_PEN,
                            penInfo=penInfo)

device = windll.user32.CreateSyntheticPointerDevice(PT_PEN, 1, 1)
print("Initialized Pen Injection as number ", device)
currently_down = False

def applyPen(x=0, y=0, pressure=0, tiltX=0, tiltY=0):
    global currently_down
    if pressure > 0:
        pointerTypeInfo.penInfo.pointerInfo.pointerFlags = (POINTER_FLAG_DOWN if not currently_down else POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT)
        currently_down = True
    else:
        pointerTypeInfo.penInfo.pointerInfo.pointerFlags = (POINTER_FLAG_UP if currently_down else POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE)
        currently_down = False

    pointerTypeInfo.penInfo.pointerInfo.ptPixelLocation.x = x
    pointerTypeInfo.penInfo.pointerInfo.ptPixelLocation.y = y
    pointerTypeInfo.penInfo.pressure = pressure
    pointerTypeInfo.penInfo.tiltX = tiltX
    pointerTypeInfo.penInfo.tiltY = tiltY
    
    result = windll.user32.InjectSyntheticPointerInput(device, byref(pointerTypeInfo), 1)
    if (result == False) and (log.level == logging.DEBUG):
        error_code = ctypes.get_last_error()
        print(f"Failed trying to update pen input. Error code: {error_code}")
        print(f"Error message: {ctypes.WinError(error_code).strerror}")


        
def read_tablet(rm_inputs, *, orientation, monitor_num, region, threshold, mode):
    """Loop forever and map evdev events to mouse

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor_num (int): monitor number to map to
        region (boolean): whether to selection mapping region with region tool
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    monitor, _ = get_monitor(region, monitor_num, orientation)
    log.debug('Chose monitor: {}'.format(monitor))

    x = y = mapped_x = mapped_y = press = mapped_press = tiltX = tiltY = 0

    stream = rm_inputs['pen']

    while True:
        try:
            data = stream.read(16)
        except TimeoutError:
            continue

        e_time, e_millis, e_type, e_code, e_value = struct.unpack('2IHHi', data)

        # handle x direction
        if codes[e_type][e_code] == 'ABS_X':
            x = e_value

        # handle y direction
        if codes[e_type][e_code] == 'ABS_Y':
            y = e_value
            
        # handle pressure
        if codes[e_type][e_code] == 'ABS_PRESSURE':
            press = e_value
            mapped_press = int(press* (MAX_WIN_PRESSURE / MAX_ABS_PRESSURE))
            
        # handle tilt
        if codes[e_type][e_code] == 'ABS_TILT_X':
            tiltX = int(e_value*( MAX_ANGLE / MAX_ABS_TILT ))
            
        if codes[e_type][e_code] == 'ABS_TILT_Y':
            tiltY = int(e_value*( MAX_ANGLE  /MAX_ABS_TILT ))

        if codes[e_type][e_code] == 'SYN_REPORT':
            
            mapped_x, mapped_y = remap(
                x, y,
                wacom_max_x, wacom_max_y,
                monitor.width, monitor.height,
                mode, orientation,
            )
            
            # handle draw
            applyPen(max(int(monitor.x+mapped_x),0), max(int(monitor.y+mapped_y),0), mapped_press, tiltX, tiltY)
            
        if log.level == logging.DEBUG:
            log_event(e_time, e_millis, e_type, e_code, e_value)