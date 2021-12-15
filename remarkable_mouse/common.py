#!/usr/bin/env python

import sys
from screeninfo import get_monitors, Monitor


# get info of where we want to map the tablet to
def get_monitor(args):
    if args.region:
        monitor = get_region(args)
    else:
        monitor = get_monitors()[args.monitor]

    return monitor

# Pop up a window, ask the user to move the window, and then get the position of the window's contents
def get_region(args):
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
        selected_pos = Monitor(
            window.winfo_x(),
            window.winfo_y(),
            window.winfo_width(),
            window.winfo_height(),
            name="Fake monitor from region selection"
        )
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
