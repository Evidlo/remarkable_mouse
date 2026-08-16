import logging
import struct
from socket import timeout as TimeoutError

from .codes import codes, types
from .common import get_monitor, remap, wacom_max_x, wacom_max_y, log_event
from ctypes import *
from ctypes.wintypes import *

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

# Constants

# Source: https://learn.microsoft.com/en-us/windows/win32/inputmsg/wmpointer-reference

# Max values for linux / windows 
MAX_ABS_PRESSURE=4095
MAX_WIN_PRESSURE=1024
MAX_ANGLE=90
MAX_ABS_TILT=6300

# Windows tilt appears flipped from remarkable event
# Tested with https://patrickhlauke.github.io/touch/pen-tracker/
WINDOWS_TILT_SIGN = -1

# For penMask
PEN_MASK_NONE=            0x00000000 # Default
PEN_MASK_PRESSURE=        0x00000001
PEN_MASK_TILT_X=          0x00000004
PEN_MASK_TILT_Y=          0x00000008

# For penFlag
PEN_FLAG_NONE=            0x00000000

# For pointerType
PT_POINTER=               0x00000001 # All
PT_PEN=                   0x00000003

#For pointerFlags
POINTER_FLAG_NONE=        0x00000000 # Default
POINTER_FLAG_NEW=         0x00000001
POINTER_FLAG_INRANGE=     0x00000002
POINTER_FLAG_INCONTACT=   0x00000004
POINTER_FLAG_DOWN=        0x00010000
POINTER_FLAG_UPDATE=      0x00020000
POINTER_FLAG_UP=          0x00040000

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
              ("ButtonChangeType",c_int)]
              
class POINTER_PEN_INFO(Structure):
    _fields_=[("pointerInfo",POINTER_INFO),
              ("penFlags",c_int),
              ("penMask",c_int),
              ("pressure", c_uint32),
              ("rotation", c_uint32),
              ("tiltX", c_int32),
              ("tiltY", c_int32)]

class POINTER_TYPE_INFO(Structure):
   _fields_=[("type",c_uint32),
              ("penInfo",POINTER_PEN_INFO)]
   
class WindowsPenDevice:
    def __init__(self):
        # Initialize Pointer and Touch info
        self.pointer_info = POINTER_INFO(pointerType=PT_PEN,
                                    pointerId=0,
                                    ptPixelLocation=POINT(950, 540),
                                    pointerFlags=POINTER_FLAG_NEW)
        
        self.pen_info = POINTER_PEN_INFO(pointerInfo=self.pointer_info,
                                        penMask=(PEN_MASK_PRESSURE | PEN_MASK_TILT_X | PEN_MASK_TILT_Y),
                                        pressure=0,
                                        tiltX=0,
                                        tiltY=0)

        self.pointer_type_info = POINTER_TYPE_INFO(type=PT_PEN,
                                    penInfo=self.pen_info)
        
        self.device_handle = windll.user32.CreateSyntheticPointerDevice(PT_PEN, 1, 1)
        self.currently_down = False
        
    def send_pen_event(self, x=0, y=0, pressure=0, tilt_x=0, tilt_y=0):
        if pressure > 0:
            self.pointer_type_info.penInfo.pointerInfo.pointerFlags = (POINTER_FLAG_DOWN if not self.currently_down else POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT)
            self.currently_down = True
        else:
            self.pointer_type_info.penInfo.pointerInfo.pointerFlags = (POINTER_FLAG_UP if self.currently_down==True else POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE)
            self.currently_down = False

        self.pointer_type_info.penInfo.pointerInfo.ptPixelLocation.x = x
        self.pointer_type_info.penInfo.pointerInfo.ptPixelLocation.y = y
        self.pointer_type_info.penInfo.pressure = pressure
        self.pointer_type_info.penInfo.tiltX = tilt_x
        self.pointer_type_info.penInfo.tiltY = tilt_y
        
        result = windll.user32.InjectSyntheticPointerInput(self.device_handle, byref(self.pointer_type_info), 1)
        if (result == False) and (log.level == logging.DEBUG):
            error_code = ctypes.get_last_error()
            log.error("Failed trying to update pen input. Error code: '{}'".format(error_code))
            log.error("Error message: '{}'".format(ctypes.WinError(error_code).strerror))

def read_tablet(rm_inputs, *, orientation, monitor_num, region, threshold, mode):
    """Loop forever and map windows pen input events to mouse

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen, button
            and touch input streams
        orientation (str): tablet orientation
        monitor_num (int): monitor number to map to
        region (boolean): whether to selection mapping region with region tool
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    local_device = WindowsPenDevice()
    log.debug("Created virtual input device '{}'".format(local_device.device_handle))

    monitor, (tot_width, tot_height) = get_monitor(region, monitor_num, orientation)

    x = y = mapped_x = mapped_y = press = mapped_press = tilt_x = tilt_y = 0

    stream = rm_inputs['pen']

    while True:
        try:
            data = stream.read(16)
        except TimeoutError:
            continue

        e_time, e_millis, e_type, e_code, e_value = struct.unpack('2IHHi', data)

        if log.level == logging.DEBUG:
            log_event(e_time, e_millis, e_type, e_code, e_value)

        # handle x direction
        if codes[e_type][e_code] == 'ABS_X':
            x = e_value

        # handle y direction
        if codes[e_type][e_code] == 'ABS_Y':
            y = e_value
            
        # handle pressure
        if codes[e_type][e_code] == 'ABS_PRESSURE':
            press = e_value
            mapped_press = int(press * (MAX_WIN_PRESSURE / MAX_ABS_PRESSURE))
            
        # handle tilt
        if codes[e_type][e_code] == 'ABS_TILT_X':
            tilt_x = WINDOWS_TILT_SIGN * int(e_value * ( MAX_ANGLE / MAX_ABS_TILT ))
            
        if codes[e_type][e_code] == 'ABS_TILT_Y':
            tilt_y = WINDOWS_TILT_SIGN * int(e_value * ( MAX_ANGLE  / MAX_ABS_TILT ))

        if codes[e_type][e_code] == 'SYN_REPORT':
            
            mapped_x, mapped_y = remap(
                x, y,
                wacom_max_x, wacom_max_y,
                monitor.width, monitor.height,
                mode, orientation,
            )

            mapped_x += monitor.x
            mapped_y += monitor.y
            
            # handle draw
            local_device.send_pen_event(int(mapped_x), int(mapped_y), mapped_press, tilt_x, tilt_y)