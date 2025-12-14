#!/usr/bin/env python3
"""
Query vehicle VIN (Vehicle Identification Number) via CAN bus using udsoncan.

This script uses UDS Service 0x22 (Read Data By Identifier) with common VIN PIDs
to retrieve the VIN from the vehicle via the can0 interface.

Usage:
    sudo python3 query_vin.py [--request-id REQUEST_ID] [--response-id RESPONSE_ID]

Requirements:
    - python-can library: pip install python-can
    - udsoncan library: pip install udsoncan
    - CAN interface (can0) configured and active
"""

import argparse
import sys
import time
from typing import Optional, List

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


class VINReader:
    """Handles VIN querying via UDS over CAN using udsoncan."""
    
    # Standard UDS VIN Data Identifiers (DIDs)
    VIN_DIDS = {
        0xF190: "VIN (ISO 14229)",
        0xF19E: "VIN (Alternative)",
        0x0F02: "VIN (Mode 09 equivalent)",
    }
    
    def __init__(self, interface: str = 'can0', request_id: int = 0x7E0, response_id: int = 0x7E8, 
                 timeout: float = 2.0):
        """
        Initialize VIN reader.
        
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
            # Configure DIDs for VIN - use a simple codec that just returns raw bytes
            # Define a simple codec that passes through bytes unchanged
            config['data_identifiers'] = {
                'default' : '>H',                      # Default codec is a struct.pack/unpack string. 16bits little endian
                0xF190: udsoncan.AsciiCodec(17),  # 17 bytes as string
                0xF19E: udsoncan.DidCodec('17s'),
                0x0F02: udsoncan.DidCodec('17s'),
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
            print(f"→ Reading DID 0x{did:04X} ({self.VIN_DIDS.get(did, 'Unknown')})")
            response = self.client.read_data_by_identifier([did])
            
            if response and response.service_data:
                # Get raw data from response
                data_record = response.service_data.values.get(did)
                if data_record is not None:
                    # The DidCodec returns bytes directly for the '17s' format
                    # Just use it as-is
                    if isinstance(data_record, bytes):
                        data = data_record
                    else:
                        # Fallback for other types
                        data = bytes(str(data_record), 'ascii', errors='ignore')
                    
                    print(f"← Received {len(data)} bytes: {data.hex()}")
                    return data
            return None
            
        except NegativeResponseException as e:
            print(f"  Negative response: {e.response.code_name} (0x{e.response.code:02X})")
            return None
        except TimeoutException:
            print(f"  Timeout waiting for response")
            return None
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    def query_vin(self, dids: Optional[List[int]] = None) -> Optional[str]:
        """
        Query VIN, trying multiple DIDs if necessary.
        
        Args:
            dids: List of DIDs to try (default: [0xF190, 0xF19E, 0x0F02])
            
        Returns:
            VIN string if found, None otherwise
        """
        if dids is None:
            dids = list(self.VIN_DIDS.keys())
            
        for did in dids:
            print(f"\nAttempting DID 0x{did:04X}...")
            
            try:
                data = self.read_data_by_identifier(did)
                
                if data:
                    vin = self._decode_vin(data)
                    if vin and len(vin) == 17:
                        return vin
                    elif vin:
                        print(f"  Received data but not valid VIN (length: {len(vin)}): {vin}")
                    
            except Exception as e:
                print(f"  Error with DID 0x{did:04X}: {e}")
                continue
                
        return None
    
    def _decode_vin(self, data: bytes) -> Optional[str]:
        """
        Decode VIN from byte data.
        
        Args:
            data: Bytes containing VIN
            
        Returns:
            VIN string or None
        """
        try:
            # Handle tuple from DidCodec - extract the bytes
            if isinstance(data, tuple) and len(data) > 0:
                data = data[0]
            
            # Convert to string if bytes
            if isinstance(data, bytes):
                # Decode to ASCII, ignore errors
                raw_str = data.decode('ascii', errors='ignore')
            elif isinstance(data, str):
                raw_str = data
            else:
                raw_str = str(data)
            
            # VIN should be exactly 17 alphanumeric characters
            # VINs are always uppercase, so filter to uppercase letters and digits only
            vin_chars = [c for c in raw_str if c.isupper() or c.isdigit()]
            
            # Find a sequence of 17 consecutive valid VIN characters
            # This handles cases where there's framing data
            if len(vin_chars) >= 17:
                vin = ''.join(vin_chars[:17])
                return vin
            
            return None
            
        except Exception as e:
            print(f"✗ Failed to decode VIN: {e}")
            import traceback
            traceback.print_exc()
            return None


def scan_for_vin(interface: str = 'can0', timeout: float = 1.0) -> Optional[str]:
    """
    Scan common ECU addresses for VIN.
    
    Args:
        interface: CAN interface name
        timeout: Timeout per ECU attempt
        
    Returns:
        VIN string if found, None otherwise
    """
    # Common OBD ECU pairs (request_id, response_id)
    common_ecus = [
        (0x7E0, 0x7E8),  # Primary OBD
        (0x7E1, 0x7E9),  # Secondary OBD
        (0x7E2, 0x7EA),  # Tertiary OBD (powertrain control)
        (0x7E3, 0x7EB),  # Transmission/motor control
        (0x7E4, 0x7EC),  # Battery management (EV)
        (0x7DF, 0x7E8),  # Broadcast to primary
        (0x7C6, 0x7CE),  # BCM (Body Control Module) - common in Hyundai/Kia
        (0x7C7, 0x7CF),  # Works on Hyundai Ioniq 5
        (0x7B3, 0x7BB),  # HVAC - sometimes has VIN
    ]
    
    print(f"Scanning for VIN across {len(common_ecus)} ECUs...")
    
    for req_id, resp_id in common_ecus:
        print(f"\n{'='*60}")
        print(f"Trying ECU: 0x{req_id:03X} → 0x{resp_id:03X}")
        print('='*60)
        
        try:
            with VINReader(interface, req_id, resp_id, timeout=timeout) as reader:
                vin = reader.query_vin()
                if vin:
                    return vin
        except KeyboardInterrupt:
            print("\n\nScan interrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"  Error: {e}")
            continue
            
    return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Query vehicle VIN via CAN bus using udsoncan',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query VIN using default OBD addresses
  sudo python3 query_vin.py
  
  # Query specific ECU
  sudo python3 query_vin.py --request-id 0x7E0 --response-id 0x7E8
  
  # Scan all common ECUs
  sudo python3 query_vin.py --scan
  
  # Use specific DID
  sudo python3 query_vin.py --did 0xF190
  
  # Adjust timeout for slower ECUs
  sudo python3 query_vin.py --timeout 5.0

Note: This script requires root/sudo to access CAN interface.
      Uses udsoncan for proper UDS protocol handling with ISO-TP.
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
        '--scan', '-s',
        action='store_true',
        help='Scan multiple ECUs for VIN'
    )
    
    parser.add_argument(
        '--did',
        type=lambda x: int(x, 0),
        help='Specific VIN DID to query (default: try 0xF190, 0xF19E, 0x0F02)'
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
    
    args = parser.parse_args()
    
    # If response-id not specified, default to request-id + 8
    if args.response_id is None:
        args.response_id = args.request_id + 8
    
    # Configure udsoncan logging if verbose
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    print("="*60)
    print("Vehicle VIN Query Tool (udsoncan)")
    print("="*60)
    
    try:
        if args.scan:
            vin = scan_for_vin(args.interface, timeout=args.timeout)
        else:
            with VINReader(args.interface, args.request_id, args.response_id, 
                          timeout=args.timeout) as reader:
                dids = [args.did] if args.did else None
                vin = reader.query_vin(dids)
        
        if vin:
            print("\n" + "="*60)
            print(f"✓ VIN FOUND: {vin}")
            print("="*60)
            print(f"\nVIN Details:")
            print(f"  Length: {len(vin)} characters")
            if len(vin) >= 3:
                print(f"  WMI (Manufacturer): {vin[:3]}")
            if len(vin) >= 9:
                print(f"  VDS (Vehicle Descriptor): {vin[3:9]}")
            if len(vin) >= 17:
                print(f"  VIS (Vehicle Identifier): {vin[9:17]}")
            if len(vin) >= 10:
                print(f"  Model Year Code: {vin[9]}")
            if len(vin) >= 11:
                print(f"  Plant Code: {vin[10]}")
            sys.exit(0)
        else:
            print("\n" + "="*60)
            print("✗ VIN not found")
            print("="*60)
            print("\nTroubleshooting:")
            print("  1. Ensure vehicle ignition is ON")
            print("  2. Verify CAN bus is active: candump can0")
            print("  3. Try scanning all ECUs: --scan")
            print("  4. Check CAN bus speed matches vehicle (usually 500kbps)")
            print("  5. Try different request/response IDs based on vehicle make")
            print("  6. Increase timeout: --timeout 5.0")
            print("  7. Enable verbose mode: --verbose")
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
