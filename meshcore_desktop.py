"""MeshCore Desktop - entry point. Run with:  pythonw meshcore_desktop.py"""
import socket
import sys
import tkinter as tk
from tkinter import messagebox

SINGLE_INSTANCE_PORT = 47653   # a bound localhost port doubles as a single-instance lock


def main():
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
    except OSError:
        from mcd.core import APP_NAME, load_config
        from mcd.i18n import T
        load_config()
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(APP_NAME, T("Aplikacja jest już uruchomiona (urządzenie obsługuje jedno połączenie naraz)."))
        return 1
    from mcd.ui import App
    root = tk.Tk()
    app = App(root)
    if "--tab" in sys.argv:                      # developer aid: open a given tab, e.g. --tab 4
        app.nb.select(app.nb.tabs()[int(sys.argv[sys.argv.index("--tab") + 1])])
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
