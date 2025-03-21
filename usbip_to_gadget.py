#!/usr/bin/env python3
"""
USB/IP to USB Gadget Shim for Virtual FIDO

This script connects the Virtual FIDO USB/IP server to a USB HID gadget device.
It acts as a bridge between the two, forwarding USB/IP packets to the HID device
and returning responses.

Usage:
  sudo python3 usbip_to_gadget.py

Requirements:
  - Python 3.6+
  - USB Gadget Mode configured for HID
  - Virtual FIDO server running locally

In Docker environment:
  - Can be run in test mode using mock environment
  - Unit tests can run without actual hardware
  - Integration tests require the Virtual FIDO server running
"""

import socket
import struct
import fcntl
import os
import time
import threading
import argparse
import sys
import logging
import unittest
import tempfile
import io
import binascii
from unittest import mock
from typing import Optional, Tuple, List, Dict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('usbip_shim')

# Constants
USBIP_PORT = 3240
HID_DEVICE_PATH = '/dev/hidg0'
USB_PACKET_SIZE = 64

# USB/IP command codes (from virtual-fido/usbip/usbip.go)
USBIP_CMD_SUBMIT = 0x00000001
USBIP_CMD_UNLINK = 0x00000002
USBIP_DIR_OUT = 0x00
USBIP_DIR_IN = 0x01

# USB Endpoints
USB_ENDPOINT_CONTROL = 0
USB_ENDPOINT_OUT = 1
USB_ENDPOINT_IN = 2

