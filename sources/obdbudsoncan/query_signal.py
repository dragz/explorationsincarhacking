#!/usr/bin/env python3
"""
Query a specific signal from the vehicle by signal ID.

This script:
1. Loads the signalset to find the signal definition
2. Determines which command contains the signal
3. Queries the vehicle via CAN bus using UDS
4. Decodes and displays the signal value

Usage:
    python3 query_signal.py --signal SIGNAL_ID --signalset PATH [--request-id HEX]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

# Add .schemas/python directory to path
SCHEMAS_DIR = Path(__file__).parent.parent / '.schemas' / 'python'
sys.path.insert(0, str(SCHEMAS_DIR))

# Import OBDb modules first, before python-can, to avoid module name conflict
try:
    from can.signals import SignalSet, Command, Signal, Scaling, Enumeration
except ImportError as e:
    print(f"Error: Could not import OBDb modules: {e}")
    print(f"Make sure the .schemas/python directory exists at: {SCHEMAS_DIR}")
    sys.exit(1)

# To import python-can after OBDb's can module, we need to:
# 1. Save reference to OBDb can module
# 2. Remove SCHEMAS_DIR from sys.path temporarily
# 3. Remove 'can' from sys.modules
# 4. Import python-can (which will register itself as 'can' in sys.modules)
# 5. Restore SCHEMAS_DIR to path
# Note: We keep python-can as sys.modules['can'] for its submodules to work
obdb_can_signals = SignalSet  # Keep reference to OBDb classes we need
sys.path.remove(str(SCHEMAS_DIR))
del sys.modules['can']
del sys.modules['can.signals']  # Remove OBDb can.signals too

try:
    import can as python_can
except ImportError:
    print("Error: python-can library not found. Install it with: pip install python-can")
    sys.exit(1)

# Restore OBDb path (but leave python-can in sys.modules['can'])
sys.path.insert(0, str(SCHEMAS_DIR))

try:
    import udsoncan
    from udsoncan.connections import PythonIsoTpConnection
    from udsoncan.client import Client
    from udsoncan.configs import ClientConfig
    from udsoncan.exceptions import *
    import isotp
except ImportError as e:
    print(f"Error: Required library not found: {e}")
    print("Install with: pip install udsoncan python-can can-isotp")
    sys.exit(1)

class RawPayload(udsoncan.DidCodec):
   def encode(self, val):
      val = (val << 4) & 0xFFFFFFFF # Do some stuff
      return struct.pack('<L', val) # Little endian, 32 bit value

   def decode(self, payload):
      return list(payload)  # Unpack bytestring to a list of integers

   def __len__(self):
      raise udsoncan.DidCodec.ReadAllRemainingData
      return 0    # encoded payload is  byte long.


def load_config() -> dict:
    """Load configuration from config.txt."""
    config = {
        'obdb_dir': '',
        'default_signalset': '',
        'default_interface': 'can0'
    }
    
    config_path = Path(__file__).parent / 'config.txt'
    if not config_path.exists():
        return config
    
    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key in config and value:
                        config[key] = value
    except Exception as e:
        print(f"Warning: Could not read config.txt: {e}")
    
    return config


def resolve_signalset_path(signalset_arg: Optional[str], config: dict) -> str:
    """Resolve signalset path from argument or config."""
    if signalset_arg:
        return signalset_arg
    
    if not config['default_signalset']:
        print("Error: No signalset specified and no default_signalset in config.txt")
        print("Either use --signalset argument or set default_signalset in config.txt")
        sys.exit(1)
    
    signalset_path = config['default_signalset']
    
    # If path is not absolute, try to resolve relative to obdb_dir
    if not Path(signalset_path).is_absolute():
        if config['obdb_dir']:
            obdb_dir = Path(config['obdb_dir'])
        else:
            # Auto-detect: go up from python-examples to OBDb root
            obdb_dir = Path(__file__).parent.parent
        
        signalset_path = obdb_dir / signalset_path
    
    return str(signalset_path)


def find_signal_in_signalset(signalset: SignalSet, signal_id: str) -> Optional[Tuple[Command, Signal]]:
    """Find a signal by ID and return the command and signal."""
    for cmd in signalset.commands:
        for signal in cmd.signals:
            if signal.id == signal_id:
                return (cmd, signal)
    return None


class SignalReader:
    """Handles signal querying via UDS over CAN."""
    
    def __init__(self, interface: str = 'can0', request_id: int = 0x7E0, response_id: int = 0x7E8,
                 timeout: float = 2.0):
        """
        Initialize signal reader.
        
        Args:
            interface: CAN interface name (default: can0)
            request_id: CAN ID for sending requests
            response_id: CAN ID for receiving responses
            timeout: Request timeout in seconds (default: 2.0)
        """
        self.interface = interface
        self.request_id = request_id
        self.response_id = response_id
        self.timeout = timeout
        self.bus = None
        self.connection = None
        self.client = None
        
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        
    def connect(self):
        """Establish connection to CAN bus and initialize UDS client."""
        try:
            # Create python-can bus
            self.bus = python_can.interface.Bus(channel=self.interface, interface='socketcan')
            print(f"✓ Connected to {self.interface}")
            
            # Create notifier for ISO-TP stack
            self.notifier = python_can.Notifier(self.bus, [], timeout=0.1)
            
            # Create ISO-TP layer with NotifierBasedCanStack
            # Configure ISO-TP parameters for proper 8-byte padding
            params = {
                'stmin': 0,
                'blocksize': 0,
                'tx_data_length': 8,
                'tx_padding': 0x00,
                'rx_flowcontrol_timeout': 1000,
                'rx_consecutive_frame_timeout': 1000
            }
            
            self.isotp_layer = isotp.NotifierBasedCanStack(
                bus=self.bus,
                notifier=self.notifier,
                address=isotp.Address(
                    txid=self.request_id,
                    rxid=self.response_id
                ),
                params=params
            )
            
            # Create ISO-TP connection for udsoncan
            self.connection = PythonIsoTpConnection(self.isotp_layer)
            
            # Create UDS client with custom config
            config = ClientConfig()
            config['request_timeout'] = self.timeout
            config['data_identifiers'] = {
                                'default' : RawPayload(), # Default DID format
            }
            
            self.client = Client(self.connection, config=config)
            
            # Open the connection
            self.connection.open()
            
            print(f"✓ UDS client initialized (TX: 0x{self.request_id:03X}, RX: 0x{self.response_id:03X})")
            
        except Exception as e:
            print(f"✗ Failed to connect to {self.interface}: {e}")
            print("\nTroubleshooting:")
            print("  1. Check if interface exists: ip link show can0")
            print("  2. Bring up interface: sudo ip link set can0 up type can bitrate 500000")
            print("  3. Run with sudo if permission denied")
            sys.exit(1)
            
    def disconnect(self):
        """Close CAN bus connection."""
        try:
            if self.connection:
                self.connection.close()
        except AttributeError:
            pass
        if hasattr(self, 'notifier') and self.notifier:
            self.notifier.stop()
        if self.bus:
            self.bus.shutdown()
            print(f"✓ Disconnected from {self.interface}")
    
    def query_signal(self, command: Command, signal: Signal) -> Optional[float]:
        """
        Query a signal from the vehicle.
        
        Args:
            command: Command containing the signal
            signal: Signal to query
            
        Returns:
            Decoded signal value, or None if failed
        """
        # Determine service and PID
        service = int(command.parameter.type.value, 16)
        pid = command.parameter.value
        
        if service == 0x22:
            print(f"→ Reading Service 0x{service:02X}, PID 0x{pid:04X}")
        else:
            print(f"→ Reading Service 0x{service:02X}, PID 0x{pid:02X}")
        
        try:
            # Query using UDS Service 0x22 (ReadDataByIdentifier)
            if service == 0x22:
                response = self.client.read_data_by_identifier([pid])
            else:
                print(f"✗ Service 0x{service:02X} not yet supported (only 0x22)")
                return None
            
            if response and response.service_data:
                # Get raw data from response
                data_record = response.service_data.values.get(pid)
                if data_record is not None:
                    # Handle different data types
                    if isinstance(data_record, bytes):
                        data = data_record
                    elif isinstance(data_record, (list, tuple)):
                        try:
                            data = bytes(data_record)
                        except TypeError:
                            data = bytes([int(x) if isinstance(x, int) else ord(str(x)[0]) for x in data_record])
                    else:
                        data = bytes(str(data_record), 'ascii', errors='ignore')
                    
                    print(f"← Received {len(data)} bytes")
                    
                    # Decode the specific signal
                    if isinstance(signal.format, Scaling):
                        value = signal.format.decode_value(data)
                        return value
                    elif isinstance(signal.format, Enumeration):
                        value = signal.format.decode_value(data)
                        return value
                    
            return None
            
        except NegativeResponseException as e:
            print(f"✗ Negative response: {e.response.code_name} (0x{e.response.code:02X})")
            return None
        except TimeoutException:
            print(f"✗ Timeout waiting for response")
            return None
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return None


def format_signal_value(signal: Signal, value) -> str:
    """Format signal value for display."""
    if isinstance(signal.format, Scaling):
        if isinstance(value, (int, float)):
            return f"{value:.3f} {signal.format.unit}"
        else:
            return f"{value}"
    elif isinstance(signal.format, Enumeration):
        return str(value)
    else:
        return str(value)


def main():
    # Load configuration
    config = load_config()
    
    parser = argparse.ArgumentParser(
        description='Query a specific signal from the vehicle by signal ID',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query battery voltage from IONIQ 5
  python3 query_signal.py --signal IONIQ5_HVBAT_HV_BATTERY_VOLTAGE \\
      --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json \\
      --request-id 0x744
  
  # Query state of charge
  python3 query_signal.py --signal IONIQ5_HVBAT_SOC_VCMS \\
      --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json \\
      --request-id 0x744
  
  # Query motor RPM
  python3 query_signal.py --signal IONIQ5_MOTOR_RPM \\
      --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json \\
      --request-id 0x7E3
  
  # Query vehicle speed
  python3 query_signal.py --signal IONIQ5_VSS_HD \\
      --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json \\
      --request-id 0x7E2
  
  # Auto-detect response ID (request-id + 8)
  python3 query_signal.py --signal IONIQ5_HVBAT_HV_BATTERY_VOLTAGE \\
      --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json \\
      --request-id 0x744

Note: The script automatically determines which command contains the signal
      and queries the appropriate service/PID combination.
        """
    )
    
    parser.add_argument(
        '--signal', '-s',
        required=True,
        help='Signal ID to query (e.g., IONIQ5_HVBAT_HV_BATTERY_VOLTAGE)'
    )
    
    parser.add_argument(
        '--signalset',
        required=False,
        help=f"Path to signalset JSON file (default: {config['default_signalset'] or 'none - must specify'})"
    )
    
    parser.add_argument(
        '--interface', '-i',
        default=config['default_interface'],
        help=f"CAN interface name (default: {config['default_interface']})"
    )
    
    parser.add_argument(
        '--request-id', '-r',
        type=lambda x: int(x, 0),
        help='CAN ID for requests (uses header from signalset if not specified)'
    )
    
    parser.add_argument(
        '--response-id', '-R',
        type=lambda x: int(x, 0),
        default=None,
        help='CAN ID for responses (default: request-id + 8, or uses rax from signalset)'
    )
    
    parser.add_argument(
        '--timeout', '-t',
        type=float,
        default=2.0,
        help='Request timeout in seconds (default: 2.0)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--info',
        action='store_true',
        help='Show signal information without querying'
    )
    
    args = parser.parse_args()
    
    # Configure udsoncan logging if verbose
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    print("="*80)
    print("Vehicle Signal Query Tool")
    print("="*80)
    
    # Resolve signalset path
    signalset_path = resolve_signalset_path(args.signalset, config)
    
    # Load signalset
    try:
        with open(signalset_path, 'r') as f:
            json_content = f.read()
        signalset = SignalSet.from_json(json_content)
        print(f"✓ Loaded signalset: {signalset_path}")
    except FileNotFoundError:
        print(f"✗ Error: Signalset file not found: {signalset_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in signalset file: {e}")
        sys.exit(1)
    
    # Find signal in signalset
    result = find_signal_in_signalset(signalset, args.signal)
    if not result:
        print(f"✗ Error: Signal '{args.signal}' not found in signalset")
        print("\nAvailable signals (first 20):")
        all_signals = set()
        for cmd in signalset.commands:
            for sig in cmd.signals:
                all_signals.add(sig.id)
        for i, sig_id in enumerate(sorted(all_signals)[:20]):
            print(f"  - {sig_id}")
        if len(all_signals) > 20:
            print(f"  ... and {len(all_signals) - 20} more")
        sys.exit(1)
    
    command, signal = result
    
    # Display signal information
    print(f"\n✓ Found signal: {signal.id}")
    print(f"  Name:        {signal.name}")
    if signal.description:
        print(f"  Description: {signal.description}")
    if signal.path:
        print(f"  Path:        {signal.path}")
    if signal.suggested_metric:
        print(f"  Metric:      {signal.suggested_metric}")
    
    # Display command information
    service = int(command.parameter.type.value, 16)
    pid = command.parameter.value
    print(f"\n  Command:     {command.id}")
    print(f"  Service:     0x{service:02X}")
    if service == 0x22:
        print(f"  PID:         0x{pid:04X}")
    else:
        print(f"  PID:         0x{pid:02X}")
    print(f"  Header:      0x{command.header:03X}")
    if command.receive_address:
        print(f"  RX Address:  0x{command.receive_address:03X}")
    
    # Display format information
    if isinstance(signal.format, Scaling):
        fmt = signal.format
        print(f"\n  Format:      Scaling")
        print(f"  Bit Offset:  {fmt.bit_offset}")
        print(f"  Bit Length:  {fmt.bit_length}")
        print(f"  Range:       {fmt.min_value} to {fmt.max_value}")
        print(f"  Unit:        {fmt.unit}")
    elif isinstance(signal.format, Enumeration):
        fmt = signal.format
        print(f"\n  Format:      Enumeration")
        print(f"  Bit Offset:  {fmt.bit_offset}")
        print(f"  Bit Length:  {fmt.bit_length}")
        print(f"  Unit:        {fmt.unit}")
        print(f"  Mappings:    {len(fmt.mappings)} values")
    
    # If --info only, exit here
    if args.info:
        sys.exit(0)
    
    # Determine CAN IDs to use
    if args.request_id is None:
        # Use header from command
        request_id = command.header
        print(f"\n✓ Using header from signalset: 0x{request_id:03X}")
    else:
        request_id = args.request_id
    
    if args.response_id is None:
        if command.receive_address:
            # Use receive address from command
            response_id = command.receive_address
            print(f"✓ Using receive address from signalset: 0x{response_id:03X}")
        else:
            # Auto-calculate: request_id + 8
            response_id = request_id + 8
            print(f"✓ Auto-calculated response ID: 0x{response_id:03X}")
    else:
        response_id = args.response_id
    
    print("\n" + "="*80)
    print("Querying Vehicle")
    print("="*80)
    
    # Query the signal
    try:
        with SignalReader(args.interface, request_id, response_id, 
                         timeout=args.timeout) as reader:
            value = reader.query_signal(command, signal)
        
        if value is not None:
            print("\n" + "="*80)
            print(f"✓ SIGNAL VALUE")
            print("="*80)
            print(f"\nSignal:  {signal.id}")
            print(f"Value:   {format_signal_value(signal, value)}")
            if signal.name:
                print(f"Name:    {signal.name}")
            sys.exit(0)
        else:
            print("\n" + "="*80)
            print(f"✗ Failed to read signal")
            print("="*80)
            print("\nTroubleshooting:")
            print("  1. Ensure vehicle ignition is ON")
            print("  2. Verify CAN bus is active: candump can0")
            print("  3. Check if ECU supports this signal")
            print("  4. Try different request/response IDs")
            print("  5. Increase timeout: --timeout 5.0")
            print("  6. Enable verbose mode: --verbose")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
