#!/usr/bin/env python

# Generate file of evdev codes from libevdev that is importable on OSX/Windows.
# Only runs on Linux.

import libevdev

with open('codes.py' , 'w') as f:
    for t in libevdev.types:
        f.write(f'\n\n{t.name} = {t.value}\n')
        for c in t.codes:
            f.write(f'{c.name} = {c.value}\n')
