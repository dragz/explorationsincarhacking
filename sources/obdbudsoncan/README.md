# OBDb Python Examples

This directory contains Python scripts demonstrating how to work with OBDb signalset data and communicate with vehicles via CAN bus.

The most important scripts are `query_signalset.py` and `query_signal.py`. The others are mostly for testing the communication.

All scripts are created with heavy use of Claude Sonnet 4 and are therefore a bit overengineered...

## Prerequisites
A working canbus setup on a Linux pc, for instance as described in https://github.com/dragz/explorationsincarhacking/

### OBDb repos


Clone '.schemas' and your vehicle repositories in https://github.com/OBDb/.

```bash
mkdir OBDb
cd OBDb
git clone https://github.com/OBDb/.schemas
git clone https://github.com/OBDb/Hyundai-IONIQ-5
```


### Python Dependencies:
```bash
# Install all dependencies
pip install python-can udsoncan can-isotp

# Verify installations
python3 -c "import can; import udsoncan; import isotp; print('OK')"
```

## Configuration

You can change `config.txt` file to set default values and avoid specifying them in every command.


**Benefits:**
- Run `query_signal.py` and `query_signalset.py` without specifying `--signalset` every time
- Command-line arguments always override config defaults
- Makes scripts more convenient for regular use

## Scripts

### 1. query_vin.py
Query vehicle VIN (Vehicle Identification Number) via CAN bus using UDS protocol.

**Features:**
- UDS Service 0x22 (ReadDataByIdentifier)
- ISO-TP transport layer with automatic 8-byte padding
- Automatic response-id calculation (request-id + 8)
- Scan mode to try multiple common ECU addresses
- VIN decoding with proper filtering

**Usage:**
```bash
# Query VIN from specific ECU
python3 query_vin.py --request-id 0x7C7

# Query with custom response ID
python3 query_vin.py --request-id 0x7C7 --response-id 0x7CF

# Scan multiple ECUs for VIN
python3 query_vin.py --scan

# Query specific DID
python3 query_vin.py --request-id 0x7C7 --did 0xF190
```

**Dependencies:**
```bash
pip install python-can udsoncan can-isotp
```

---

### 2. query_did.py
Query any DID (Data Identifier) from the vehicle and display as hex string.

**Features:**
- Generic DID querying (not limited to VIN)
- Raw hex output display
- Optional ASCII decoding for text data
- Same reliable UDS/ISO-TP setup as query_vin.py

**Usage:**
```bash
# Query VIN (outputs as hex)
python3 query_did.py --did 0xF190 --request-id 0x7C7

# Query ECU serial number
python3 query_did.py --did 0xF18C --request-id 0x7C7

# Try ASCII decoding
python3 query_did.py --did 0xF190 --request-id 0x7C7 --ascii

# Increase timeout for slow ECUs
python3 query_did.py --did 0x0100 --request-id 0x7C7 --timeout 5.0
```

**Common DIDs:**
- `0xF190` - VIN (Vehicle Identification Number)
- `0xF187` - Vehicle Manufacturer Spare Part Number
- `0xF18A` - Vehicle Manufacturer ECU Software Number
- `0xF18C` - ECU Serial Number
- `0xF191` - ECU Hardware Version Number
- `0xF19E` - System Supplier ECU Software Number

---

### 3. query_signalset.py
Search and parse OBDb signalset JSON files to discover available commands and signals.

**Features:**
- Load and parse signalset JSON files
- Search commands by service type, PID, or CAN ID
- Display detailed signal information (format, range, units)
- List all available signals grouped by path
- Decode example responses

**Usage:**
```bash
# View signalset summary (uses config.txt default if configured)
python3 query_signalset.py

# Or specify signalset explicitly
python3 query_signalset.py -s ../Hyundai-IONIQ-5/signalsets/v3/default.json

# Search by service 0x22
python3 query_signalset.py --service 0x22

# Search by specific PID
python3 query_signalset.py -s ../Hyundai-IONIQ-5/signalsets/v3/default.json --service 0x22 --pid 0xE001

# Search by CAN ID
python3 query_signalset.py -s ../Hyundai-IONIQ-5/signalsets/v3/default.json --can-id 0x74C

# List all signals
python3 query_signalset.py -s ../Hyundai-IONIQ-5/signalsets/v3/default.json --list-signals

# Show verbose signal details
python3 query_signalset.py -s ../Hyundai-IONIQ-5/signalsets/v3/default.json --service 0x22 --pid 0xE001 --verbose
```

