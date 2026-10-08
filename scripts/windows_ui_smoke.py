"""Create every Windows desktop view without the actual hardware."""
import tkinter as tk
from unittest.mock import patch
from nexvary_usim_lab.discovery import Inventory
from nexvary_usim_lab.gui import Workstation

def empty():
    return Inventory("NOT_DETECTED",[],[],"No device in headless test","OK")

with patch("nexvary_usim_lab.gui.detect",empty):
    root=tk.Tk()
    root.withdraw()
    ui=Workstation(root)
    root.update()
    for page in ("devices","sim","sms","reports","about"):
        ui.show(page)
        root.update()
    root.destroy()
print("GUI smoke: all five pages created and opened")
