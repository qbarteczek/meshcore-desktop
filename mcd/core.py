"""Core: background thread that owns the device connection.

The GUI never touches the radio directly. It schedules coroutines on this thread's asyncio loop
with ``Core.call()`` and receives results as tuples on a ``queue.Queue`` (see ``Core.ui``).
"""
import asyncio
import csv
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

from meshcore import EventType, MeshCore

from .i18n import T, set_lang

APP_NAME = "MeshCore Desktop"
VERSION = "0.2.0-dev"
SRC = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("APPDATA", str(SRC))) / "MeshCoreDesktop"
DATA.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA / "config.json"
LINK_CSV = DATA / "link_test.csv"
LOG_FILE = DATA / "app.log"
INSTALL_INI = DATA / "install.ini"   # written by the installer: language picked during setup

DEFAULTS = {
    "lang": "",
    "devices": [],            # saved connections: {"label", "kind": ble|serial|tcp, ...}
    "last_device": -1,
    "autoconnect": True,
    "sound": True,
    "target_name": "",
    "link_enabled": False,
    "link_interval_min": 60,
    "probe_enabled": False,
    "probe_channel": "#test",
    "traces_url": "",
    "counter": 0,
}
LINK_COLS = ["time", "device", "target", "nr", "result", "ack_s", "route", "rssi", "snr", "noise", "bat_V",
             "srv_seen", "srv_snr", "srv_rssi", "srv_hops"]
TYPE_NAMES = {1: "klient", 2: "repeater", 3: "serwer pokoju", 4: "czujnik"}
NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"   # Nordic UART service used by MeshCore companions


def log(msg):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def system_lang():
    try:
        import ctypes
        return "pl" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x15 else "en"
    except Exception:  # noqa: BLE001
        return "en"


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except ValueError:
            pass
    if INSTALL_INI.exists():          # language chosen in the installer wins once, then the file is consumed
        for line in INSTALL_INI.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("lang="):
                cfg["lang"] = line.split("=", 1)[1].strip()
        INSTALL_INI.unlink()
    if cfg["lang"] not in ("pl", "en"):
        cfg["lang"] = system_lang()
    set_lang(cfg["lang"])
    save_config(cfg)
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def device_label(dev):
    if dev.get("label"):
        return dev["label"]
    if dev["kind"] == "ble":
        return dev["address"]
    if dev["kind"] == "serial":
        return dev["port"]
    return f"{dev['host']}:{dev['port']}"


async def ble_scan(timeout=12):
    """Return [(name, address, rssi)] of MeshCore companions advertising over BLE."""
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    out = []
    for addr, (dev, adv) in found.items():
        name = adv.local_name or dev.name or ""
        if "meshcore" in name.lower() or NUS_UUID in [u.lower() for u in adv.service_uuids]:
            out.append((name, addr, adv.rssi))
    return sorted(out, key=lambda x: -x[2])


async def ble_pair(addr, pin):
    """Pair with a PIN through WinRT.

    bleak on Windows cannot supply a PIN, and a bond made without one is rejected by MeshCore with
    "GATT Insufficient Authentication". Any existing bond is removed first.
    """
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import (DevicePairingKinds, DevicePairingProtectionLevel,
                                                   DevicePairingResultStatus)
    num = int(addr.replace(":", ""), 16)
    dev = await BluetoothLEDevice.from_bluetooth_address_async(num)
    if dev is None:
        return "NOT_FOUND"
    pairing = dev.device_information.pairing
    if pairing.is_paired:
        await pairing.unpair_async()
        await asyncio.sleep(3)
        dev = await BluetoothLEDevice.from_bluetooth_address_async(num)
        pairing = dev.device_information.pairing

    def on_request(sender, args):
        if args.pairing_kind == DevicePairingKinds.PROVIDE_PIN:
            args.accept_with_pin(pin)
        else:
            args.accept()

    custom = pairing.custom
    token = custom.add_pairing_requested(on_request)
    try:
        res = await custom.pair_with_protection_level_async(
            DevicePairingKinds.PROVIDE_PIN | DevicePairingKinds.CONFIRM_ONLY,
            DevicePairingProtectionLevel.ENCRYPTION_AND_AUTHENTICATION)
    finally:
        custom.remove_pairing_requested(token)
    return DevicePairingResultStatus(res.status).name