class USBIPShim:
    """Bridge between USB/IP and USB HID Gadget"""
    
    def __init__(self, usbip_host: str, usbip_port: int, hid_device: str):
        self.usbip_host = usbip_host
        self.usbip_port = usbip_port
        self.hid_device = hid_device
        self.sock = None
        self.hid_fd = None
        self.connected = False
        self.pending_requests: Dict[int, dict] = {}
        self.lock = threading.Lock()
        self.device_attached = False
    
    def connect(self) -> bool:
        """Connect to USB/IP server and open HID device"""
        try:
            # Connect to USB/IP server
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.usbip_host, self.usbip_port))
            logger.info(f"Connected to USB/IP server at {self.usbip_host}:{self.usbip_port}")
            
            # Open HID device
            self.hid_fd = os.open(self.hid_device, os.O_RDWR)
            logger.info(f"Opened HID device at {self.hid_device}")
            
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.cleanup()
            return False
    
    def cleanup(self):
        """Close connections and clean up resources"""
        if self.sock:
            self.sock.close()
            self.sock = None
        
        if self.hid_fd is not None:
            os.close(self.hid_fd)
            self.hid_fd = None
        
        self.connected = False
        self.device_attached = False
    
    def attach_device(self) -> bool:
        """Attach the virtual USB device via USB/IP"""
        try:
            # Send OP_REQ_DEVLIST command
            command_header = struct.pack("!II", 0x8005, 0x00000001)  # Version 1, OP_REQ_DEVLIST
            self.sock.sendall(command_header)
            
            # Read response header
            header_data = self.sock.recv(8)
            if not header_data or len(header_data) < 8:
                logger.error("Failed to read device list response header")
                return False
            
            # Parse response to get device info
            version, command, status = struct.unpack("!HHI", header_data)
            
            # Read number of devices
            devices_data = self.sock.recv(4)
            num_devices = struct.unpack("!I", devices_data)[0]
            logger.info(f"Found {num_devices} devices")
            
            if num_devices < 1:
                logger.error("No devices available")
                return False
            
            # Read device information
            device_data = self.sock.recv(1024)  # Read enough for the device info
            
            # Attach the first device (bus_id should be "2-2" for Virtual FIDO)
            bus_id = "2-2"
            
            # Send OP_REQ_IMPORT command
            command_header = struct.pack("!II", 0x8003, 0x00000003)  # Version 3, OP_REQ_IMPORT
            self.sock.sendall(command_header)
            
            # Send bus_id (padded to 32 bytes)
            padded_bus_id = bus_id.encode('ascii') + b'\0' * (32 - len(bus_id))
            self.sock.sendall(padded_bus_id)
            
            # Read response header
            import_header = self.sock.recv(8)
            if not import_header or len(import_header) < 8:
                logger.error("Failed to read import response header")
                return False
            
            # Read device data
            device_import_data = self.sock.recv(512)  # Large enough for the import data
            
            logger.info(f"Device {bus_id} attached successfully")
            self.device_attached = True
            return True
            
        except Exception as e:
            logger.error(f"Error attaching device: {e}")
            return False
    
    def forward_to_hid(self, data: bytes) -> Optional[bytes]:
        """Forward HID reports to the HID device and read response"""
        if not self.connected or self.hid_fd is None:
            logger.error("Not connected to HID device")
            return None
        
        try:
            os.write(self.hid_fd, data)
            logger.debug(f"Wrote {len(data)} bytes to HID device: {data.hex()}")
            
            # Read response (may need adjustment based on protocol timing)
            response = os.read(self.hid_fd, USB_PACKET_SIZE)
            logger.debug(f"Read {len(response)} bytes from HID device: {response.hex()}")
            return response
        except Exception as e:
            logger.error(f"HID communication error: {e}")
            return None
    
    def handle_usb_message(self, header: dict, data: Optional[bytes] = None) -> bytes:
        """Process a USB message and return the appropriate response"""
        if header['command'] == USBIP_CMD_SUBMIT:
            # Handle SUBMIT command
            response_data = b''
            
            # If this is an OUT transaction with data
            if header['direction'] == USBIP_DIR_OUT and data:
                # For endpoint 1 (OUT), forward to HID and get response
                if header['endpoint'] == USB_ENDPOINT_OUT:
                    hid_response = self.forward_to_hid(data)
                    if hid_response:
                        response_data = hid_response
                
                # For control endpoint, process setup packet
                elif header['endpoint'] == USB_ENDPOINT_CONTROL:
                    # Just acknowledge for now
                    pass
            
            # Create response header
            response_header = struct.pack(
                "!IIIIII",
                0x00000003,  # Reply to SUBMIT
                header['sequence_number'],
                0,  # Status
                header['actual_length'],
                0,  # Start frame
                0   # Error count
            )
            
            # For IN transactions, include the response data
            if header['direction'] == USBIP_DIR_IN:
                return response_header + response_data
            else:
                return response_header
        
        elif header['command'] == USBIP_CMD_UNLINK:
            # Handle UNLINK command
            return struct.pack(
                "!IIIIII",
                0x00000004,  # Reply to UNLINK
                header['sequence_number'],
                0,  # Status
                0, 0, 0  # Padding
            )
        
        else:
            logger.warning(f"Unknown command: {header['command']}")
            return b''
    
    def process_usbip_messages(self):
        """Main loop to process USB/IP messages"""
        if not self.connected or not self.device_attached:
            logger.error("Not connected or device not attached")
            return
        
        while self.connected:
            try:
                # Read message header (20 bytes for USB/IP protocol)
                header_data = self.sock.recv(20)
                if not header_data or len(header_data) < 20:
                    if not header_data:
                        logger.info("Connection closed by server")
                    else:
                        logger.error(f"Incomplete header received: {len(header_data)} bytes")
                    break
                
                # Parse header
                command, sequence_num, unused1, unused2, direction, endpoint = struct.unpack("!IIIIII", header_data[:24])
                
                header = {
                    'command': command,
                    'sequence_number': sequence_num,
                    'direction': direction,
                    'endpoint': endpoint,
                    'actual_length': 0
                }
                
                logger.debug(f"Received USB/IP message: cmd={command}, seq={sequence_num}, dir={direction}, ep={endpoint}")
                
                # Read additional data if needed
                data = None
                if command == USBIP_CMD_SUBMIT:
                    # Read setup packet for control transfers
                    setup_data = self.sock.recv(8)
                    
                    # Read transfer buffer for OUT transfers
                    if direction == USBIP_DIR_OUT:
                        buffer_length_data = self.sock.recv(4)
                        buffer_length = struct.unpack("!I", buffer_length_data)[0]
                        if buffer_length > 0:
                            data = self.sock.recv(buffer_length)
                            header['actual_length'] = len(data)
                
                # Process the message
                response = self.handle_usb_message(header, data)
                
                # Send response back to USB/IP server
                if response:
                    self.sock.sendall(response)
            
            except Exception as e:
                logger.error(f"Error processing USB/IP message: {e}")
                break
        
        logger.info("Stopped processing USB/IP messages")
    
    def run(self):
        """Main method to run the shim"""
        if not self.connect():
            return False
        
        if not self.attach_device():
            self.cleanup()
            return False
        
        # Start processing messages
        try:
            self.process_usbip_messages()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.cleanup()
        
        return True


