## Table of Contents

- [Introduction](#introduction)
- [Hardware setup](#hardware-setup)
- [Software setup](#software-setup)
  - [Installing the can327 kernel module](#installing-the-can327-kernel-module)
  - [Installing the CANBUS tools](#installing-the-canbus-tools)
- [Setting up the Bluetooth connection](#setting-up-the-bluetooth-connection)
- [Setting up the CANBUS](#setting-up-the-canbus)
- [Testing the setup](#testing-the-setup)
- [Closing the connection](#closing-the-connection)
- [Troubleshooting](#troubleshooting)
  - [Checking that the OBDII device is working](#checking-that-the-obdii-device-is-working)
  - [Monitoring the bluetooth traffic](#monitoring-the-bluetooth-traffic)
  - [Watch the kernel messages](#watch-the-kernel-messages)

## Introduction

This is a short writeup of the steps needed to connect an OBDII
bluetooth adapter to a Raspberry Pi4. The process should be very
similar on a regular PC running Linux as long as it has a working
bluetooth module.

_NOTE1_: This writeup only concerns the process of getting the hardware
communication going. It is not a comprehensive guide to CANBUS nor
how to hack a car.

_NOTE2_: Modern cars do not send the CANBUS traffic to the diagnostic port, so it is in most cases not possible to sniff the bus traffic using this interface. One can use UDS (Unified Diagnostic Services) to talk to the car through the OBDII interface. A good starting point is the introductory material at [CarHacking on Reddit](https://www.reddit.com/r/CarHacking/) (and to join the friendly community there).

## Hardware setup

- A Raspberry Pi running Raspbian (Based on Debian 12 Bookworm).
- A OBDII bluetooth adapter (I'm using a VGATE Pro).
- A car with an OBDII port.

## Software setup

The kernel module `can327` needed for CAN communication to the ELM327 is not
included in the Raspbian Linux release and need to be compiled
separately. Using `dkms` one can automate this process and have the
module recompiled every time the kernel is upgraded.

### Installing the `can327` kernel module

To install a kernel module one needs the kernel headers and dkms:

```
sudo apt update
sudo apt install build-essential linux-headers-$(uname -r) dkms

```

Fetch `can327.c` from the kernel source tree. (it doesn't seem to change much so any recent version of the kernel source should do)

```
https://github.com/torvalds/linux/blob/master/drivers/net/can/can327.c
```

Copy it to the right place and create a dkms setup

```
sudo mkdir -p /usr/src/can327-1.0/
sudo cp can327.c /usr/src/can327-1.0/
```

Create the dkms config and Makefile in the above directory

`/usr/src/can327-1.0/Makefile`:

```
obj-m += can327.o

all:
        make -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules

clean:
        make -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean
```

(remember the tabs in the Makefile if you're copying this)

`/usr/src/can327-1.0/dkms.conf`:

```
PACKAGE_NAME="can327"
PACKAGE_VERSION="1.0"
BUILT_MODULE_NAME[0]="can327"
DEST_MODULE_LOCATION[0]="/kernel/drivers/net/can/"
AUTOINSTALL="yes"
```

Register the module with dkms, build and install it:

```
sudo dkms add -m can327 -v 1.0
sudo dkms build -m can327 -v 1.0
sudo dkms install -m can327 -v 1.0
```

If everything is correct you should now see something like

```
sudo dkms status
can327/1.0, 6.6.62+rpt-rpi-v8, aarch64: installed

```

and

```
modinfo can327
filename:       /lib/modules/6.6.62+rpt-rpi-v8/updates/dkms/can327.ko.xz
author:         Max Staudt <max@enpas.org>
license:        GPL
description:    ELM327 based CAN interface
alias:          tty-ldisc-30
srcversion:     7F50115BF9D717366AF765F
depends:        can-dev
name:           can327
vermagic:       6.6.62+rpt-rpi-v8 SMP preempt mod_unload modversions aarch64
sig_id:         PKCS#7
signer:         DKMS module signing key
sig_key:        51:9A:4B:23:34:63:5B:AE:0A:79:11:DF:7E:C0:AD:2E:D6:38:25:B5
sig_hashalgo:   sha512
signature:      08:60:D3:B3:93:7C:2D:BB:75:D1:FA:08:EC:E5:E7:5E:76:2F:1C:90:
                E6:9F:BE:33:55:E3:2F:C6:A8:68:8F:FF:BF:84:81:AB:52:0C:3B:2A:
                FA:1F:F3:62:A4:68:07:7B:B7:6A:DD:3E:F0:83:7A:79:4C:F0:15:6F:
                91:D6:56:64:C7:4D:C7:18:A4:0A:BC:0F:C8:53:E9:B0:AB:72:70:23:
                BC:3A:E2:45:41:8E:8D:33:C8:5F:6D:73:8F:97:93:EA:9F:C1:D3:78:
                6D:7E:1E:B0:BA:29:E6:9C:93:77:2F:F6:62:AA:B1:D0:C4:59:96:BA:
                B9:1A:DD:BE:97:02:48:D1:D2:B4:FC:63:A7:01:1C:AD:2F:BF:6A:D2:
                03:17:D8:B7:E3:FE:42:39:7C:5F:1E:F5:43:2A:33:C5:ED:4A:2D:11:
                B0:3B:9D:27:EB:4B:64:8E:92:97:BD:3C:9C:78:DE:46:62:B7:EC:95:
                5B:7E:F7:BD:54:EF:94:00:DB:89:87:AD:2C:B2:00:6D:B4:CE:99:4E:
                A0:55:AB:C6:18:F8:EA:E3:66:D3:CA:E1:0A:39:72:4A:05:C9:4B:27:
                30:07:85:A8:C9:3F:46:5F:39:97:BF:36:83:40:A1:15:2C:C1:E5:07:
                A9:9A:4E:2B:F6:78:52:80:79:C1:6E:A0:2C:5E:6D:93
```

### Installing the CANBUS tools

The kernel now has the neccessary modules for the CANBUS communication and we only need the userspace utils:

```
sudo apt install can-utils
```

## Setting up the Bluetooth connection

Raspbian includes all the tools needed for bluetooth connection so this is smooth sailing. Put the OBDII device into the diagnostic port in the car. (Many devices has an idle timeout to save power so you might have to reseat it if it has been sitting idle for a while)

Start scanning

```
$ bluetoothctl power on
Changing power on succeeded
$ bluetoothctl --timeout 5 scan on
Discovery started
[CHG] Controller DC:A6:32:34:62:E5 Discovering: yes
[NEW] Device 78:21:84:CF:ED:4A ZAP097907
[NEW] Device CB:EA:EF:A7:30:4F CB-EA-EF-A7-30-4F
[NEW] Device DE:52:BE:9C:16:2D TT214H BlueFrog
[NEW] Device 8C:79:F5:89:3F:EF 8C-79-F5-89-3F-EF
[NEW] Device C4:DE:E2:E1:E1:92 CAF-P583S-KEU
[NEW] Device 50:54:7B:81:2D:6F BM6
[NEW] Device D2:E0:2F:8D:53:6C IOS-Vlink
[NEW] Device 74:46:B3:54:5F:BD S6b01d8bf167b1aafC
```

In this case the device of interest is the one named IOS-Vlink.

```
$ bluetoothctl trust D2:E0:2F:8D:53:6C
$ bluetoothctl connect D2:E0:2F:8D:53:6C
```

It might ask for a PIN, usually it is 0000 or 1234. It should be documented in the setup guide.

If the connection is successful one must bind the device to a pty.

```
sudo /usr/bin/rfcomm bind rfcomm0 D2:E0:2F:8D:53:6C
```

## Setting up the CANBUS

The SocketCAN kernel interface is a standard way to communicate over the CANBUS and makes
programming communication very easy. It is included in the Raspbian build and works out of the box.

Connect the pty attached to `rfcomm0` to a line discipline

```
sudo ldattach --debug --speed 38400 --eightbits --noparity --onestopbit 30 /dev/rfcomm0
```

Now you have something that looks like a network device, `can0`. It needs to be configured before
you can talk to it

```
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000  listen-only off
sudo ip link set can0 up
```

## Testing the setup

Create to terminals: Run `candump can0` on the first and then the command

```
cansend can0 '7DF#0201010000000000'
```

on the second terminal. You should now see something like this on the first terminal running `candump`:

```
$ candump can0
  can0  7DF   [8]  02 01 01 00 00 00 00 00
  can0  7EE   [8]  06 41 01 00 04 00 00 AA
  can0  7EC   [8]  06 41 01 00 00 00 00 AA
  can0  5EA   [8]  06 41 01 00 04 00 00 AA
  can0  7EB   [8]  06 41 01 00 04 00 00 AA
  can0  74C   [8]  06 41 01 00 04 00 00 AA
  can0  7ED   [8]  06 41 01 00 04 00 00 AA
```

You have now a working connection to the car's CANBUS. The details in the answer will vary between car brands but if `candump` only shows one line the car has not responded. The first line is just the data from `cansend`.

## Closing the connection

Do most of the steps in reverse

```
$ sudo killall ldattach
$ sudo ip link set can0 down
$ sudo rfcomm unbind /dev/rfcomm0
$ bluetoothctl disconnect D2:E0:2F:8D:53:6C
$ bluetoothctl power off
```

## Troubleshooting

The chain of things that need to be connected is long and the cheap OBDII devices are flaky.

### Checking that the OBDII device is working.

Minicom can be used to talk directly to the device using AT-commands. After doing bind to `/dev/rfcomm0` and before running `ldattach` run

```
minicom -D /dev/rfcomm0
```

and try to type the command `ATZ` it should then respond with the ELM327 protocol number. Mine says `ELM 2.3`. Quit minicom with `Ctrl-A q` to quit without hanging up. If you use `Ctrl-A x` it will close the bluetooth connection.

### Monitoring the bluetooth traffic

Run `btmon` while trying cansend. If it shows activity the can traffic goes over the bluetooth connection and you have a healthy connection.

### Watch the kernel messages

If you see something like this the connection is not healthy

```
$ dmesg -T
[Sat Feb  1 14:10:19 2025] can0: Received illegal character 0a.
[Sat Feb  1 14:10:19 2025] can0: bus-off
[Sat Feb  1 14:10:19 2025] can0: ELM327 misbehaved. Blocking further communication.
[Sat Feb  1 14:24:39 2025] can0 (unregistered): can327 off rfcomm0.

```

Try to reconnect using `bluetoothctl`. You might have to rebind etc.

<!-- This is **bold** text, and this is _emphasized_ text. -->