class Core(threading.Thread):
    def __init__(self, uiq):
        super().__init__(daemon=True)
        self.uiq = uiq
        self.cfg = load_config()
        self.mc = None
        self.connected = False
        self.want = None            # device dict we should be connected to (None = stay offline)
        self.dev_key = ""           # public key prefix of the connected device (names its history file)
        self.channels = {}          # idx -> name
        self.msgs = {}              # conversation key -> list of messages
        self.unread = set()
        self.info = {}
        self.next_link = self._first_link_time()
        self.link_busy = False
        self.loop = None
        self.change = None

    # ---- helpers ---------------------------------------------------------
    def _first_link_time(self):
        """Keep the test cadence across restarts: continue from the last logged test, not from app start."""
        soonest = time.time() + 60
        try:
            last = LINK_CSV.read_text(encoding="utf-8-sig").strip().splitlines()[-1].split(";")[0]
            due = time.mktime(time.strptime(last, "%Y-%m-%d %H:%M:%S")) + int(self.cfg["link_interval_min"]) * 60
            return max(soonest, due)
        except (OSError, ValueError, IndexError):
            return soonest

    def ui(self, *ev):
        self.uiq.put(ev)

    def call(self, coro):
        return asyncio.run_coroutine_threadsafe(self._guard(coro), self.loop)

    async def _guard(self, coro):
        try:
            return await coro
        except Exception as e:  # noqa: BLE001 - report to the user instead of killing the thread
            log(f"error: {e!r}")
            self.ui("toast", T("Błąd: {err}", err=e))

    def _need(self):
        if not self.connected:
            raise RuntimeError(T("brak połączenia z urządzeniem"))

    @property
    def my_name(self):
        return (self.mc.self_info or {}).get("name", "?") if self.mc else "?"

    def history_file(self):
        return DATA / f"history_{self.dev_key}.jsonl"

    def _load_history(self):
        self.msgs, self.unread = {}, set()
        f = self.history_file()
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                self.msgs.setdefault(m.pop("conv"), []).append(m)

    def _store(self, conv, m):
        with self.history_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps({"conv": conv, **m}, ensure_ascii=False) + "\n")

    def contact_by_prefix(self, prefix):
        for k, c in (self.mc.contacts if self.mc else {}).items():
            if k.startswith(prefix):
                return c
        return None

    def find_contact(self, name):
        """Exact name first, otherwise the first contact whose name starts with it."""
        if not name:
            return None
        cs = list(self.mc.contacts.values())
        return next((c for c in cs if c["adv_name"] == name), None) or \
            next((c for c in cs if c["adv_name"].startswith(name)), None)

    # ---- connection ------------------------------------------------------
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.change = asyncio.Event()
        self.loop.run_until_complete(self.main())

    async def do_connect(self, dev):
        self.want = dev
        self.change.set()

    async def do_disconnect(self):
        self.want = None
        self.change.set()

    async def _open(self, dev):
        if dev["kind"] == "serial":
            return await MeshCore.create_serial(dev["port"], int(dev.get("baud", 115200)))
        if dev["kind"] == "tcp":
            return await MeshCore.create_tcp(dev["host"], int(dev["port"]))
        try:
            return await MeshCore.create_ble(dev["address"])
        except Exception as e:  # noqa: BLE001
            if "Authentication" not in str(e) or not dev.get("pin"):
                raise
        self.ui("status", T("Parowanie Bluetooth z PIN-em…"), False)
        res = await ble_pair(dev["address"], dev["pin"])
        if res not in ("PAIRED", "ALREADY_PAIRED"):
            raise RuntimeError(T("Parowanie nieudane ({res}) - sprawdź PIN", res=res))
        return await MeshCore.create_ble(dev["address"])

    async def main(self):
        asyncio.ensure_future(self.link_scheduler())
        if self.cfg["autoconnect"] and 0 <= self.cfg["last_device"] < len(self.cfg["devices"]):
            self.want = self.cfg["devices"][self.cfg["last_device"]]
        while True:
            dev = self.want
            self.change.clear()
            if dev is None:
                self.ui("status", T("Niepołączono"), False)
                await self.change.wait()
                continue
            self.ui("status", T("Łączenie: {name}…", name=device_label(dev)), False)
            lost = asyncio.Event()
            try:
                self.mc = await self._open(dev)
                if self.mc is None:
                    raise RuntimeError(T("urządzenie nie odpowiada"))
                self.mc.subscribe(EventType.DISCONNECTED, lambda e: lost.set())
                self.mc.subscribe(EventType.CONTACT_MSG_RECV, self.on_dm)
                self.mc.subscribe(EventType.CHANNEL_MSG_RECV, self.on_chan)
                self.mc.subscribe(None, self.on_any)
                await self.mc.commands.set_time(int(time.time()))
                await self.mc.ensure_contacts()
                await self.refresh_channels()
                await self.refresh_info()
                self.dev_key = self.mc.self_info.get("public_key", "unknown")[:12]
                self._load_history()
                dev["label"] = self.my_name
                save_config(self.cfg)
                await self.mc.start_auto_message_fetching()
                self.connected = True
                self.ui("status", T("Połączono: {name}", name=self.my_name), True)
                self.ui("contacts")
                log(f"connected {device_label(dev)}")
                while not lost.is_set() and not self.change.is_set():
                    waits = [asyncio.ensure_future(lost.wait()), asyncio.ensure_future(self.change.wait())]
                    done, pending = await asyncio.wait(waits, timeout=300, return_when=asyncio.FIRST_COMPLETED)
                    for p in pending:
                        p.cancel()
                    if not done:                      # keep-alive doubles as a battery refresh
                        r = await self.mc.commands.get_bat()
                        if r.is_error():
                            break
                        self.info["bat"] = r.payload
                        self.ui("info")
            except Exception as e:  # noqa: BLE001
                log(f"connect: {e!r}")
                self.ui("status", T("Brak połączenia: {err}", err=str(e)[:80]), False)
            self.connected = False
            if self.mc:
                try:
                    await asyncio.wait_for(self.mc.disconnect(), 10)
                except Exception:  # noqa: BLE001
                    pass
            self.mc = None
            self.ui("contacts")
            if self.want is dev and not self.change.is_set():   # unexpected drop: retry after a pause
                if lost.is_set():
                    self.ui("status", T("Rozłączono, ponawiam…"), False)
                try:
                    await asyncio.wait_for(self.change.wait(), 15)
                except asyncio.TimeoutError:
                    pass

    async def refresh_channels(self):
        chans = {}
        for i in range(40):
            r = await self.mc.commands.get_channel(i)
            if r.is_error():
                break
            if r.payload.get("channel_name"):
                chans[i] = r.payload["channel_name"]
        self.channels = chans
        self.ui("channels")

    async def refresh_info(self):
        await self.mc.commands.send_appstart()
        info = {"self": dict(self.mc.self_info)}
        for key, cmd in (("dev", self.mc.commands.send_device_query), ("bat", self.mc.commands.get_bat),
                         ("radio", self.mc.commands.get_stats_radio), ("core", self.mc.commands.get_stats_core)):
            r = await cmd()
            info[key] = {} if r.is_error() else r.payload
        self.info = info
        self.ui("info")

    # ---- incoming events -------------------------------------------------
    def _add(self, conv, m, unread=True):
        self.msgs.setdefault(conv, []).append(m)
        if unread:
            self.unread.add(conv)
        self.ui("msg", conv, m if unread else None)

    def on_dm(self, ev):
        p = ev.payload
        c = self.contact_by_prefix(p["pubkey_prefix"])
        name = c["adv_name"] if c else p["pubkey_prefix"]
        if p.get("txt_type") == 1:                 # reply to a remote CLI command, not a chat message
            self.ui("remote", f"{name}> {p['text']}")
            return
        m = {"t": time.time(), "dir": "in", "sender": name, "text": p["text"],
             "snr": p.get("SNR"), "hops": p.get("path_len")}
        conv = "c:" + p["pubkey_prefix"]
        self._store(conv, m)
        self._add(conv, m)

    def on_chan(self, ev):
        p = ev.payload
        sender, sep, text = p["text"].partition(": ")
        if not sep:
            sender, text = "?", p["text"]
        m = {"t": time.time(), "dir": "in", "sender": sender, "text": text,
             "snr": p.get("SNR"), "hops": p.get("path_len")}
        conv = f"ch:{p['channel_idx']}"
        self._store(conv, m)
        self._add(conv, m)

    def on_any(self, ev):
        """Feed the Developer tab: decoded radio packets and every other library event."""
        p = ev.payload
        if ev.type == EventType.RX_LOG_DATA and isinstance(p, dict):
            self.ui("packet", "{}  SNR {:>6}  RSSI {:>5}  type {:<3} route {:<2} hops {:<2} len {:<4} path {}".format(
                time.strftime("%H:%M:%S"), p.get("snr", "?"), p.get("rssi", "?"), p.get("payload_type", "?"),
                p.get("route_type", "?"), p.get("path_len", "?"), p.get("payload_length", "?"), p.get("path", "")))
        elif ev.type not in (EventType.OK, EventType.NO_MORE_MSGS, EventType.NEXT_CONTACT, EventType.CONTACTS,
                             EventType.CHANNEL_INFO):   # CHANNEL_INFO carries channel keys - keep them out of logs
            self.ui("event", f"{time.strftime('%H:%M:%S')}  {ev.type.name}  {str(p)[:300]}")

    # ---- messaging -------------------------------------------------------
    async def do_send(self, conv, text):
        self._need()
        m = {"t": time.time(), "dir": "out", "sender": self.my_name, "text": text, "st": "…"}
        self._add(conv, m, unread=False)
        if conv.startswith("ch:"):
            r = await self.mc.commands.send_chan_msg(int(conv[3:]), text)
            m["st"] = T("błąd") if r.is_error() else T("wysłano")
        else:
            c = self.contact_by_prefix(conv[2:])
            if c is None:
                m["st"] = T("brak kontaktu")
            else:
                r = await self.mc.commands.send_msg_with_retry(c, text, max_attempts=3,
                                                               max_flood_attempts=2, flood_after=2)
                m["st"] = T("✓ doręczono") if r is not None else T("✗ brak potwierdzenia")
        self._store(conv, m)
        self.ui("msg", conv, None)

    # ---- link test -------------------------------------------------------
    async def link_scheduler(self):
        while True:
            await asyncio.sleep(5)
            if self.cfg["link_enabled"] and self.want and time.time() >= self.next_link and not self.link_busy:
                # short BLE drop: give the link 5 minutes to return before logging a failed test
                if self.connected or time.time() >= self.next_link + 300:
                    await self._guard(self.do_link_test())

    def schedule_next(self):
        self.next_link = time.time() + max(1, int(self.cfg["link_interval_min"])) * 60

    async def do_link_test(self):
        if self.link_busy:
            return
        self.link_busy = True
        self.schedule_next()
        row = dict.fromkeys(LINK_COLS, "")
        row["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        row["target"] = self.cfg["target_name"]
        try:
            if not self.connected:
                row["result"] = T("brak połączenia")
                return
            row["device"] = self.my_name
            target = self.find_contact(self.cfg["target_name"])
            if target is None:
                row["result"] = T("brak kontaktu")
                return
            self.cfg["counter"] += 1
            save_config(self.cfg)
            row["nr"] = self.cfg["counter"]
            row["target"] = target["adv_name"]
            self.ui("toast", T("Test łącza nr {n}: wysyłam do {name}…", n=row["nr"], name=target["adv_name"]))
            text = f"QT{row['nr']} {time.strftime('%H:%M')}"
            conv = "c:" + target["public_key"][:12]
            m = {"t": time.time(), "dir": "out", "sender": self.my_name, "text": text, "st": "…"}
            self._add(conv, m, unread=False)
            t0 = time.time()
            r = await self.mc.commands.send_msg_with_retry(target, text, max_attempts=3,
                                                           max_flood_attempts=2, flood_after=2)
            if r is not None:
                row["result"], row["ack_s"] = "ACK", f"{time.time() - t0:.1f}"
                m["st"] = T("✓ doręczono")
            else:
                row["result"] = T("brak ACK")
                m["st"] = T("✗ brak potwierdzenia")
            self._store(conv, m)
            self.ui("msg", conv, None)
            await self.mc.commands.get_contacts()
            target = self.contact_by_prefix(target["public_key"][:12]) or target
            pl = target.get("out_path_len", -1)
            row["route"] = "flood" if pl < 0 else pl
            r = await self.mc.commands.get_stats_radio()
            if not r.is_error():
                row["rssi"], row["snr"] = r.payload.get("last_rssi"), r.payload.get("last_snr")
                row["noise"] = r.payload.get("noise_floor")
            r = await self.mc.commands.get_bat()
            if not r.is_error():
                row["bat_V"] = f"{r.payload['level'] / 1000:.2f}"
            # Receiver side: an optional bridge publishes what the target heard, but only for channel messages.
            if self.cfg["traces_url"]:
                probe = None
                if self.cfg["probe_enabled"]:
                    idx = next((i for i, n in self.channels.items() if n == self.cfg["probe_channel"]), None)
                    if idx is not None:
                        probe = text
                        await self.mc.commands.send_chan_msg(idx, probe)
                await self._check_server(row, probe)
        finally:
            new = not LINK_CSV.exists()
            with LINK_CSV.open("a", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, LINK_COLS, delimiter=";")
                if new:
                    w.writeheader()
                w.writerow(row)
            self.link_busy = False
            self.ui("link", row)
            log(f"link test: {row}")

    async def _check_server(self, row, probe):
        def fetch():
            with urllib.request.urlopen(self.cfg["traces_url"], timeout=8) as r:
                return json.load(r)
        for i in range(7 if probe else 1):
            if i:
                await asyncio.sleep(15)
            try:
                d = await self.loop.run_in_executor(None, fetch)
            except Exception:  # noqa: BLE001
                row["srv_seen"] = T("serwer niedostępny")
                return
            if not probe:
                row["srv_seen"] = "-"
                return
            for t in d.get("traces", []):
                if t.get("text") == probe:
                    row["srv_seen"] = T("tak")
                    row["srv_snr"], row["srv_rssi"], row["srv_hops"] = t.get("snr"), t.get("rssi"), t.get("path_len")
                    return
        row["srv_seen"] = T("nie")

    # ---- device configuration -------------------------------------------
    async def _done(self, r, what):
        self.ui("toast", f"{what}: {T('BŁĄD') + ' ' + str(r.payload) if r.is_error() else 'OK'}")
        return not r.is_error()

    async def do_set_basic(self, name, lat, lon, txp):
        self._need()
        s = self.mc.self_info
        if name != s.get("name"):
            await self._done(await self.mc.commands.set_name(name), T("Nazwa"))
        if (lat, lon) != (s.get("adv_lat"), s.get("adv_lon")):
            await self._done(await self.mc.commands.set_coords(lat, lon), T("Pozycja"))
        if txp != s.get("tx_power"):
            await self._done(await self.mc.commands.set_tx_power(txp), T("Moc nadawania"))
        await self.refresh_info()

    async def do_set_radio(self, freq, bw, sf, cr):
        self._need()
        await self._done(await self.mc.commands.set_radio(freq, bw, sf, cr), T("Radio (wymaga restartu)"))
        await self.refresh_info()

    async def do_set_pin(self, pin):
        self._need()
        await self._done(await self.mc.commands.set_devicepin(pin), T("PIN Bluetooth (po restarcie sparuj ponownie)"))

    async def do_set_autoadd(self, auto):
        self._need()
        await self._done(await self.mc.commands.set_manual_add_contacts(not auto), T("Dodawanie kontaktów"))
        await self.refresh_info()

    async def do_advert(self, flood):
        self._need()
        await self._done(await self.mc.commands.send_advert(flood), T("Rozgłoszenie"))

    async def do_sync_time(self):
        self._need()
        await self._done(await self.mc.commands.set_time(int(time.time())), T("Zegar"))

    async def do_reboot(self):
        self._need()
        await self.mc.commands.reboot()
        self.ui("toast", T("Restart urządzenia - połączenie wróci za chwilę"))

    async def do_refresh(self):
        self._need()
        await self.mc.commands.get_contacts()
        await self.refresh_channels()
        await self.refresh_info()
        self.ui("contacts")
        self.ui("toast", T("Odświeżono"))

    async def do_set_channel(self, idx, name, secret):
        self._need()
        await self._done(await self.mc.commands.set_channel(idx, name, secret), f"{T('Kanał')} {idx}")
        await self.refresh_channels()

    async def do_backup(self, path):
        """Save identity-free settings, channels (with keys) and the contact list to a JSON file."""
        self._need()
        chans = []
        for i in self.channels:
            p = (await self.mc.commands.get_channel(i)).payload
            sec = p.get("channel_secret", b"")
            chans.append({"idx": i, "name": p["channel_name"], "secret": sec.hex() if isinstance(sec, bytes) else str(sec)})
        data = {"app": APP_NAME, "version": VERSION, "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
                "self": self.info.get("self", {}), "device": self.info.get("dev", {}),
                "channels": chans, "contacts": list(self.mc.contacts.values())}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        self.ui("toast", T("Zapisano kopię: {path}", path=path))

    async def do_restore(self, path):
        """Restore name, position, TX power and channels. Radio parameters and contacts are left alone."""
        self._need()
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        s = d.get("self", {})
        await self.do_set_basic(s.get("name", self.my_name), s.get("adv_lat", 0.0), s.get("adv_lon", 0.0),
                                s.get("tx_power", self.mc.self_info.get("tx_power")))
        for ch in d.get("channels", []):
            await self.mc.commands.set_channel(ch["idx"], ch["name"], bytes.fromhex(ch["secret"]))
        await self.refresh_channels()
        self.ui("toast", T("Przywrócono ustawienia z kopii"))

    # ---- contacts --------------------------------------------------------
    async def do_reset_path(self, prefix):
        self._need()
        await self._done(await self.mc.commands.reset_path(self.contact_by_prefix(prefix)), T("Reset trasy"))
        await self.mc.commands.get_contacts()
        self.ui("contacts")

    async def do_remove_contacts(self, prefixes):
        self._need()
        n = 0
        for p in prefixes:
            c = self.contact_by_prefix(p)
            if c is not None and not (await self.mc.commands.remove_contact(c)).is_error():
                n += 1
        await self.mc.commands.get_contacts()
        self.ui("contacts")
        self.ui("toast", T("Usunięto kontaktów: {n}", n=n))

    # ---- remote management (repeaters, room servers, sensors over the mesh) ----
    def _rout(self, text):
        self.ui("remote", f"{time.strftime('%H:%M:%S')}  {text}")

    async def do_remote_login(self, prefix, pwd):
        self._need()
        c = self.contact_by_prefix(prefix)
        self._rout(T("Logowanie do {name}…", name=c["adv_name"]))
        r = await self.mc.commands.send_login_sync(c, pwd, min_timeout=15)
        self._rout(T("Zalogowano") if r is not None else T("Logowanie nieudane (złe hasło albo brak odpowiedzi)"))

    async def do_remote_query(self, prefix, what):
        self._need()
        c = self.contact_by_prefix(prefix)
        self._rout(T("Pytam {name} o: {what}…", name=c["adv_name"], what=what))
        cmds = self.mc.commands
        if what == "status":
            res = await cmds.req_status_sync(c, min_timeout=15)
        elif what == "telemetry":
            res = await cmds.req_telemetry_sync(c, min_timeout=15)
        else:
            res = await cmds.fetch_all_neighbours(c, min_timeout=15)
            if res:
                names = {k[:8]: v["adv_name"] for k, v in self.mc.contacts.items()}
                for n in res.get("neighbours", []):
                    n["name"] = names.get(str(n.get("pubkey", ""))[:8], "")
        if res is None:
            self._rout(T("brak odpowiedzi"))
        else:
            self._rout(json.dumps(res, ensure_ascii=False, indent=1, default=str))

    async def do_remote_cmd(self, prefix, cmd):
        self._need()
        c = self.contact_by_prefix(prefix)
        self._rout(f"{c['adv_name']}< {cmd}")
        r = await self.mc.commands.send_cmd(c, cmd)
        if r.is_error():
            self._rout(f"{T('BŁĄD')} {r.payload}")

    async def do_local_cmd(self, cmd):
        """Developer tab: run a Python expression against the library, e.g. ``get_bat()`` or ``send_advert(True)``."""
        self._need()
        res = eval("mc.commands." + cmd if not cmd.startswith("mc.") else cmd,  # noqa: S307 - local developer console
                   {"mc": self.mc, "EventType": EventType})
        if asyncio.iscoroutine(res):
            res = await res
        self.ui("event", f"> {cmd}\n{getattr(res, 'payload', res)}")


class SerialConsole:
    """Plain-text CLI of a repeater / room server / sensor plugged in over USB (not the companion protocol)."""

    def __init__(self, uiq):
        self.uiq = uiq
        self.ser = None

    @staticmethod
    def ports():
        from serial.tools import list_ports
        return [(p.device, p.description) for p in list_ports.comports()]

    def open(self, port, baud=115200):
        import serial
        self.close()
        self.ser = serial.Serial(port, baud, timeout=0.2)
        threading.Thread(target=self._reader, args=(self.ser,), daemon=True).start()

    def _reader(self, ser):
        buf = b""
        while ser.is_open:
            try:
                data = ser.read(256)
            except Exception:  # noqa: BLE001 - cable pulled
                break
            if data:
                buf += data
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    self.uiq.put(("serial", ln.decode("utf-8", "replace").rstrip("\r")))
            elif buf:
                self.uiq.put(("serial", buf.decode("utf-8", "replace")))
                buf = b""
        self.uiq.put(("serial", "--- " + T("Zamknięto port") + " ---"))

    def send(self, cmd):
        if self.ser and self.ser.is_open:
            self.ser.write(cmd.encode("utf-8") + b"\r")

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:  # noqa: BLE001
                pass
            self.ser = None


def autostart_path():
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup" / f"{APP_NAME}.lnk"


def set_autostart(enable):
    """Create or remove a Startup-folder shortcut (works for both the installed exe and a source checkout)."""
    lnk = autostart_path()
    if not enable:
        lnk.unlink(missing_ok=True)
        return
    if getattr(sys, "frozen", False):
        target, args = sys.executable, ""
    else:
        target = str(Path(sys.executable).with_name("pythonw.exe"))
        args = f'"{SRC / "meshcore_desktop.py"}"'
    import subprocess
    ps = (f"$l=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
          f"$l.TargetPath='{target}';$l.Arguments='{args}';$l.WorkingDirectory='{Path(target).parent}';$l.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False, creationflags=0x08000000)