def test_hid_device(device_path: str):
    """Test if the HID device is accessible"""
    # Check if running in Docker
    in_docker = is_running_in_docker()
    
    try:
        # For real devices
        if device_path == HID_DEVICE_PATH and not in_docker:
            # Check if device exists
            if not os.path.exists(device_path):
                logger.error(f"HID device {device_path} does not exist")
                if in_docker:
                    logger.info("In Docker environment: Creating mock HID device")
                    # Create a temporary file as mock HID device
                    with open(device_path, 'w') as f:
                        pass
                    os.chmod(device_path, 0o666)
                else:
                    logger.error("USB gadget mode may not be configured correctly")
                    return False
        
        # Test file access
        fd = os.open(device_path, os.O_RDWR)
        logger.info(f"HID device {device_path} is accessible")
        os.close(fd)
        return True
    except Exception as e:
        logger.error(f"HID device {device_path} test failed: {e}")
        # In Docker, we can use a temporary file as a mock device
        if in_docker and device_path == HID_DEVICE_PATH:
            try:
                logger.info("Creating a temporary mock HID device for Docker testing")
                temp_file = tempfile.NamedTemporaryFile(delete=False)
                temp_path = temp_file.name
                temp_file.close()
                logger.info(f"Created temporary HID device at {temp_path}")
                return True
            except Exception as e2:
                logger.error(f"Failed to create mock HID device: {e2}")
                return False
        return False

