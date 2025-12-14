#!/usr/bin/env python3
"""
Query vehicle Data Identifier (DID) via CAN bus using udsoncan.

This script uses UDS Service 0x22 (Read Data By Identifier) to retrieve
any DID from the vehicle via the CAN interface.

Usage:
    python3 query_did.py --did 0xF190 [--request-id REQUEST_ID] [--response-id RESPONSE_ID]

Requirements:
    - python-can library: pip install python-can
    - udsoncan library: pip install udsoncan
    - can-isotp library: pip install can-isotp
    - CAN interface (can0) configured and active
"""

import argparse
import sys
from typing import Optional

try:
    import can as python_can
except ImportError:
    print("Error: python-can library not found. Install it with: pip install python-can")
    sys.exit(1)

try:
    import udsoncan
    from udsoncan.connections import PythonIsoTpConnection
    from udsoncan.client import Client
    from udsoncan.configs import ClientConfig
    from udsoncan.exceptions import *
    from udsoncan import services
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


class DIDReader:
    """Handles DID querying via UDS over CAN using udsoncan."""
    
    def __init__(self, interface: str = 'can0', request_id: int = 0x7E0, response_id: int = 0x7E8, 
                 timeout: float = 2.0):
        """
        Initialize DID reader.
        
        Args:
            interface: CAN interface name (default: can0)
            request_id: CAN ID for sending requests (default: 0x7E0 - typical OBD)
            response_id: CAN ID for receiving responses (default: 0x7E8 - typical OBD)
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
                'stmin': 0,                          # Minimum separation time
                'blocksize': 0,                      # Block size (0 = unlimited)
                'tx_data_length': 8,                 # Transmit data length - ensures 8 byte frames
                'tx_padding': 0x00,                  # Padding byte value
                'rx_flowcontrol_timeout': 1000,      # Flow control timeout in ms
                'rx_consecutive_frame_timeout': 1000 # Consecutive frame timeout in ms
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
            # Empty data_identifiers - we'll handle raw bytes
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
            # isotp_layer might not have all expected attributes, ignore
            pass
        if hasattr(self, 'notifier') and self.notifier:
            self.notifier.stop()
        if self.bus:
            self.bus.shutdown()
            print(f"✓ Disconnected from {self.interface}")
            
    def read_data_by_identifier(self, did: int) -> Optional[bytes]:
        """
        Read data using UDS Service 0x22 (ReadDataByIdentifier).
        
        Args:
            did: Data Identifier to read
            
        Returns:
            Response data as bytes, or None if failed
        """
        try:
            print(f"→ Reading DID 0x{did:04X}")
            response = self.client.read_data_by_identifier([did])
            
            if response and response.service_data:
                # Get raw data from response
                data_record = response.service_data.values.get(did)
                if data_record is not None:
                    # Handle different data types
                    if isinstance(data_record, bytes):
                        data = data_record
                    elif isinstance(data_record, (list, tuple)):
                        # Convert list/tuple to bytes
                        try:
                            data = bytes(data_record)
                        except TypeError:
                            # If elements are not integers, convert them
                            data = bytes([int(x) if isinstance(x, int) else ord(str(x)[0]) for x in data_record])
                    else:
                        # Try to convert to bytes
                        data = bytes(str(data_record), 'ascii', errors='ignore')
                    
                    print(f"← Received {len(data)} bytes")
                    return data
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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Query vehicle DID (Data Identifier) via CAN bus using udsoncan',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query DID 0xF190 (VIN) using default OBD addresses
  python3 query_did.py --did 0xF190
  
  # Query specific DID from specific ECU
  python3 query_did.py --did 0xF190 --request-id 0x7C7 --response-id 0x7CF
  
  # Query with custom timeout
  python3 query_did.py --did 0x0100 --timeout 5.0
  
  # Use request-id with automatic response-id (request-id + 8)
  python3 query_did.py --did 0xF190 --request-id 0x7C7

Common DIDs:
  0xF190 - VIN (Vehicle Identification Number)
  0xF187 - Vehicle Manufacturer Spare Part Number
  0xF18A - Vehicle Manufacturer ECU Software Number
  0xF18C - ECU Serial Number
  0xF191 - ECU Hardware Version Number
  0xF19E - System Supplier ECU Software Number

Note: Uses udsoncan for proper UDS protocol handling with ISO-TP.
      Automatically pads all CAN frames to 8 bytes.
        """
    )
    
    parser.add_argument(
        '--interface', '-i',
        default='can0',
        help='CAN interface name (default: can0)'
    )
    
    parser.add_argument(
        '--request-id', '-r',
        type=lambda x: int(x, 0),
        default=0x7E0,
        help='CAN ID for requests (default: 0x7E0)'
    )
    
    parser.add_argument(
        '--response-id', '-R',
        type=lambda x: int(x, 0),
        default=None,
        help='CAN ID for responses (default: request-id + 8)'
    )
    
    parser.add_argument(
        '--did', '-d',
        type=lambda x: int(x, 0),
        required=True,
        help='Data Identifier to query (required, e.g., 0xF190 for VIN)'
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
        '--ascii', '-a',
        action='store_true',
        help='Try to decode response as ASCII text'
    )
    
    args = parser.parse_args()
    
    # If response-id not specified, default to request-id + 8
    if args.response_id is None:
        args.response_id = args.request_id + 8
    
    # Configure udsoncan logging if verbose
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    print("="*60)
    print("Vehicle DID Query Tool (udsoncan)")
    print("="*60)
    
    try:
        with DIDReader(args.interface, args.request_id, args.response_id, 
                      timeout=args.timeout) as reader:
            data = reader.read_data_by_identifier(args.did)
        
        if data:
            print("\n" + "="*60)
            print(f"✓ DID 0x{args.did:04X} DATA RECEIVED")
            print("="*60)
            print(f"\nData Length: {len(data)} bytes")
            print(f"\nHex String:")
            print(f"  {data.hex()}")
            
            # Format as hex bytes for readability
            print(f"\nFormatted Hex:")
            hex_formatted = ' '.join([f'{b:02X}' for b in data])
            # Print in rows of 16 bytes
            for i in range(0, len(hex_formatted), 48):  # 48 = 16 bytes * 3 chars per byte
                print(f"  {hex_formatted[i:i+48]}")
            
            # Try ASCII decode if requested or if data looks like text
            if args.ascii or all(32 <= b < 127 for b in data):
                try:
                    ascii_str = data.decode('ascii', errors='ignore')
                    if ascii_str.strip():
                        print(f"\nASCII Interpretation:")
                        print(f"  {ascii_str}")
                except:
                    pass
            
            sys.exit(0)
        else:
            print("\n" + "="*60)
            print(f"✗ Failed to read DID 0x{args.did:04X}")
            print("="*60)
            print("\nTroubleshooting:")
            print("  1. Ensure vehicle ignition is ON")
            print("  2. Verify CAN bus is active: candump can0")
            print("  3. Check if ECU supports this DID")
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
