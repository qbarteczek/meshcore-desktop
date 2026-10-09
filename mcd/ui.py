"""Tkinter user interface. All radio work is delegated to ``core.Core``."""
import csv
import os
import queue
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import core as corem
from .core import APP_NAME, DATA, LINK_COLS, LINK_CSV, TYPE_NAMES, VERSION, Core, SerialConsole, device_label, save_config
from . import i18n
from .i18n import T

HERE = Path(__file__).resolve().parent
QUICK_CMDS = ["ver", "clock", "get name", "get radio", "get tx", "neighbors", "advert", "clear stats", "reboot"]


def scrolled(parent, widget_cls, **kw):
    """Create a widget with a vertical scrollbar inside its own frame; returns (frame, widget)."""
    f = ttk.Frame(parent)
    w = widget_cls(f, **kw)
    sb = ttk.Scrollbar(f, command=w.yview)
    w.config(yscrollcommand=sb.set)
    w.pack(side="left", fill="both", expand=True)
    sb.pack(side="left", fill="y")
    return f, w


class LogView:
    """Read-only text box with Pause / Clear / Save controls, used for consoles and logs."""

    def __init__(self, parent, height=10, controls=True):
        self.frame = ttk.Frame(parent)
        self.paused = tk.BooleanVar(value=False)
        if controls:
            bar = ttk.Frame(self.frame)
            bar.pack(fill="x", side="bottom", pady=(2, 0))
            ttk.Checkbutton(bar, text=T("Wstrzymaj"), variable=self.paused).pack(side="left")
            ttk.Button(bar, text=T("Wyczyść"), command=self.clear).pack(side="left", padx=4)
            ttk.Button(bar, text=T("Zapisz do pliku…"), command=self.save).pack(side="left")
        f, self.text = scrolled(self.frame, tk.Text, height=height, wrap="none", state="disabled",
                                font=("Consolas", 9), background="#fafafa")
        f.pack(fill="both", expand=True)

    def add(self, line):
        if self.paused.get():
            return
        self.text.config(state="normal")
        self.text.insert("end", line + "\n")
        if int(self.text.index("end-1c").split(".")[0]) > 3000:
            self.text.delete("1.0", "500.0")
        self.text.config(state="disabled")
        self.text.see("end")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def save(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if p:
            Path(p).write_text(self.text.get("1.0", "end"), encoding="utf-8")


class App:
    def __init__(self, root):
        self.root = root
        self.uiq = queue.Queue()
        self.core = Core(self.uiq)
        self.serial = SerialConsole(self.uiq)
        self.conv = None
        self.conv_keys = []
        self.remote_keys = []
        self.link_results = []
        root.title(APP_NAME)
        root.geometry("1040x680")
        root.minsize(820, 520)
        ico = HERE / "app.ico"
        if ico.exists():
            root.iconbitmap(str(ico))

        bar = ttk.Frame(root, padding=(8, 5))
        bar.pack(fill="x")
        self.status = ttk.Label(bar, text="…", font=("Segoe UI", 10, "bold"))
        self.status.pack(side="left")
        ttk.Button(bar, text=T("Pomoc"), command=self.show_help).pack(side="right")
        ttk.Button(bar, text=T("Rozłącz"), command=lambda: self.core.call(self.core.do_disconnect())).pack(side="right", padx=4)
        ttk.Button(bar, text=T("Połącz…"), command=self.connect_dialog).pack(side="right")
        self.devbox = ttk.Combobox(bar, state="readonly", width=26)
        self.devbox.pack(side="right", padx=4)
        self.devbox.bind("<<ComboboxSelected>>", self.pick_saved)
        ttk.Label(bar, text=T("Urządzenie:")).pack(side="right")
        self.batt = ttk.Label(bar, text="")
        self.batt.pack(side="right", padx=10)
        self.toast = ttk.Label(root, text="", padding=(8, 2), foreground="#555")
        self.toast.pack(fill="x", side="bottom")

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True)
        for title, build in ((T("Wiadomości"), self.build_chat), (T("Kontakty"), self.build_contacts),
                             (T("Zdalne zarządzanie"), self.build_remote), (T("Test łącza"), self.build_link),
                             (T("Urządzenie"), self.build_device), (T("Konsola USB"), self.build_serial),
                             (T("Deweloper"), self.build_dev), (T("Ustawienia"), self.build_settings)):
            f = ttk.Frame(self.nb, padding=8)
            self.nb.add(f, text=f"  {title}  ")
            build(f)

        self.fill_saved()
        self.core.start()
        self.load_link_rows()
        self.poll()
        self.tick()
        if not self.core.cfg["devices"]:
            root.after(400, self.connect_dialog)

    # ---- connection ------------------------------------------------------
    def fill_saved(self):
        cfg = self.core.cfg
        self.devbox.config(values=[f"{device_label(d)}  [{d['kind']}]" for d in cfg["devices"]])
        if 0 <= cfg["last_device"] < len(cfg["devices"]):
            self.devbox.current(cfg["last_device"])
        else:
            self.devbox.set("")
        if hasattr(self, "saved_list"):
            self.saved_list.delete(0, "end")
            for d in cfg["devices"]:
                self.saved_list.insert("end", f"{device_label(d)}  [{d['kind']}]")

    def pick_saved(self, _e=None):
        i = self.devbox.current()
        if i >= 0:
            self.connect_to(self.core.cfg["devices"][i])

    def connect_to(self, dev):
        cfg = self.core.cfg
        ident = {k: v for k, v in dev.items() if k in ("kind", "address", "port", "host")}
        for i, d in enumerate(cfg["devices"]):
            if {k: v for k, v in d.items() if k in ident} == ident:
                d.update(dev)
                cfg["last_device"] = i
                break
        else:
            cfg["devices"].append(dev)
            cfg["last_device"] = len(cfg["devices"]) - 1
        save_config(cfg)
        self.fill_saved()
        self.core.call(self.core.do_connect(cfg["devices"][cfg["last_device"]]))

    def connect_dialog(self):
        win = tk.Toplevel(self.root)
        win.title(T("Połącz z urządzeniem MeshCore"))
        win.transient(self.root)
        win.geometry("520x380")
        ttk.Label(win, wraplength=490, foreground="#555", padding=8, text=T(
            "Urządzenia z firmware „companion” (klient). Repeater podłączony kablem USB obsłużysz w zakładce „Konsola USB”."
        )).pack(fill="x")
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Bluetooth
        fb = ttk.Frame(nb, padding=8)
        nb.add(fb, text=T("Bluetooth"))
        found = []
        top = ttk.Frame(fb)
        info = ttk.Label(top, text="")
        lst = tk.Listbox(fb, height=8, exportselection=False)
        pin = tk.StringVar(value="123456")

        def scan():
            info.config(text=T("Szukam urządzeń (12 s)…"))
            fut = self.core.call(corem.ble_scan())

            def done():
                if not fut.done():
                    win.after(300, done)
                    return
                found[:] = fut.result() or []
                if not win.winfo_exists():
                    return
                lst.delete(0, "end")
                for name, addr, rssi in found:
                    lst.insert("end", f"{name}   {addr}   {rssi} dBm")
                info.config(text=T("Znaleziono: {n}", n=len(found)))
            done()

        def go_ble():
            if not lst.curselection():
                messagebox.showinfo(APP_NAME, T("Wybierz urządzenie z listy."), parent=win)
                return
            name, addr, _ = found[lst.curselection()[0]]
            self.connect_to({"kind": "ble", "address": addr, "pin": pin.get().strip(), "label": name})
            win.destroy()

        top.pack(fill="x")
        ttk.Button(top, text=T("Szukaj urządzeń"), command=scan).pack(side="left")
        info.pack(side="left", padx=8)
        lst.pack(fill="both", expand=True, pady=6)
        bot = ttk.Frame(fb)
        bot.pack(fill="x")
        ttk.Label(bot, text=T("PIN parowania:")).pack(side="left")
        ttk.Entry(bot, textvariable=pin, width=10).pack(side="left", padx=4)
        ttk.Button(bot, text=T("Połącz"), command=go_ble).pack(side="right")

        # USB serial
        fs = ttk.Frame(nb, padding=8)
        nb.add(fs, text=T("USB (port szeregowy)"))
        ports = SerialConsole.ports()
        port = tk.StringVar(value=ports[0][0] if ports else "")
        baud = tk.StringVar(value="115200")
        ttk.Label(fs, text=T("Port:")).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(fs, textvariable=port, values=[p for p, _ in ports], width=14).grid(row=0, column=1, sticky="w")
        ttk.Label(fs, text="\n".join(f"{p}: {d}" for p, d in ports) or T("Brak portów szeregowych"),
                  foreground="#555").grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(fs, text=T("Prędkość:")).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(fs, textvariable=baud, width=10).grid(row=2, column=1, sticky="w")

        def go_serial():
            if port.get():
                self.connect_to({"kind": "serial", "port": port.get(), "baud": int(baud.get() or 115200)})
                win.destroy()
        ttk.Button(fs, text=T("Połącz"), command=go_serial).grid(row=3, column=1, sticky="w", pady=8)

        # TCP
        ft = ttk.Frame(nb, padding=8)
        nb.add(ft, text=T("Sieć (TCP/Wi-Fi)"))
        host, tport = tk.StringVar(), tk.StringVar(value="5000")
        ttk.Label(ft, text=T("Adres (host):")).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(ft, textvariable=host, width=24).grid(row=0, column=1, sticky="w")
        ttk.Label(ft, text=T("Port:")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(ft, textvariable=tport, width=8).grid(row=1, column=1, sticky="w")

        def go_tcp():
            if not host.get().strip() or not tport.get().isdigit():
                messagebox.showinfo(APP_NAME, T("Podaj adres i port."), parent=win)
                return
            self.connect_to({"kind": "tcp", "host": host.get().strip(), "port": int(tport.get())})
            win.destroy()
        ttk.Button(ft, text=T("Połącz"), command=go_tcp).grid(row=2, column=1, sticky="w", pady=8)

    # ---- Messages --------------------------------------------------------
    def build_chat(self, f):
        left = ttk.Frame(f)
        left.pack(side="left", fill="y", padx=(0, 6))
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *a: self.fill_convs())
        ttk.Label(left, text=T("Szukaj kontaktu:")).pack(anchor="w")
        ttk.Entry(left, textvariable=self.filter).pack(fill="x")
        lf, self.convs = scrolled(left, tk.Listbox, width=30, exportselection=False, activestyle="none", font=("Segoe UI", 10))
        lf.pack(fill="both", expand=True, pady=4)
        self.convs.bind("<<ListboxSelect>>", self.on_pick)

        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True)
        self.conv_title = ttk.Label(right, text=T("Wybierz rozmowę"), font=("Segoe UI", 11, "bold"))
        self.conv_title.pack(anchor="w")
        ef = ttk.Frame(right)
        ef.pack(side="bottom", fill="x", pady=(4, 0))
        self.entry = ttk.Entry(ef, font=("Segoe UI", 10))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())
        ttk.Button(ef, text=T("Wyślij"), command=self.send).pack(side="left", padx=(4, 0))
        tf, self.view = scrolled(right, tk.Text, wrap="word", state="disabled", font=("Segoe UI", 10), padx=6, pady=4)
        tf.pack(fill="both", expand=True)
        self.view.tag_config("meta", foreground="#777", font=("Segoe UI", 8))
        self.view.tag_config("in", foreground="#0b5394", font=("Segoe UI", 10, "bold"))
        self.view.tag_config("out", foreground="#38761d", font=("Segoe UI", 10, "bold"))

    def contacts(self):
        return sorted((self.core.mc.contacts.values() if self.core.mc else []), key=lambda x: x["adv_name"].lower())

    def fill_convs(self):
        c = self.core
        flt = self.filter.get().strip().lower()
        items = [] if flt else [(f"ch:{i}", "# " + n.lstrip("#")) for i, n in sorted(c.channels.items())]
        target = c.cfg["target_name"].lower()
        for ct in self.contacts():
            key, name = "c:" + ct["public_key"][:12], ct["adv_name"]
            if flt:
                if flt not in name.lower():
                    continue
            elif key not in c.msgs and not (target and name.lower().startswith(target)):
                continue
            items.append((key, name))
        self.conv_keys = [k for k, _ in items]
        self.convs.delete(0, "end")
        for k, label in items:
            self.convs.insert("end", ("● " if k in c.unread else "   ") + label)
        if self.conv in self.conv_keys:
            self.convs.selection_set(self.conv_keys.index(self.conv))

    def open_conv(self, key, label):
        self.conv = key
        self.core.unread.discard(key)
        self.conv_title.config(text=label)
        self.fill_convs()
        self.show_conv()
        self.entry.focus_set()

    def on_pick(self, _e):
        sel = self.convs.curselection()
        if sel:
            self.open_conv(self.conv_keys[sel[0]], self.convs.get(sel[0])[2:].strip())

    def show_conv(self):
        self.view.config(state="normal")
        self.view.delete("1.0", "end")
        for m in self.core.msgs.get(self.conv, [])[-300:]:
            meta = time.strftime("%d.%m %H:%M", time.localtime(m["t"]))
            if m["dir"] == "in":
                if m.get("hops") not in (None, 255):
                    meta += f" · {T('hopy')} {m['hops']}"
                if m.get("snr") is not None:
                    meta += f" · SNR {m['snr']}"
            elif m.get("st"):
                meta += " · " + m["st"]
            self.view.insert("end", m["sender"], m["dir"])
            self.view.insert("end", "  " + meta + "\n", "meta")
            self.view.insert("end", m["text"] + "\n\n")
        self.view.config(state="disabled")
        self.view.see("end")

    def send(self):
        text = self.entry.get().strip()
        if text and self.conv:
            self.entry.delete(0, "end")
            self.core.call(self.core.do_send(self.conv, text))

    # ---- Contacts --------------------------------------------------------
    def build_contacts(self, f):
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.cfilter = tk.StringVar()
        self.ctype = tk.StringVar(value=T("wszystkie"))
        self.cfilter.trace_add("write", lambda *a: self.fill_contacts())
        ttk.Label(top, text=T("Filtr:")).pack(side="left")
        ttk.Entry(top, textvariable=self.cfilter, width=22).pack(side="left", padx=4)
        ttk.Label(top, text=T("Typ:")).pack(side="left", padx=(8, 0))
        cb = ttk.Combobox(top, textvariable=self.ctype, state="readonly", width=14,
                          values=[T("wszystkie")] + [T(v) for v in TYPE_NAMES.values()])
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.fill_contacts())
        self.ccount = ttk.Label(top, text="")
        self.ccount.pack(side="right")
        cols = ("name", "type", "heard", "route", "key")
        tf, self.ctree = scrolled(f, ttk.Treeview, columns=cols, show="headings", selectmode="browse")
        for c, (title, w) in zip(cols, ((T("Nazwa"), 240), (T("Typ"), 110), (T("Ostatnio słyszany"), 140),
                                        (T("Trasa"), 100), (T("Klucz"), 130))):
            self.ctree.heading(c, text=title, command=lambda c=c: self.sort_contacts(c))
            self.ctree.column(c, width=w, anchor="w")
        tf.pack(fill="both", expand=True, pady=6)
        self.csort = ("name", False)
        bf = ttk.Frame(f)
        bf.pack(fill="x")
        for text, cmd in ((T("Napisz"), self.contact_message), (T("Zarządzaj zdalnie"), self.contact_manage),
                          (T("Resetuj trasę"), self.contact_reset), (T("Kopiuj klucz"), self.contact_copy),
                          (T("Usuń"), self.contact_remove)):
            ttk.Button(bf, text=text, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Button(bf, text=T("Porządki…"), command=self.contacts_cleanup).pack(side="right")

    def sort_contacts(self, col):
        self.csort = (col, not self.csort[1] if self.csort[0] == col else False)
        self.fill_contacts()

    def fill_contacts(self):
        flt = self.cfilter.get().strip().lower()
        rows = []
        for c in self.contacts():
            tname = T(TYPE_NAMES.get(c.get("type"), "?"))
            if (flt and flt not in c["adv_name"].lower()) or self.ctype.get() not in (T("wszystkie"), tname):
                continue
            pl = c.get("out_path_len", -1)
            route = "flood" if pl < 0 else (T("bezpośrednio") if pl == 0 else f"{pl} {T('hopy')}")
            la = c.get("last_advert", 0)
            rows.append({"name": c["adv_name"], "type": tname, "route": route, "key": c["public_key"][:12], "la": la,
                         "heard": time.strftime("%Y-%m-%d %H:%M", time.localtime(la)) if la else "-"})
        col, rev = self.csort
        rows.sort(key=lambda r: r["la"] if col == "heard" else str(r[col]).lower(), reverse=rev)
        self.ctree.delete(*self.ctree.get_children())
        for r in rows:
            self.ctree.insert("", "end", iid=r["key"], values=(r["name"], r["type"], r["heard"], r["route"], r["key"]))
        mx = self.core.info.get("dev", {}).get("max_contacts", "?")
        self.ccount.config(text=T("Kontakty: {n} / {max}", n=len(self.contacts()), max=mx))

    def _csel(self):
        sel = self.ctree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, T("Najpierw wybierz kontakt."))
            return None, None
        return sel[0], self.ctree.item(sel[0], "values")[0]

    def contact_message(self):
        key, name = self._csel()
        if key:
            self.nb.select(0)
            self.open_conv("c:" + key, name)

    def contact_manage(self):
        key, name = self._csel()
        if key:
            self.fill_remote()
            if key in self.remote_keys:
                self.rnode.current(self.remote_keys.index(key))
            self.nb.select(2)

    def contact_reset(self):
        key, _ = self._csel()
        if key:
            self.core.call(self.core.do_reset_path(key))

    def contact_copy(self):
        key, _ = self._csel()
        if key:
            c = self.core.contact_by_prefix(key)
            self.root.clipboard_clear()
            self.root.clipboard_append(c["public_key"])

    def contact_remove(self):
        key, name = self._csel()
        if key and messagebox.askyesno(APP_NAME, T("Usunąć kontakt „{name}” z urządzenia?", name=name)):
            self.core.call(self.core.do_remove_contacts([key]))

    def contacts_cleanup(self):
        days = simpledialog.askinteger(APP_NAME, T("Usuń kontakty niesłyszane od ilu dni?"), parent=self.root,
                                       initialvalue=30, minvalue=1, maxvalue=3650)
        if not days:
            return
        limit, c = time.time() - days * 86400, self.core
        target = c.find_contact(c.cfg["target_name"]) if c.mc else None
        old = [x["public_key"][:12] for x in self.contacts()
               if x.get("last_advert", 0) < limit and "c:" + x["public_key"][:12] not in c.msgs and x is not target]
        if not old:
            messagebox.showinfo(APP_NAME, T("Brak kontaktów do usunięcia."))
        elif messagebox.askyesno(APP_NAME, T(
                "Usunąć {n} kontaktów niesłyszanych od {d} dni?\n(Kontakty z historią rozmów i cel testu łącza zostają.)",
                n=len(old), d=days)):
            c.call(c.do_remove_contacts(old))

    # ---- Remote management ----------------------------------------------
    def build_remote(self, f):
        ttk.Label(f, foreground="#555", text=T(
            "Zarządzanie repeaterem, serwerem pokoju lub czujnikiem przez sieć radiową (wymaga hasła administratora węzła)."
        )).pack(anchor="w")
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        ttk.Label(top, text=T("Węzeł:")).pack(side="left")
        self.rnode = ttk.Combobox(top, width=34, postcommand=self.fill_remote)
        self.rnode.pack(side="left", padx=4)
        ttk.Label(top, text=T("Hasło:")).pack(side="left", padx=(8, 0))
        self.rpwd = ttk.Entry(top, width=14, show="•")
        self.rpwd.pack(side="left", padx=4)
        ttk.Button(top, text=T("Zaloguj"), command=lambda: self.remote("login")).pack(side="left")
        for label, what in ((T("Status"), "status"), (T("Telemetria"), "telemetry"), (T("Sąsiedzi"), "neighbours")):
            ttk.Button(top, text=label, command=lambda w=what: self.remote(w)).pack(side="left", padx=(4, 0))
        cf = ttk.Frame(f)
        cf.pack(fill="x", side="bottom", pady=(4, 0))
        ttk.Label(cf, text=T("Polecenie CLI:")).pack(side="left")
        self.rcmd = ttk.Entry(cf, font=("Consolas", 10))
        self.rcmd.pack(side="left", fill="x", expand=True, padx=4)
        self.rcmd.bind("<Return>", lambda e: self.remote("cmd"))
        ttk.Button(cf, text=T("Wyślij"), command=lambda: self.remote("cmd")).pack(side="left")
        qf = ttk.Frame(f)
        qf.pack(fill="x", side="bottom")
        ttk.Label(qf, text=T("Szybkie polecenia:")).pack(side="left")
        for q in QUICK_CMDS:
            ttk.Button(qf, text=q, width=len(q) + 1, command=lambda q=q: self.quick(self.rcmd, q, lambda: self.remote("cmd"))).pack(side="left", padx=1)
        self.rlog = LogView(f)
        self.rlog.frame.pack(fill="both", expand=True)

    def quick(self, entry, cmd, run):
        entry.delete(0, "end")
        entry.insert(0, cmd)
        if cmd != "reboot" or messagebox.askyesno(APP_NAME, T("Zrestartować urządzenie?")):
            run()

    def fill_remote(self):
        typed = self.rnode.get().strip().lower()
        nodes = [c for c in self.contacts() if c.get("type") in (2, 3, 4)]
        if typed and typed not in [f"{c['adv_name']}  [{T(TYPE_NAMES[c['type']])}]".lower() for c in nodes]:
            nodes = [c for c in nodes if typed in c["adv_name"].lower()] or nodes
        self.remote_keys = [c["public_key"][:12] for c in nodes]
        self.rnode.config(values=[f"{c['adv_name']}  [{T(TYPE_NAMES[c['type']])}]" for c in nodes])

    def remote(self, what):
        i = self.rnode.current()
        if i < 0:
            messagebox.showinfo(APP_NAME, T("Najpierw wybierz węzeł."))
            return
        key, c = self.remote_keys[i], self.core
        if what == "login":
            c.call(c.do_remote_login(key, self.rpwd.get()))
        elif what == "cmd":
            cmd = self.rcmd.get().strip()
            if cmd:
                self.rcmd.delete(0, "end")
                c.call(c.do_remote_cmd(key, cmd))
        else:
            c.call(c.do_remote_query(key, what))

    # ---- Link test -------------------------------------------------------
    def build_link(self, f):
        cfg = self.core.cfg
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.v_en = tk.BooleanVar(value=cfg["link_enabled"])
        self.v_int = tk.IntVar(value=cfg["link_interval_min"])
        self.v_target = tk.StringVar(value=cfg["target_name"])
        self.v_probe = tk.BooleanVar(value=cfg["probe_enabled"])
        self.v_pchan = tk.StringVar(value=cfg["probe_channel"])
        self.v_url = tk.StringVar(value=cfg["traces_url"])
        ttk.Checkbutton(top, text=T("Automatyczny test co"), variable=self.v_en, command=self.save_link).grid(row=0, column=0, sticky="w")
        ttk.Spinbox(top, from_=5, to=1440, width=5, textvariable=self.v_int, command=self.save_link).grid(row=0, column=1)
        ttk.Label(top, text=T("min   do kontaktu:")).grid(row=0, column=2, padx=4)
        self.tbox = ttk.Combobox(top, textvariable=self.v_target, width=22,
                                 postcommand=lambda: self.tbox.config(values=[c["adv_name"] for c in self.contacts() if c.get("type") == 1]))
        self.tbox.grid(row=0, column=3)
        ttk.Button(top, text=T("Wyślij test teraz"), command=self.link_now).grid(row=0, column=4, padx=10)
        self.next_lbl = ttk.Label(top, text="")
        self.next_lbl.grid(row=0, column=5, sticky="w")
        ttk.Label(top, text=T("Adres mostka (traces.json):")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(top, textvariable=self.v_url, width=52).grid(row=1, column=1, columnspan=4, sticky="w")
        ttk.Checkbutton(top, text=T("Dodatkowo sonda na kanale (SNR/RSSI po stronie odbiorcy z mostka):"),
                        variable=self.v_probe, command=self.save_link).grid(row=2, column=0, columnspan=4, sticky="w")
        self.pchan = ttk.Combobox(top, textvariable=self.v_pchan, width=14, state="readonly")
        self.pchan.grid(row=2, column=4, sticky="w")
        for w in (self.tbox, self.pchan):
            w.bind("<<ComboboxSelected>>", lambda _e: self.save_link())
        sf = ttk.Frame(f)
        sf.pack(fill="x", pady=(6, 2))
        self.summary = ttk.Label(sf, text="", font=("Segoe UI", 10, "bold"))
        self.summary.pack(side="left")
        ttk.Label(sf, text="   " + T("Ostatnie testy:")).pack(side="left")
        self.strip = tk.Canvas(sf, height=16, width=490, highlightthickness=0)
        self.strip.pack(side="left", padx=6)
        heads = {"time": (T("Czas"), 130), "device": (T("Urządzenie"), 90), "target": (T("Cel"), 90), "nr": (T("Nr"), 40),
                 "result": (T("Wynik"), 95), "ack_s": (T("ACK po [s]"), 70), "route": (T("Trasa"), 50),
                 "rssi": ("RSSI", 50), "snr": ("SNR", 45), "noise": (T("Szum"), 50), "bat_V": (T("Bat [V]"), 55),
                 "srv_seen": (T("Odebrał"), 80), "srv_snr": ("SNR*", 45), "srv_rssi": ("RSSI*", 50), "srv_hops": (T("Hopy"), 45)}
        tf, self.tree = scrolled(f, ttk.Treeview, columns=LINK_COLS, show="headings")
        for c in LINK_COLS:
            self.tree.heading(c, text=heads[c][0])
            self.tree.column(c, width=heads[c][1], anchor="center")
        tf.pack(fill="both", expand=True)
        self.tree.tag_configure("ok", foreground="#38761d")
        self.tree.tag_configure("bad", foreground="#cc0000")
        ttk.Label(f, text=T("Dziennik: {path}", path=LINK_CSV), foreground="#777").pack(anchor="w")

    def save_link(self):
        cfg = self.core.cfg
        try:
            interval = max(5, int(self.v_int.get()))
        except (tk.TclError, ValueError):
            interval = cfg["link_interval_min"]
        changed = interval != cfg["link_interval_min"] or self.v_en.get() != cfg["link_enabled"]
        cfg.update(link_enabled=self.v_en.get(), link_interval_min=interval, target_name=self.v_target.get().strip(),
                   probe_enabled=self.v_probe.get(), probe_channel=self.v_pchan.get(), traces_url=self.v_url.get().strip())
        save_config(cfg)
        if changed:
            self.core.schedule_next()

    def link_now(self):
        self.save_link()
        self.core.call(self.core.do_link_test())

    def add_link_row(self, row):
        ok = row.get("result") == "ACK"
        self.tree.insert("", 0, values=[row.get(c, "") for c in LINK_COLS], tags=("ok" if ok else "bad",))
        self.link_results.append(ok)
        n, good = len(self.link_results), sum(self.link_results)
        self.summary.config(text=T("Potwierdzone: {ok} z {n} testów ({p}%)", ok=good, n=n, p=100 * good // max(1, n)))
        self.strip.delete("all")
        for i, r in enumerate(self.link_results[-48:]):           # one square per test, oldest on the left
            self.strip.create_rectangle(i * 10, 2, i * 10 + 8, 14, fill="#38761d" if r else "#cc0000", outline="")

    def load_link_rows(self):
        if LINK_CSV.exists():
            with LINK_CSV.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f, delimiter=";"):
                    self.add_link_row(row)

    # ---- Device ----------------------------------------------------------
    def build_device(self, f):
        left = ttk.Frame(f)
        left.pack(side="left", fill="y", padx=(0, 16))
        self.dv = {k: tk.StringVar() for k in ("name", "lat", "lon", "txp", "freq", "bw", "sf", "cr")}

        def field(parent, row, label, key):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(parent, textvariable=self.dv[key], width=18).grid(row=row, column=1, sticky="w", padx=6)

        g1 = ttk.LabelFrame(left, text=T("Podstawowe"), padding=8)
        g1.pack(fill="x")
        for i, (label, key) in enumerate(((T("Nazwa"), "name"), (T("Szer. geogr."), "lat"), (T("Dł. geogr."), "lon"), (T("Moc TX [dBm]"), "txp"))):
            field(g1, i, label, key)
        ttk.Button(g1, text=T("Zapisz"), command=self.save_basic).grid(row=4, column=1, sticky="e", pady=(6, 0))
        self.v_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(g1, text=T("Automatycznie dodawaj nowe kontakty"), variable=self.v_auto,
                        command=lambda: self.core.call(self.core.do_set_autoadd(self.v_auto.get()))).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        g2 = ttk.LabelFrame(left, text=T("Radio LoRa"), padding=8)
        g2.pack(fill="x", pady=8)
        for i, (label, key) in enumerate(((T("Częstotliwość [MHz]"), "freq"), (T("Pasmo [kHz]"), "bw"), ("SF", "sf"), ("CR", "cr"))):
            field(g2, i, label, key)
        ttk.Button(g2, text=T("Zapisz radio…"), command=self.save_radio).grid(row=4, column=1, sticky="e", pady=(6, 0))

        g3 = ttk.LabelFrame(left, text=T("Akcje"), padding=8)
        g3.pack(fill="x")
        c = self.core
        acts = [(T("Odśwież"), lambda: c.call(c.do_refresh())),
                (T("Synchronizuj zegar"), lambda: c.call(c.do_sync_time())),
                (T("Rozgłoś się (zero-hop)"), lambda: c.call(c.do_advert(False))),
                (T("Rozgłoś się (flood)"), lambda: c.call(c.do_advert(True))),
                (T("Kopia ustawień…"), self.backup),
                (T("Przywróć z kopii…"), self.restore),
                (T("Zmień PIN Bluetooth…"), self.set_pin),
                (T("Restart urządzenia"), self.reboot)]
        for i, (t, cmd) in enumerate(acts):
            ttk.Button(g3, text=t, command=cmd).grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)

        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True)
        self.devinfo = tk.Text(right, height=8, state="disabled", font=("Consolas", 9), background="#f4f4f4", relief="flat")
        self.devinfo.pack(fill="x")
        g4 = ttk.LabelFrame(right, text=T("Kanały"), padding=8)
        g4.pack(fill="both", expand=True, pady=(8, 0))
        self.chlist = tk.Listbox(g4, height=8, exportselection=False, font=("Segoe UI", 10))
        self.chlist.pack(fill="both", expand=True)
        cf = ttk.Frame(g4)
        cf.pack(fill="x", pady=(6, 0))
        ttk.Button(cf, text=T("Dodaj / zmień kanał…"), command=self.edit_channel).pack(side="left")
        ttk.Button(cf, text=T("Usuń kanał"), command=self.del_channel).pack(side="left", padx=6)
        ttk.Label(g4, foreground="#777", text=T(
            "Kanał „#nazwa” ma klucz wyliczany z nazwy; inne wymagają klucza (32 znaki hex).")).pack(anchor="w")

    def fill_device(self):
        info = self.core.info if self.core.connected or self.core.mc else {}
        s, d, b = info.get("self", {}), info.get("dev", {}), info.get("bat", {})
        for key, src in (("name", "name"), ("lat", "adv_lat"), ("lon", "adv_lon"), ("txp", "tx_power"),
                         ("freq", "radio_freq"), ("bw", "radio_bw"), ("sf", "radio_sf"), ("cr", "radio_cr")):
            self.dv[key].set(s.get(src, ""))
        self.v_auto.set(not s.get("manual_add_contacts", False))
        r = info.get("radio", {})
        lines = [f"{T('Model')}:      {d.get('model', '?')}",
                 f"{T('Firmware')}:   {d.get('ver', '?')} ({d.get('fw_build', '?')})",
                 f"{T('Klucz')}:      {s.get('public_key', '')[:32]}…",
                 f"{T('Bateria')}:    {b.get('level', 0) / 1000:.2f} V   {T('pamięć')}: {b.get('used_kb', '?')}/{b.get('total_kb', '?')} kB",
                 f"Radio:      {T('szum')} {r.get('noise_floor', '?')} dBm, {T('ostatni RSSI')} {r.get('last_rssi', '?')} dBm, SNR {r.get('last_snr', '?')} dB",
                 f"{T('Czas w eterze')}: TX {r.get('tx_air_secs', '?')} s, RX {r.get('rx_air_secs', '?')} s",
                 f"Stats:      {info.get('core', {})}"]
        self.devinfo.config(state="normal")
        self.devinfo.delete("1.0", "end")
        self.devinfo.insert("end", "\n".join(lines) if info else "")
        self.devinfo.config(state="disabled")
        self.batt.config(text=f"🔋 {b['level'] / 1000:.2f} V" if b.get("level") else "")

    def fill_channels(self):
        self.chlist.delete(0, "end")
        for i, n in sorted(self.core.channels.items()):
            self.chlist.insert("end", f"{i}: {n}")
        self.pchan.config(values=[n for _, n in sorted(self.core.channels.items())])

    def save_basic(self):
        try:
            args = (self.dv["name"].get().strip(), float(self.dv["lat"].get()), float(self.dv["lon"].get()),
                    int(float(self.dv["txp"].get())))
        except ValueError:
            messagebox.showerror(APP_NAME, T("Pozycja i moc muszą być liczbami."))
            return
        mx = self.core.info.get("self", {}).get("max_tx_power", 22)
        if not args[0] or not 1 <= args[3] <= mx:
            messagebox.showerror(APP_NAME, T("Nazwa nie może być pusta, a moc musi być w zakresie 1–{mx} dBm.", mx=mx))
            return
        self.core.call(self.core.do_set_basic(*args))

    def save_radio(self):
        try:
            a = (float(self.dv["freq"].get()), float(self.dv["bw"].get()), int(self.dv["sf"].get()), int(self.dv["cr"].get()))
        except ValueError:
            messagebox.showerror(APP_NAME, T("Parametry radia muszą być liczbami."))
            return
        if not (150 <= a[0] <= 960 and 7 <= a[1] <= 500 and 5 <= a[2] <= 12 and 5 <= a[3] <= 8):
            messagebox.showerror(APP_NAME, T("Parametry poza zakresem (częstotliwość 150–960 MHz, pasmo 7–500 kHz, SF 5–12, CR 5–8)."))
            return
        if messagebox.askyesno(APP_NAME, T(
                "Zmiana parametrów radia odetnie urządzenie od sieci, jeśli nie będą takie same jak u pozostałych węzłów.\n\nZapisać {f} MHz / {b} kHz / SF{sf} / CR{cr}?",
                f=a[0], b=a[1], sf=a[2], cr=a[3])):
            self.core.call(self.core.do_set_radio(*a))

    def set_pin(self):
        pin = simpledialog.askstring(APP_NAME, T("Nowy PIN Bluetooth (6 cyfr):"), parent=self.root)
        if pin is None:
            return
        if not (pin.isdigit() and len(pin) == 6):
            messagebox.showerror(APP_NAME, T("PIN musi mieć dokładnie 6 cyfr."))
            return
        self.core.call(self.core.do_set_pin(int(pin)))

    def reboot(self):
        if messagebox.askyesno(APP_NAME, T("Zrestartować urządzenie?")):
            self.core.call(self.core.do_reboot())

    def backup(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")],
                                         initialfile=f"meshcore-{self.core.my_name}-{time.strftime('%Y%m%d')}.json")
        if p:
            self.core.call(self.core.do_backup(p))

    def restore(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if p and messagebox.askyesno(APP_NAME, T(
                "Przywrócić nazwę, pozycję, moc i kanały z kopii „{name}”?\n(Parametry radia i kontakty nie są zmieniane.)",
                name=Path(p).name)):
            self.core.call(self.core.do_restore(p))

    def edit_channel(self):
        sel = self.chlist.curselection()
        used = sorted(self.core.channels)
        free = next(i for i in range(41) if i not in used)
        idx = simpledialog.askinteger(T("Kanał"), T("Numer kanału (slot):"), parent=self.root,
                                      initialvalue=used[sel[0]] if sel else free, minvalue=0, maxvalue=39)
        if idx is None:
            return
        name = simpledialog.askstring(T("Kanał"), T("Nazwa kanału (np. #test):"), parent=self.root,
                                      initialvalue=self.core.channels.get(idx, "#"))
        if not name:
            return
        secret = None
        if not name.startswith("#"):
            hx = simpledialog.askstring(T("Kanał"), T("Klucz kanału (32 znaki hex):"), parent=self.root) or ""
            try:
                secret = bytes.fromhex(hx)
            except ValueError:
                secret = b""
            if len(secret) != 16:
                messagebox.showerror(APP_NAME, T("Klucz musi mieć dokładnie 32 znaki szesnastkowe."))
                return
        self.core.call(self.core.do_set_channel(idx, name, secret))

    def del_channel(self):
        sel = self.chlist.curselection()
        if not sel:
            return
        idx = sorted(self.core.channels)[sel[0]]
        if messagebox.askyesno(APP_NAME, T("Usunąć kanał {i}: {n}?", i=idx, n=self.core.channels[idx])):
            self.core.call(self.core.do_set_channel(idx, "", bytes(16)))

    # ---- USB console -----------------------------------------------------
    def build_serial(self, f):
        ttk.Label(f, foreground="#555", text=T(
            "Bezpośrednia konsola tekstowa repeatera, serwera pokoju lub czujnika podłączonego kablem USB.")).pack(anchor="w")
        top = ttk.Frame(f)
        top.pack(fill="x", pady=6)
        ttk.Label(top, text=T("Port:")).pack(side="left")
        self.sport = ttk.Combobox(top, width=12, postcommand=lambda: self.sport.config(values=[p for p, _ in SerialConsole.ports()]))
        self.sport.pack(side="left", padx=4)
        ttk.Label(top, text=T("Prędkość:")).pack(side="left")
        self.sbaud = ttk.Entry(top, width=8)
        self.sbaud.insert(0, "115200")
        self.sbaud.pack(side="left", padx=4)
        ttk.Button(top, text=T("Otwórz"), command=self.serial_open).pack(side="left")
        ttk.Button(top, text=T("Zamknij"), command=self.serial.close).pack(side="left", padx=4)
        cf = ttk.Frame(f)
        cf.pack(fill="x", side="bottom", pady=(4, 0))
        ttk.Label(cf, text=T("Polecenie:")).pack(side="left")
        self.scmd = ttk.Entry(cf, font=("Consolas", 10))
        self.scmd.pack(side="left", fill="x", expand=True, padx=4)
        self.scmd.bind("<Return>", lambda e: self.serial_send())
        ttk.Button(cf, text=T("Wyślij"), command=self.serial_send).pack(side="left")
        qf = ttk.Frame(f)
        qf.pack(fill="x", side="bottom")
        ttk.Label(qf, text=T("Szybkie polecenia:")).pack(side="left")
        for q in QUICK_CMDS:
            ttk.Button(qf, text=q, width=len(q) + 1, command=lambda q=q: self.quick(self.scmd, q, self.serial_send)).pack(side="left", padx=1)
        self.slog = LogView(f)
        self.slog.frame.pack(fill="both", expand=True)

    def serial_open(self):
        try:
            self.serial.open(self.sport.get(), int(self.sbaud.get() or 115200))
            self.slog.add("--- " + T("Otwarto {port}", port=self.sport.get()) + " ---")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, T("Błąd: {err}", err=e))

    def serial_send(self):
        cmd = self.scmd.get().strip()
        if cmd:
            self.scmd.delete(0, "end")
            self.slog.add("> " + cmd)
            self.serial.send(cmd)

    # ---- Developer -------------------------------------------------------
    def build_dev(self, f):
        cf = ttk.Frame(f)
        cf.pack(fill="x", side="bottom", pady=(4, 0))
        ttk.Label(cf, text=T("Polecenie do podłączonego urządzenia:")).pack(side="left")
        self.dcmd = ttk.Entry(cf, font=("Consolas", 10))
        self.dcmd.insert(0, "get_stats_packets()")
        self.dcmd.pack(side="left", fill="x", expand=True, padx=4)
        run = lambda: self.core.call(self.core.do_local_cmd(self.dcmd.get().strip()))  # noqa: E731
        self.dcmd.bind("<Return>", lambda e: run())
        ttk.Button(cf, text=T("Wykonaj"), command=run).pack(side="left")
        ttk.Button(cf, text=T("Folder danych"), command=lambda: os.startfile(DATA)).pack(side="left", padx=4)
        pw = ttk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=True)
        g1 = ttk.LabelFrame(pw, text=T("Pakiety radiowe"), padding=4)
        g2 = ttk.LabelFrame(pw, text=T("Zdarzenia"), padding=4)
        self.plog, self.elog = LogView(g1, height=8), LogView(g2, height=8)
        self.plog.frame.pack(fill="both", expand=True)
        self.elog.frame.pack(fill="both", expand=True)
        pw.add(g1, weight=1)
        pw.add(g2, weight=1)

    # ---- Settings --------------------------------------------------------
    def build_settings(self, f):
        cfg = self.core.cfg
        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Label(row, text=T("Język / Language:")).pack(side="left")
        lang = ttk.Combobox(row, state="readonly", width=12, values=["Polski", "English"])
        lang.current(0 if cfg["lang"] == "pl" else 1)
        lang.pack(side="left", padx=6)
        note = ttk.Label(f, text="", foreground="#b45f06")
        note.pack(anchor="w")

        def set_language(_e):
            cfg["lang"] = "pl" if lang.current() == 0 else "en"
            save_config(cfg)
            note.config(text=T("Zmiana języka zadziała po ponownym uruchomieniu aplikacji."))
        lang.bind("<<ComboboxSelected>>", set_language)

        def toggle(key, var):
            cfg[key] = var.get()
            save_config(cfg)
        for key, text in (("autoconnect", T("Łącz automatycznie z ostatnim urządzeniem przy starcie")),
                          ("sound", T("Powiadamiaj dźwiękiem o nowych wiadomościach"))):
            v = tk.BooleanVar(value=cfg[key])
            ttk.Checkbutton(f, text=text, variable=v, command=lambda k=key, v=v: toggle(k, v)).pack(anchor="w", pady=(8, 0))
        va = tk.BooleanVar(value=corem.autostart_path().exists())
        ttk.Checkbutton(f, text=T("Uruchamiaj razem z Windows"), variable=va,
                        command=lambda: corem.set_autostart(va.get())).pack(anchor="w", pady=(8, 0))
        ttk.Label(f, text=T("Zapamiętane urządzenia:")).pack(anchor="w", pady=(16, 2))
        self.saved_list = tk.Listbox(f, height=6, width=50, exportselection=False)
        self.saved_list.pack(anchor="w")

        def forget():
            sel = self.saved_list.curselection()
            if sel:
                del cfg["devices"][sel[0]]
                cfg["last_device"] = -1
                save_config(cfg)
                self.fill_saved()
        ttk.Button(f, text=T("Usuń z listy"), command=forget).pack(anchor="w", pady=4)
        ttk.Label(f, text=f"{APP_NAME} · {T('Wersja {v}', v=VERSION)} · MIT · github.com/qbarteczek/meshcore-desktop",
                  foreground="#777").pack(anchor="w", side="bottom")

    def show_help(self):
        win = tk.Toplevel(self.root)
        win.title(f"{APP_NAME} - {T('Pomoc')}")
        win.geometry("760x600")
        f, txt = scrolled(win, tk.Text, wrap="word", font=("Segoe UI", 10), padx=14, pady=10)
        f.pack(fill="both", expand=True)
        txt.tag_config("h", font=("Segoe UI", 12, "bold"), spacing1=10, spacing3=4)
        path = HERE / f"help_{i18n.LANG}.md"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                txt.insert("end", line.lstrip("# ") + "\n", "h")
            else:
                txt.insert("end", line + "\n")
        txt.config(state="disabled")

    # ---- event pump ------------------------------------------------------
    def poll(self):
        try:
            while True:
                ev = self.uiq.get_nowait()
                kind = ev[0]
                if kind == "status":
                    self.status.config(text=("🟢 " if ev[2] else "⚪ ") + ev[1])
                elif kind == "toast":
                    self.toast.config(text=time.strftime("%H:%M:%S  ") + ev[1])
                elif kind == "msg":
                    if ev[1] == self.conv:
                        self.core.unread.discard(ev[1])
                        self.show_conv()
                    self.fill_convs()
                    if ev[2]:                       # a new incoming message
                        self.toast.config(text=time.strftime("%H:%M:%S  ") + T("Nowa wiadomość: {name}", name=ev[2]["sender"]))
                        if self.core.cfg["sound"]:
                            self.root.bell()
                    n = len(self.core.unread)
                    self.root.title(f"({n}) {APP_NAME}" if n else APP_NAME)
                elif kind == "contacts":
                    self.fill_convs()
                    self.fill_contacts()
                    self.fill_device()
                    self.fill_saved()
                elif kind == "channels":
                    self.fill_channels()
                    self.fill_convs()
                elif kind == "info":
                    self.fill_device()
                elif kind == "link":
                    self.add_link_row(ev[1])
                elif kind == "remote":
                    self.rlog.add(ev[1])
                elif kind == "serial":
                    self.slog.add(ev[1])
                elif kind == "packet":
                    self.plog.add(ev[1])
                elif kind == "event":
                    self.elog.add(ev[1])
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    def tick(self):
        c = self.core
        if c.link_busy:
            txt = T("test w toku…")
        elif c.cfg["link_enabled"]:
            left = max(0, int(c.next_link - time.time()))
            txt = T("następny za {m} min {s:02d} s", m=left // 60, s=left % 60)
        else:
            txt = T("automat wyłączony")
        self.next_lbl.config(text=txt)
        self.root.after(1000, self.tick)