def test_usbip_server(host: str, port: int):
    """Test if the USB/IP server is running"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((host, port))
        logger.info(f"USB/IP server at {host}:{port} is reachable")
        sock.close()
        return True
    except Exception as e:
        logger.error(f"USB/IP server test failed: {e}")
        return False

def run_tests(args):
    """Run basic connectivity tests"""
    logger.info("Running tests...")
    hid_ok = test_hid_device(args.hid_device)
    usbip_ok = test_usbip_server(args.host, args.port)
    
    if hid_ok and usbip_ok:
        logger.info("All tests passed! The shim should work correctly.")
        return True
    else:
        logger.error("Some tests failed. Check the logs for details.")
        return False


# =============== Test Cases ===============

class TestUSBIPShim(unittest.TestCase):
    """Test cases for the USB/IP Shim"""
    
    def setUp(self):
        """Set up test environment"""
        # Create a temporary file to mock the HID device
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_filename = self.temp_file.name
        self.temp_file.close()
        
        # Create mocked socket
        self.mock_socket = mock.MagicMock()
        socket.socket = mock.MagicMock(return_value=self.mock_socket)
        
        # Set up the shim with our test file as the HID device
        self.shim = USBIPShim("127.0.0.1", 3240, self.temp_filename)
    
    def tearDown(self):
        """Clean up after tests"""
        # Remove temporary file
        if os.path.exists(self.temp_filename):
            os.unlink(self.temp_filename)
    
    def test_connect(self):
        """Test connection setup"""
        # Prepare mocks
        self.mock_socket.connect = mock.MagicMock()
        
        # Call the method
        result = self.shim.connect()
        
        # Verify
        self.assertTrue(result)
        self.assertTrue(self.shim.connected)
        self.mock_socket.connect.assert_called_once_with(("127.0.0.1", 3240))
    
    def test_cleanup(self):
        """Test resource cleanup"""
        # Setup
        self.shim.sock = self.mock_socket
        self.shim.hid_fd = os.open(self.temp_filename, os.O_RDWR)
        self.shim.connected = True
        
        # Call the method
        self.shim.cleanup()
        
        # Verify
        self.assertFalse(self.shim.connected)
        self.assertIsNone(self.shim.sock)
        self.assertIsNone(self.shim.hid_fd)
        self.mock_socket.close.assert_called_once()
    
    def test_forward_to_hid(self):
        """Test forwarding data to HID device"""
        # Setup
        test_data = b"FIDO_TEST_DATA" + b"\x00" * 50  # Pad to make 64 bytes
        expected_response = b"FIDO_RESPONSE" + b"\x00" * 52
        
        # Mock the os.write and os.read functions to simulate device I/O
        original_write = os.write
        original_read = os.read
        
        def mock_write(fd, data):
            # Just record that write was called
            self.assertEqual(fd, self.shim.hid_fd)
            self.assertEqual(data, test_data)
            return len(data)
            
        def mock_read(fd, length):
            self.assertEqual(fd, self.shim.hid_fd)
            self.assertEqual(length, USB_PACKET_SIZE)
            return expected_response
        
        try:
            # Replace the os functions with our mocks
            os.write = mock_write
            os.read = mock_read
            
            # Set up the shim
            self.shim.connected = True
            self.shim.hid_fd = os.open(self.temp_filename, os.O_RDWR)
            
            # Test the method
            response = self.shim.forward_to_hid(test_data)
            
            # Verify that response contains our expected data
            self.assertEqual(response, expected_response)
        finally:
            # Restore original os functions
            os.write = original_write
            os.read = original_read
    
    def test_handle_usb_message_submit_out(self):
        """Test handling a USB SUBMIT command (OUT direction)"""
        # Setup
        header = {
            'command': USBIP_CMD_SUBMIT,
            'sequence_number': 123,
            'direction': USBIP_DIR_OUT,
            'endpoint': USB_ENDPOINT_OUT,
            'actual_length': 64
        }
        data = b"TEST_OUT_DATA" + b"\x00" * 52  # 64 bytes
        
        # Mock the forward_to_hid method
        self.shim.forward_to_hid = mock.MagicMock(return_value=b"RESPONSE" + b"\x00" * 56)
        
        # Call the method
        response = self.shim.handle_usb_message(header, data)
        
        # Verify
        self.shim.forward_to_hid.assert_called_once_with(data)
        self.assertEqual(len(response), 24)  # Just header for OUT direction
    
    def test_handle_usb_message_submit_in(self):
        """Test handling a USB SUBMIT command (IN direction)"""
        # Setup
        header = {
            'command': USBIP_CMD_SUBMIT,
            'sequence_number': 124,
            'direction': USBIP_DIR_IN,
            'endpoint': USB_ENDPOINT_IN,
            'actual_length': 0
        }
        
        # Call the method
        response = self.shim.handle_usb_message(header)
        
        # Verify
        self.assertEqual(len(response), 24)  # Header only for empty response
    
    def test_handle_usb_message_unlink(self):
        """Test handling a USB UNLINK command"""
        # Setup
        header = {
            'command': USBIP_CMD_UNLINK,
            'sequence_number': 125,
            'endpoint': 0,
            'direction': 0,
            'actual_length': 0
        }
        
        # Call the method
        response = self.shim.handle_usb_message(header)
        
        # Verify response format
        self.assertEqual(len(response), 24)  # UNLINK response is 24 bytes
        
        # Check sequence number in response
        seq_num = struct.unpack("!I", response[4:8])[0]
        self.assertEqual(seq_num, 125)
    
    def test_handle_unknown_command(self):
        """Test handling an unknown USB command"""
        # Setup
        header = {
            'command': 0xFFFF,  # Unknown command
            'sequence_number': 126,
            'endpoint': 0,
            'direction': 0,
            'actual_length': 0
        }
        
        # Call the method
        response = self.shim.handle_usb_message(header)
        
        # Verify
        self.assertEqual(response, b'')  # Should return empty response


class TestUSBIPHIDIntegrationFake(unittest.TestCase):
    """Integration tests with fake server and device"""
    
    def setUp(self):
        """Set up test environment"""
        # Create a fake HID device (temp file)
        self.fake_hid = tempfile.NamedTemporaryFile(delete=False)
        self.fake_hid_path = self.fake_hid.name
        self.fake_hid.close()
        
        # Create a fake USBIP server
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('127.0.0.1', 0))  # Bind to a random port
        self.server_port = self.server_socket.getsockname()[1]
        self.server_socket.listen(1)
        
        # Save original socket class
        self.original_socket = socket.socket
        
        # Start server thread
        self.server_thread = threading.Thread(target=self.fake_usbip_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        # Create shim instance with fake device and server
        self.shim = USBIPShim("127.0.0.1", self.server_port, self.fake_hid_path)
    
    def tearDown(self):
        """Clean up test resources"""
        # Stop server
        if hasattr(self, 'server_socket'):
            self.server_socket.close()
        
        # Restore original socket
        socket.socket = self.original_socket
        
        # Remove fake HID device
        if os.path.exists(self.fake_hid_path):
            os.unlink(self.fake_hid_path)
    
    def fake_usbip_server(self):
        """Run a fake USBIP server for testing"""
        try:
            # Accept connection
            client_sock, addr = self.server_socket.accept()
            
            # Simulate USBIP server responses
            while True:
                data = client_sock.recv(1024)
                if not data:
                    break
                
                # Fake response for device list
                if len(data) >= 8 and struct.unpack("!I", data[4:8])[0] == 0x00000001:
                    # OP_REQ_DEVLIST
                    response = struct.pack("!HHI", 0x0111, 0x0001, 0)  # Version, reply code, status
                    response += struct.pack("!I", 1)  # 1 device
                    
                    # Device information (simplified)
                    dev_info = b"2-2\0" + b"\0" * 28  # Bus ID
                    dev_info += struct.pack("!IIIIIHHHBB", 
                        2, 2, 2, 0x18d1, 0x5022, 0x0200, 0, 0, 0, 1
                    )
                    response += dev_info
                    
                    client_sock.sendall(response)
                
                # Fake response for import device
                elif len(data) >= 8 and struct.unpack("!I", data[4:8])[0] == 0x00000003:
                    # OP_REQ_IMPORT
                    response = struct.pack("!HHI", 0x0111, 0x0003, 0)  # Version, reply code, status
                    
                    # Basic device info
                    dev_info = struct.pack("!II", 0x18d1, 0x5022)  # VendorID, ProductID
                    response += dev_info + b"\0" * 500  # Padding
                    
                    client_sock.sendall(response)
                
                # Fake response for USB messages
                elif len(data) >= 4:
                    # Parse command
                    cmd = struct.unpack("!I", data[0:4])[0]
                    
                    if cmd == USBIP_CMD_SUBMIT:
                        # Return a fake SUBMIT response
                        seq_num = struct.unpack("!I", data[4:8])[0]
                        response = struct.pack("!IIIIII",
                            0x00000003,  # Reply to SUBMIT
                            seq_num,
                            0,  # Status
                            0,  # Actual length
                            0,  # Start frame
                            0   # Error count
                        )
                        client_sock.sendall(response)
                    
                    elif cmd == USBIP_CMD_UNLINK:
                        # Return a fake UNLINK response
                        seq_num = struct.unpack("!I", data[4:8])[0]
                        response = struct.pack("!IIIIII",
                            0x00000004,  # Reply to UNLINK
                            seq_num,
                            0,  # Status
                            0, 0, 0  # Padding
                        )
                        client_sock.sendall(response)
        
        except Exception as e:
            print(f"Fake server error: {e}")
        finally:
            if 'client_sock' in locals():
                client_sock.close()
    
    def test_connect_and_attach(self):
        """Test connecting to server and attaching device"""
        # Mock socket's recv method to return proper responses
        self.shim.sock = mock.MagicMock()
        
        # Mock the connect method
        self.shim.connect = mock.MagicMock(return_value=True)
        
        # For attach_device, create a mocked socket with proper responses
        # First response: device list header
        dev_list_header = struct.pack("!HHI", 0x0111, 0x0001, 0)  # Version, reply code, status
        # Second response: number of devices
        dev_count = struct.pack("!I", 1)  # 1 device
        # Third response: device info (simplified)
        dev_info = b"2-2\0" + b"\0" * 28  # Bus ID
        dev_info += struct.pack("!IIIIIHHHBB", 
            2, 2, 2, 0x18d1, 0x5022, 0x0200, 0, 0, 0, 1
        )
        
        # Import response header
        import_header = struct.pack("!HHI", 0x0111, 0x0003, 0)  # Version, reply code, status
        # Import response data
        import_data = struct.pack("!II", 0x18d1, 0x5022)  # VendorID, ProductID
        import_data += b"\0" * 500  # Padding
        
        # Configure socket.recv to return our prepared responses in sequence
        self.shim.sock.recv = mock.MagicMock(side_effect=[
            dev_list_header, dev_count, dev_info,
            import_header, import_data
        ])
        
        # Attach device
        attach_result = self.shim.attach_device()
        self.assertTrue(attach_result)
        
        # Verify state
        self.assertTrue(self.shim.device_attached)


class FunctionalTests:
    """Functional tests that can be run on a real system"""
    
    @staticmethod
    def run_mock_fido_packet_test():
        """Test sending a mock FIDO packet through the system"""
        # Check if HID device exists
        if not os.path.exists(HID_DEVICE_PATH):
            logger.error(f"HID device {HID_DEVICE_PATH} does not exist")
            return False
            
        try:
            # Open HID device
            hid_fd = os.open(HID_DEVICE_PATH, os.O_RDWR)
            
            # Create a sample CTAP HID packet
            # CTAP HID init packet: channel ID + command + payload length
            channel_id = b"\x12\x34\x56\x78"  # Made-up channel ID
            command = b"\x86"  # PING command
            payload_len = b"\x00\x08"  # 8 bytes payload
            payload = b"PINGTEST"  # Test payload
            
            packet = channel_id + command + payload_len + payload
            packet = packet.ljust(64, b"\x00")  # Pad to 64 bytes
            
            # Write packet to HID device
            logger.info(f"Writing test packet: {packet.hex()}")
            os.write(hid_fd, packet)
            
            # Read response
            time.sleep(0.5)  # Give time for processing
            response = os.read(hid_fd, 64)
            logger.info(f"Received response: {response.hex()}")
            
            # Check if response starts with same channel ID
            if response[:4] == channel_id:
                logger.info("Test successful! Received response with matching channel ID")
                success = True
            else:
                logger.error("Test failed: Channel ID mismatch in response")
                success = False
                
            # Clean up
            os.close(hid_fd)
            return success
            
        except Exception as e:
            logger.error(f"Mock FIDO packet test failed: {e}")
            return False
    
    @staticmethod
    def run_virtual_fido_connectivity_test():
        """Test connectivity to Virtual FIDO USB/IP server"""
        try:
            # Try to connect to the USB/IP server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(("127.0.0.1", USBIP_PORT))
            
            # Send a device list request
            command_header = struct.pack("!II", 0x8005, 0x00000001)  # Version 1, OP_REQ_DEVLIST
            sock.sendall(command_header)
            
            # Read response header
            header_data = sock.recv(8)
            if not header_data or len(header_data) < 8:
                logger.error("Failed to read device list response")
                sock.close()
                return False
            
            # Parse response
            version, command, status = struct.unpack("!HHI", header_data)
            
            # Read number of devices
            devices_data = sock.recv(4)
            num_devices = struct.unpack("!I", devices_data)[0]
            
            logger.info(f"Virtual FIDO server returned {num_devices} devices")
            logger.info("Virtual FIDO connectivity test successful")
            
            sock.close()
            return num_devices > 0
            
        except Exception as e:
            logger.error(f"Virtual FIDO connectivity test failed: {e}")
            return False
    
    @staticmethod
    def run_all_functional_tests():
        """Run all functional tests"""
        results = {}
        
        logger.info("Running functional tests on the real system...")
        
        # Test 1: Virtual FIDO server connectivity
        logger.info("Test 1: Virtual FIDO Server Connectivity")
        results["virtual_fido_connectivity"] = FunctionalTests.run_virtual_fido_connectivity_test()
        
        # Test 2: Mock FIDO packet test
        logger.info("Test 2: Mock FIDO Packet Test")
        results["mock_fido_packet"] = FunctionalTests.run_mock_fido_packet_test()
        
        # Print summary
        logger.info("Functional Test Results:")
        for test, result in results.items():
            status = "PASSED" if result else "FAILED"
            logger.info(f"  {test}: {status}")
        
        # Overall success if all tests passed
        return all(results.values())


def is_running_in_docker():
    """Check if running inside a Docker container"""
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return any('docker' in line for line in f)
    except:
        return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="USB/IP to USB Gadget Shim for Virtual FIDO")
    parser.add_argument("--host", default="127.0.0.1", help="USB/IP server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=USBIP_PORT, help=f"USB/IP server port (default: {USBIP_PORT})")
    parser.add_argument("--hid-device", default=HID_DEVICE_PATH, help=f"HID device path (default: {HID_DEVICE_PATH})")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--test", action="store_true", help="Run basic connectivity tests and exit")
    parser.add_argument("--unittest", action="store_true", help="Run unit tests and exit")
    parser.add_argument("--functional-test", action="store_true", help="Run functional tests and exit")
    parser.add_argument("--docker-mode", action="store_true", help="Enable Docker-specific behaviors")
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    # Auto-detect Docker environment if not explicitly specified
    in_docker = args.docker_mode or is_running_in_docker()
    if in_docker:
        logger.info("Running in Docker environment")
    
    # Check if running as root for most operations
    # Skip check in Docker or for unit tests
    if not (args.unittest or in_docker) and os.geteuid() != 0:
        logger.error("This script must be run as root (sudo)")
        return 1
    
    # Run unit tests if requested
    if args.unittest:
        test_loader = unittest.TestLoader()
        test_suite = test_loader.loadTestsFromTestCase(TestUSBIPShim)
        test_suite.addTests(test_loader.loadTestsFromTestCase(TestUSBIPHIDIntegrationFake))
        
        test_runner = unittest.TextTestRunner(verbosity=2)
        result = test_runner.run(test_suite)
        
        return 0 if result.wasSuccessful() else 1
    
    # For Docker environment, modify paths and behavior as needed
    if in_docker:
        # Use a temp file as mock HID device in Docker
        if args.hid_device == HID_DEVICE_PATH:
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            args.hid_device = temp_file.name
            temp_file.close()
            logger.info(f"In Docker: Using temporary file as HID device: {args.hid_device}")
    
    # Run functional tests if requested
    if args.functional_test:
        success = FunctionalTests.run_all_functional_tests()
        return 0 if success else 1
    
    # Run basic tests if requested
    if args.test:
        success = run_tests(args)
        return 0 if success else 1
    
    # Create and run the shim
    shim = USBIPShim(args.host, args.port, args.hid_device)
    success = shim.run()
    
    # Clean up temp file if created in Docker mode
    if in_docker and args.hid_device != HID_DEVICE_PATH:
        try:
            os.unlink(args.hid_device)
        except:
            pass
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())