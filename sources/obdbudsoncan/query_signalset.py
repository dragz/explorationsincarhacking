#!/usr/bin/env python3
"""
Example script demonstrating how to use the OBDb Python modules to query and parse signalset data.

This script shows:
1. Loading and parsing signalset JSON files
2. Searching for commands by CAN ID and service type
3. Finding signals within commands
4. Decoding response data

Usage:
    python3 query_signalset.py [--signalset PATH] [--can-id HEX] [--service HEX] [--pid HEX]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List


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


# Load config first to get obdb_dir
config = load_config()

# Add .schemas/python directory to path
if config['obdb_dir']:
    SCHEMAS_DIR = Path(config['obdb_dir']) / '.schemas' / 'python'
else:
    # Auto-detect: go up from script location
    SCHEMAS_DIR = Path(__file__).parent.parent / '.schemas' / 'python'
sys.path.insert(0, str(SCHEMAS_DIR))

try:
    # Import OBDb modules (note: different from python-can library)
    from can.signals import SignalSet, Command, Signal, Scaling, Enumeration
    from can.command_registry import CommandRegistry, ServiceType, CommandResponse
    from can.can_frame import CANPacket, CANIDFormat
except ImportError as e:
    print(f"Error: Could not import OBDb modules: {e}")
    print(f"Make sure the .schemas/python directory exists at: {SCHEMAS_DIR}")
    sys.exit(1)


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


def load_signalset_from_file(filepath: str) -> SignalSet:
    """Load and parse a signalset JSON file."""
    print(f"Loading signalset from: {filepath}")
    
    with open(filepath, 'r') as f:
        json_content = f.read()
    
    signalset = SignalSet.from_json(json_content)
    print(f"✓ Loaded {len(signalset.commands)} commands")
    
    return signalset


def search_commands_by_service(signalset: SignalSet, service: int, pid: Optional[int] = None) -> List[Command]:
    """Search for commands by service type and optionally by PID."""
    matching_commands = []
    
    for cmd in signalset.commands:
        # Check if service matches
        cmd_service = int(cmd.parameter.type.value, 16)
        if cmd_service != service:
            continue
        
        # Check if PID matches (if specified)
        if pid is not None and cmd.parameter.value != pid:
            continue
        
        matching_commands.append(cmd)
    
    return matching_commands


def search_commands_by_can_id(signalset: SignalSet, can_id: int) -> List[Command]:
    """Search for commands by CAN ID (header or receive address)."""
    matching_commands = []
    
    for cmd in signalset.commands:
        if cmd.header == can_id or cmd.receive_address == can_id:
            matching_commands.append(cmd)
    
    return matching_commands


def print_command_details(command: Command, verbose: bool = False):
    """Print details about a command."""
    service = int(command.parameter.type.value, 16)
    pid = command.parameter.value
    
    print(f"\n{'='*80}")
    print(f"Command: {command.id}")
    print(f"{'='*80}")
    print(f"Service:  0x{service:02X}")
    
    if service == 0x22:
        print(f"PID:      0x{pid:04X}")
    else:
        print(f"PID:      0x{pid:02X}")
    
    if command.header:
        print(f"Header:   0x{command.header:03X}")
    if command.receive_address:
        print(f"RX ID:    0x{command.receive_address:03X}")
    
    if command.update_frequency:
        print(f"Freq:     {command.update_frequency} Hz")
    
    print(f"\nSignals: ({len(command.signals)})")
    print(f"{'-'*80}")
    
    for signal in command.signals:
        print(f"\nSignal ID:   {signal.id}")
        print(f"Name:        {signal.name}")
        
        if signal.description:
            print(f"Description: {signal.description}")
        
        if signal.path:
            print(f"Path:        {signal.path}")
        
        if signal.suggested_metric:
            print(f"Metric:      {signal.suggested_metric}")
        
        # Print format details
        if isinstance(signal.format, Scaling):
            fmt = signal.format
            print(f"Format:      Scaling")
            print(f"  Bit Offset: {fmt.bit_offset}")
            print(f"  Bit Length: {fmt.bit_length}")
            print(f"  Range:      {fmt.min_value} to {fmt.max_value}")
            print(f"  Unit:       {fmt.unit}")
            if verbose:
                print(f"  Scalar:     {fmt.scalar}")
                print(f"  Divisor:    {fmt.divisor}")
                print(f"  Offset:     {fmt.offset}")
                print(f"  Signed:     {fmt.signed}")
                print(f"  Bytes LSB:  {fmt.bytes_lsb}")
        
        elif isinstance(signal.format, Enumeration):
            fmt = signal.format
            print(f"Format:      Enumeration")
            print(f"  Bit Offset: {fmt.bit_offset}")
            print(f"  Bit Length: {fmt.bit_length}")
            print(f"  Unit:       {fmt.unit}")
            if verbose:
                print(f"  Mappings:   {len(fmt.mappings)}")
                for key, value in list(fmt.mappings.items())[:5]:  # Show first 5
                    print(f"    {key} = {value}")
                if len(fmt.mappings) > 5:
                    print(f"    ... and {len(fmt.mappings) - 5} more")


def decode_response_example(command: Command, response_hex: str):
    """Demonstrate decoding a response for a command."""
    print(f"\n{'='*80}")
    print(f"Decoding Response")
    print(f"{'='*80}")
    print(f"Response Hex: {response_hex}")
    
    # Convert hex string to bytes
    response_bytes = bytes.fromhex(response_hex.replace(' ', ''))
    
    # Skip the first 3 bytes (service + PID) for service 0x22
    service = int(command.parameter.type.value, 16)
    if service == 0x22:
        data = response_bytes[3:]  # Skip 0x62 + 2-byte PID
    elif service == 0x21:
        data = response_bytes[2:]  # Skip 0x61 + 1-byte offset
    elif service == 0x01:
        data = response_bytes[2:]  # Skip 0x41 + 1-byte PID
    else:
        data = response_bytes[1:]  # Skip service response byte
    
    print(f"Data Bytes:   {data.hex()}")
    print(f"\nDecoded Values:")
    print(f"{'-'*80}")
    
    # Decode each signal
    for signal in command.signals:
        try:
            if isinstance(signal.format, Scaling):
                value = signal.format.decode_value(data)
                print(f"{signal.id:40} = {value:12.3f} {signal.format.unit}")
            elif isinstance(signal.format, Enumeration):
                value = signal.format.decode_value(data)
                print(f"{signal.id:40} = {value}")
        except Exception as e:
            print(f"{signal.id:40} = ERROR: {e}")


def list_all_signals(signalset: SignalSet):
    """List all unique signals across all commands."""
    print(f"\n{'='*80}")
    print(f"All Signals Summary")
    print(f"{'='*80}")
    
    # Collect all unique signals
    all_signals = set()
    for cmd in signalset.commands:
        for signal in cmd.signals:
            all_signals.add(signal.id)
    
    print(f"Total unique signals: {len(all_signals)}")
    
    # Group by path
    signals_by_path = {}
    for cmd in signalset.commands:
        for signal in cmd.signals:
            path = signal.path or "Root"
            if path not in signals_by_path:
                signals_by_path[path] = []
            if signal not in signals_by_path[path]:
                signals_by_path[path].append(signal)
    
    print(f"\nSignals by Path:")
    for path in sorted(signals_by_path.keys()):
        signals = signals_by_path[path]
        print(f"\n  {path}/ ({len(signals)} signals)")
        for signal in sorted(signals, key=lambda s: s.id)[:5]:  # Show first 5
            print(f"    - {signal.id}: {signal.name}")
        if len(signals) > 5:
            print(f"    ... and {len(signals) - 5} more")


def main():
    # config already loaded at module level
    global config
    
    parser = argparse.ArgumentParser(
        description='Query and parse OBDb signalset data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load and list all commands in a signalset
  python3 query_signalset.py --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json
  
  # Search for commands by service 0x22
  python3 query_signalset.py --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json --service 0x22
  
  # Search for specific PID
  python3 query_signalset.py --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json --service 0x22 --pid 0xE001
  
  # Search by CAN ID
  python3 query_signalset.py --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json --can-id 0x74C
  
  # Decode a response (provide response hex)
  python3 query_signalset.py --signalset ../Hyundai-IONIQ-5/signalsets/v3/default.json --service 0x22 --pid 0xE001 --decode "62 E0 01 00 00 00 FF 1D C8 01 2C 00 05 00 00 09 C4"
        """
    )
    
    parser.add_argument(
        '--signalset', '-s',
        required=False,
        help=f"Path to signalset JSON file (default: {config['default_signalset'] or 'none - must specify'})"
    )
    
    parser.add_argument(
        '--service',
        type=lambda x: int(x, 0),
        help='Filter by service type (e.g., 0x22, 0x21, 0x01)'
    )
    
    parser.add_argument(
        '--pid',
        type=lambda x: int(x, 0),
        help='Filter by PID value (e.g., 0xE001)'
    )
    
    parser.add_argument(
        '--can-id',
        type=lambda x: int(x, 0),
        help='Filter by CAN ID (e.g., 0x74C)'
    )
    
    parser.add_argument(
        '--decode',
        help='Hex string of response to decode (requires --service and --pid)'
    )
    
    parser.add_argument(
        '--list-signals', '-l',
        action='store_true',
        help='List all unique signals'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed signal format information'
    )
    
    args = parser.parse_args()
    
    # Resolve signalset path
    signalset_path = resolve_signalset_path(args.signalset, config)
    
    # Load signalset
    try:
        signalset = load_signalset_from_file(signalset_path)
    except FileNotFoundError:
        print(f"✗ Error: Signalset file not found: {signalset_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in signalset file: {e}")
        sys.exit(1)
    
    # List signals if requested
    if args.list_signals:
        list_all_signals(signalset)
        return
    
    # Search for commands
    commands = []
    
    if args.can_id is not None:
        commands = search_commands_by_can_id(signalset, args.can_id)
        print(f"\nFound {len(commands)} command(s) for CAN ID 0x{args.can_id:03X}")
    
    elif args.service is not None:
        commands = search_commands_by_service(signalset, args.service, args.pid)
        if args.pid is not None:
            print(f"\nFound {len(commands)} command(s) for Service 0x{args.service:02X}, PID 0x{args.pid:04X}")
        else:
            print(f"\nFound {len(commands)} command(s) for Service 0x{args.service:02X}")
    
    else:
        # No filter - show all commands summary
        print(f"\n{'='*80}")
        print(f"Signalset Summary")
        print(f"{'='*80}")
        print(f"Total Commands: {len(signalset.commands)}")
        
        # Count by service type
        services = {}
        for cmd in signalset.commands:
            service = int(cmd.parameter.type.value, 16)
            services[service] = services.get(service, 0) + 1
        
        print(f"\nCommands by Service:")
        for service in sorted(services.keys()):
            print(f"  Service 0x{service:02X}: {services[service]} commands")
        
        # Count by CAN ID
        can_ids = {}
        for cmd in signalset.commands:
            if cmd.header:
                can_ids[cmd.header] = can_ids.get(cmd.header, 0) + 1
        
        print(f"\nCommands by CAN Header ID:")
        for can_id in sorted(can_ids.keys())[:10]:  # Show first 10
            print(f"  0x{can_id:03X}: {can_ids[can_id]} commands")
        if len(can_ids) > 10:
            print(f"  ... and {len(can_ids) - 10} more")
        
        print(f"\nUse --service, --pid, or --can-id to filter commands")
        print(f"Use --list-signals to see all available signals")
        return
    
    # Display matching commands
    for cmd in commands[:10]:  # Limit to first 10 for readability
        print_command_details(cmd, args.verbose)
    
    if len(commands) > 10:
        print(f"\n... and {len(commands) - 10} more commands (showing first 10)")
    
    # Decode response if provided
    if args.decode and commands:
        decode_response_example(commands[0], args.decode)
    elif args.decode:
        print("\n✗ Cannot decode: no matching command found")


if __name__ == '__main__':
    main()
