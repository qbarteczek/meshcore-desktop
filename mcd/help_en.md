# MeshCore Desktop – help

A Windows desktop tool for MeshCore radio mesh devices: messaging, configuration, remote management of repeaters and diagnostic tools.

# 1. Connecting to a device

Click “Connect…” at the top of the window and pick a transport:

• Bluetooth – click “Scan for devices”, select yours, enter the PIN (the MeshCore default is 123456; devices with a screen show their own) and click “Connect”. The app performs the PIN pairing itself.
• USB (serial port) – for devices running “companion USB” firmware. Pick the COM port.
• Network (TCP/Wi-Fi) – for devices running “companion Wi-Fi” firmware. Enter host and port (usually 5000).

A device accepts one connection at a time: disconnect the MeshCore phone app first.
Connected devices are remembered in the “Device:” list – selecting an entry reconnects.

# 2. Messages

The list on the left shows channels and the contacts you have already talked to. To write to someone new, type part of the name in “Find contact”.
Private messages show whether the recipient acknowledged them (“✓ delivered”). Channel messages have no acknowledgements.
A ● dot marks unread messages. History is stored separately for each device.

# 3. Contacts

The full contact list stored on the device, filterable by name and type (client, repeater, room server, sensor). Click a column header to sort.
“Clean up…” removes contacts not heard for a given number of days – useful when the list is full and the device stops accepting new ones. Contacts with message history and the link-test target are kept.

# 4. Remote management

Repeaters, room servers and sensors are configured over the radio mesh, through the connected device:
1. pick a node from the list (you can type part of its name),
2. enter the node's admin password and click “Log in”,
3. use “Status”, “Telemetry”, “Neighbours” or type a CLI command (e.g. “ver”, “get radio”, “set name …”).

Replies travel over the radio, so they may take ten or more seconds, or never arrive if the node is out of range.

# 5. Link test

Periodically sends a short message to a chosen contact and records whether it was acknowledged (ACK), how long it took, the route, and the sender's signal and battery voltage. Results go to a CSV file.
Optional: if a bridge on the receiving side publishes a traces.json file, the app reads the receiver-side SNR/RSSI from it. This needs the “channel probe”, an extra message on a chosen channel – use it sparingly on public channels.
The test only runs while the application is open and connected.

# 6. Device

Name, position, TX power, radio parameters, Bluetooth PIN and channels of the connected device.
Warning: wrong radio parameters cut the device off the mesh. “Back up settings…” saves settings, channels (with keys) and the contact list to a JSON file; “Restore from backup…” restores name, position, power and channels.

# 7. USB console

A repeater, room server or sensor connected by USB cable exposes a text command console. Pick the port, click “Open” and type commands (e.g. “ver”, “get radio”, “set tx 20”, “reboot”).
This is a separate connection – no companion device is needed.

# 8. Developer

Live view of received radio packets (SNR, RSSI, type, route) and of every library event. The command box runs any meshcore library command, e.g. get_bat(), get_stats_packets(), send_advert(True).
“Data folder” opens the directory with configuration, history and logs.

# 9. Settings

Language (Polish/English), auto-connect on start, notification sound, start with Windows, the list of saved devices.

# Troubleshooting

• “Connection failed … Insufficient Authentication” – wrong PIN. Reconnect through “Connect…” and enter the right one.
• The device does not show up in a scan – it is connected to a phone or switched off; disconnect the phone app.
• Messages are not acknowledged – the recipient is out of range; try “Reset path” in the Contacts tab.

# Licence and credits

MeshCore Desktop is free software under the MIT licence. It uses the meshcore (meshcore_py), bleak and pyserial libraries. It is not an official MeshCore product.
Source code: https://github.com/qbarteczek/meshcore-desktop
