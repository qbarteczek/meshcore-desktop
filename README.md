# MeshCore Desktop

A simple Windows desktop tool for [MeshCore](https://meshcore.co.uk) radio mesh devices — messaging, device
configuration, remote management of repeaters, link testing and developer diagnostics.
Interface in **English and Polish** (chosen in the installer, switchable in Settings).

> **Status: developer preview (0.2.0-dev).** It works with the author's hardware, but large parts are lightly tested —
> see [Tested / not tested](#tested--not-tested). This is a community project, not an official MeshCore product.

🇵🇱 [Wersja polska poniżej](#meshcore-desktop--po-polsku)

![icon](mcd/app.png)

## Features

| Tab | What it does |
|---|---|
| **Messages** | Private chats with delivery confirmation (ACK) and channel chats; per-device history; unread markers and sound. |
| **Contacts** | Full contact list with type, last-heard time and route; sort and filter; reset path, remove, copy key; *Clean up* removes contacts not heard for N days (handy when the list is full). |
| **Remote management** | Log in to a repeater, room server or sensor over the mesh; status, telemetry, neighbours; free-form CLI commands with quick buttons. |
| **Link test** | Sends a message to a chosen contact on a schedule and logs ACK, time-to-ACK, route, RSSI/SNR/noise and battery to CSV. Can read receiver-side SNR/RSSI from an optional bridge (`traces.json`). |
| **Device** | Name, position, TX power, LoRa radio parameters, Bluetooth PIN, channels, contact auto-add, advert, clock sync, reboot, JSON backup/restore. |
| **USB console** | Plain text console for a repeater / room server / sensor connected by USB cable. |
| **Developer** | Live radio packet log, library event log, and a command box that runs any `meshcore` library call. |
| **Settings** | Language, auto-connect, notification sound, start with Windows, saved devices. |

Connections: **Bluetooth LE** (with automatic PIN pairing), **USB serial** and **TCP/Wi-Fi** companion devices.
The full user guide is built in (**Help** button) and available as [help_en.md](mcd/help_en.md) / [help_pl.md](mcd/help_pl.md).

## Install

**Installer (recommended):** download `MeshCoreDesktop-Setup-x.y.z.exe` from
[Releases](https://github.com/qbarteczek/meshcore-desktop/releases), run it and pick the language on the first page.
It installs for the current user only — no administrator rights needed.

**From source** (Windows 10/11, Python 3.11+):

```powershell
git clone https://github.com/qbarteczek/meshcore-desktop
cd meshcore-desktop
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw meshcore_desktop.py
```

**Build the installer yourself:** install `requirements-dev.txt` and [Inno Setup 6](https://jrsoftware.org/isinfo.php),
then run `installer\build.ps1`. The result lands in `dist\`.

## Good to know

- A MeshCore device accepts **one connection at a time** — disconnect the phone app first.
- On Windows a Bluetooth bond made without a PIN is rejected by MeshCore ("Insufficient Authentication").
  The app pairs with the PIN itself; the MeshCore default is `123456`.
- Settings, history and logs live in `%APPDATA%\MeshCoreDesktop` (Developer → *Data folder*). Nothing is sent anywhere.
- The link test's optional *channel probe* posts a message to a channel every interval. Be considerate on public channels.

## Tested / not tested

| Area | State |
|---|---|
| BLE connect + PIN pairing, messages, contacts list, device info, channels list, link test, event log | tested on a Seeed XIAO nRF52 companion, firmware v1.17.1, Windows 11 |
| USB-serial and TCP companion connections | implemented, **not tested** |
| Remote management (login, status, telemetry, neighbours, CLI) | implemented, **not tested** against a real repeater |
| USB text console | implemented, **not tested** |
| Changing radio parameters, PIN, channels; backup/restore; contact clean-up | implemented, **not tested** |

Bug reports and pull requests are welcome.

## Project layout

```
meshcore_desktop.py   entry point (single-instance lock, --tab N developer option)
mcd/core.py           background thread owning the device connection; all radio work
mcd/ui.py             tkinter interface
mcd/i18n.py           translations (Polish source strings → English)
mcd/help_*.md         built-in user guide
installer/            PyInstaller + Inno Setup build (language selection at install time)
```

How it fits together: the GUI never talks to the radio. It schedules coroutines on the core thread's asyncio loop
(`Core.call`) and receives results as tuples on a queue that the GUI polls. To add a language, add a dictionary next
to `EN` in `mcd/i18n.py`; to add a feature, add a `do_*` coroutine in `core.py` and a widget in `ui.py`.

## Credits and references

- **MeshCore** firmware and protocol — <https://github.com/meshcore-dev/MeshCore> (MIT).
- **meshcore_py** — the Python library this app is built on — <https://github.com/meshcore-dev/meshcore_py> (MIT).
- **bleak** — Bluetooth LE for Python — <https://github.com/hbldh/bleak> (MIT).
- **pyserial** — <https://github.com/pyserial/pyserial> (BSD-3-Clause).
- **PyWinRT** — Windows Runtime projections used for PIN pairing — <https://github.com/pywinrt/pywinrt> (MIT).
- Built with **PyInstaller** and **Inno Setup**.
- The application icon is original work, released under the same licence as the code.
- Written with the help of Claude Code (Anthropic).

"MeshCore" is the name of the upstream project; this tool is independent and not endorsed by its authors.

## Licence

[MIT](LICENSE)

---

# MeshCore Desktop – po polsku

Proste narzędzie na Windows do obsługi urządzeń sieci radiowej [MeshCore](https://meshcore.co.uk): rozmowy,
konfiguracja urządzenia, zdalne zarządzanie repeaterami, test łącza i diagnostyka dla deweloperów.
Interfejs po **polsku i angielsku** (wybór w instalatorze, zmiana w Ustawieniach).

> **Stan: wersja deweloperska (0.2.0-dev).** Działa ze sprzętem autora, ale spora część funkcji jest słabo
> przetestowana – patrz tabela [Tested / not tested](#tested--not-tested). To projekt społecznościowy, nie oficjalny produkt MeshCore.

## Funkcje

- **Wiadomości** – rozmowy prywatne z potwierdzeniem doręczenia i kanały; historia osobno dla każdego urządzenia.
- **Kontakty** – pełna lista z typem, czasem ostatniego kontaktu i trasą; sortowanie, filtr, reset trasy, usuwanie,
  „Porządki” (usuwanie kontaktów niesłyszanych od N dni).
- **Zdalne zarządzanie** – logowanie do repeatera, serwera pokoju lub czujnika przez sieć radiową; status, telemetria,
  sąsiedzi, polecenia CLI.
- **Test łącza** – cykliczna wiadomość do wybranego kontaktu, zapis ACK, czasu, trasy, sygnału i baterii do CSV.
- **Urządzenie** – nazwa, pozycja, moc, parametry radia, PIN Bluetooth, kanały, kopia i przywracanie ustawień.
- **Konsola USB** – tekstowa konsola repeatera podłączonego kablem.
- **Deweloper** – podgląd pakietów radiowych i zdarzeń, wywoływanie dowolnych komend biblioteki `meshcore`.
- **Ustawienia** – język, autołączenie, dźwięk, start z Windows.

Połączenia: **Bluetooth LE** (parowanie z PIN-em robi aplikacja), **USB** i **TCP/Wi-Fi**.
Pełna instrukcja jest w aplikacji (przycisk **Pomoc**) i w pliku [help_pl.md](mcd/help_pl.md).

## Instalacja

**Instalator:** pobierz `MeshCoreDesktop-Setup-x.y.z.exe` z
[Releases](https://github.com/qbarteczek/meshcore-desktop/releases), uruchom i wybierz język na pierwszej stronie.
Instaluje się tylko dla bieżącego użytkownika, bez uprawnień administratora.

**Ze źródeł** – polecenia jak w części angielskiej (Python 3.11+, `pip install -r requirements.txt`,
`pythonw meshcore_desktop.py`).

## Warto wiedzieć

- Urządzenie MeshCore obsługuje **jedno połączenie naraz** – najpierw rozłącz aplikację w telefonie.
- Domyślny PIN Bluetooth MeshCore to `123456`.
- Ustawienia, historia i dzienniki są w `%APPDATA%\MeshCoreDesktop`. Aplikacja niczego nigdzie nie wysyła.
- „Sonda na kanale” w teście łącza wysyła wiadomość na kanał przy każdym teście – na kanałach publicznych używaj z umiarem.

Licencja: [MIT](LICENSE). Źródła i podziękowania: sekcja [Credits and references](#credits-and-references).