**Dependencies:**
Uses the OBDb Python modules from `.schemas/python`:
- `can.signals` - SignalSet, Command, Signal parsing
- `can.command_registry` - Command registry and decoding
- `signalsets.loader` - Signalset file loading utilities

---

### 4. query_signal.py
Query a specific signal from the vehicle by signal ID.

**Features:**
- Automatically finds signal in signalset
- Determines which command contains the signal
- Queries vehicle via UDS using the correct service/PID
- Decodes and displays just the requested signal value
- Auto-detects CAN IDs from signalset
- Info mode to show signal details without querying
uses config.txt default if configured)

**Usage:**
```
python3 query_signal.py --signal IONIQ5_HVBAT_HV_BATTERY_VOLTAGE

# Or specify signalset explicitly
python3 query_signal.py --signal IONIQ5_HVBAT_HV_BATTERY_VOLTAGE \
    --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json

# Query state of charge with explicit request ID
python3 query_signal.py --signal IONIQ5_HVBAT_SOC_VCMSuery state of charge with explicit request ID
python3 query_signal.py --signal IONIQ5_HVBAT_SOC_VCMS \
    --signalset ../Hyundai-IONIQ-5/signalsets/v3/

# Show signal information without querying
python3 query_signal.py --signal IONIQ5_VSS_HD

# Show signal information without querying
python3 query_signal.py --signal IONIQ5_VSS_HD \
    --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json --info

# Query with custom timeout
python3 query_signal.py --signal IONIQ5_ODO_KM \
    --signalset ../Hyundai-IONIQ-5/signalsets/v--timeout 5.0
```

**Note:** Both `query_signal.py` and `query_signalset.py` support `config.txt` for default signalset paths.
**How it works:**
1. Loads the signalset JSON file
2. Searches for the signal by ID
3. Extracts the command (service/PID/CAN IDs)
4. Connects to CAN bus via udsoncan
5. Queries the ECU with the appropriate UDS command
6. Decodes only the requested signal from the response
7. Displays the value with units

**Dependencies:**
```bash
pip install python-can udsoncan can-isotp
```

---

## CAN Interface Setup

All scripts require a configured CAN interface (typically `can0`).

### Setup SocketCAN:
```bash
# Bring up CAN interface with 500kbps bitrate
sudo ip link set can0 up type can bitrate 500000

# Verify interface is active
ip link show can0

# Monitor CAN traffic
candump can0
```

### Common CAN bitrates:
- 500000 (500 kbps) - Most common for automotive
- 250000 (250 kbps)
- 125000 (125 kbps)

---

## OBDb Python API

The `.schemas/python` directory contains the core OBDb Python modules:

### Core Modules:
- **`can/signals.py`** - Signal, Command, SignalSet classes with JSON parsing
- **`can/command_registry.py`** - CommandRegistry for searching and decoding
- **`can/can_frame.py`** - CAN frame handling
- **`signalsets/loader.py`** - Load signalsets by model year or path
- **`overlapping_signals.py`** - Signal validation utilities
- **`json_formatter.py`** - JSON formatting and validation

### Example API Usage:
```python
from can.signals import SignalSet
from can.command_registry import CommandRegistry

# Load signalset from JSON
with open('path/to/signalset.json', 'r') as f:
    signalset = SignalSet.from_json(f.read())

# Search for commands
for cmd in signalset.commands:
    if cmd.header == 0x74C:
        print(f"Found: {cmd.id}")
        for signal in cmd.signals:
            print(f"  - {signal.name}")
```

---

## Vehicle-Specific Notes

### Hyundai IONIQ 5
- VIN available at: `0x7C7 → 0x7CF`, DID `0xF190`
- Battery info at: `0x744 → 0x74C`, various PIDs (`0xE001`, `0xE002`, `0xE003`)
- Motor info at: `0x7E3 → 0x7EB`, DID `0xE001`

---

## Troubleshooting

### CAN Interface Issues:
```bash
# Check if interface exists
ip link show can0

# Check for errors
ip -details -statistics link show can0

# Restart interface
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 500000
```

### Permission Errors:
Run with `sudo` or add user to appropriate groups:
```bash
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

### No Response from ECU:
- Verify vehicle ignition is ON
- Check CAN bitrate matches vehicle (usually 500kbps)
- Try different request/response IDs
- Increase timeout: `--timeout 5.0`
- Use `candump can0` to verify traffic

---

## Additional Resources

- **OBDb Repository**: https://github.com/OBDb
- **UDS Specification**: ISO 14229
- **ISO-TP Protocol**: ISO 15765-2
- **SocketCAN Documentation**: https://www.kernel.org/doc/html/latest/networking/can.html
