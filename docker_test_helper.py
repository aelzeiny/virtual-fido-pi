#!/usr/bin/env python3
"""
Docker Test Helper for Virtual FIDO Integration Tests

This script provides helper functions to run integration tests in Docker.
It creates mock objects and file system structures to support testing
without requiring actual hardware.
"""

import os
import sys
import tempfile
import socket
import struct
import threading
import time
import unittest
import logging
from unittest import mock

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('docker_test_helper')

# Constants for testing
USBIP_PORT = 3240
HID_DEVICE_PATH = '/dev/hidg0'
USB_PACKET_SIZE = 64
MOCK_HID_PATH = None

class MockUSBIPServer:
    """Mock USB/IP server for testing"""
    
    def __init__(self, host='127.0.0.1', port=USBIP_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the mock server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set socket option to reuse address
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            logger.info(f"Mock USB/IP server listening on {self.host}:{self.port}")
            
            self.running = True
            self.thread = threading.Thread(target=self._server_loop)
            self.thread.daemon = True
            self.thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Failed to start mock USB/IP server: {e}")
            self.cleanup()
            return False
    
    def _server_loop(self):
        """Main server loop"""
        try:
            while self.running:
                # Set a timeout for accept to allow checking running state
                self.server_socket.settimeout(1.0)
                try:
                    client, addr = self.server_socket.accept()
                    logger.info(f"Client connected from {addr}")
                    self.client_socket = client
                    self._handle_client(client)
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error accepting connection: {e}")
                    if self.client_socket:
                        self.client_socket.close()
                        self.client_socket = None
        except Exception as e:
            logger.error(f"Server loop error: {e}")
        finally:
            self.cleanup()
    
    def _handle_client(self, client):
        """Handle client connection"""
        try:
            while self.running:
                # Receive data with timeout
                client.settimeout(1.0)
                try:
                    data = client.recv(1024)
                    if not data:
                        logger.info("Client disconnected")
                        break
                    
                    # Parse command header
                    if len(data) >= 8:
                        # Handle device list request
                        if data[4:8] == b'\x00\x00\x00\x01':  # OP_REQ_DEVLIST
                            logger.info("Received device list request")
                            self._send_device_list(client)
                        
                        # Handle device import request
                        elif data[4:8] == b'\x00\x00\x00\x03':  # OP_REQ_IMPORT
                            logger.info("Received device import request")
                            self._send_device_import(client)
                        
                        # Handle USB commands
                        elif len(data) >= 4:
                            cmd = struct.unpack("!I", data[0:4])[0]
                            logger.info(f"Received USB command: {cmd}")
                            
                            # SUBMIT command
                            if cmd == 0x00000001:
                                seq_num = struct.unpack("!I", data[4:8])[0]
                                self._send_submit_response(client, seq_num)
                            
                            # UNLINK command
                            elif cmd == 0x00000002:
                                seq_num = struct.unpack("!I", data[4:8])[0]
                                self._send_unlink_response(client, seq_num)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error handling client data: {e}")
                    break
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            if client:
                client.close()
    
    def _send_device_list(self, client):
        """Send a mock device list response"""
        # Version, reply code, status
        response = struct.pack("!HHI", 0x0111, 0x0001, 0)
        # Number of devices
        response += struct.pack("!I", 1)
        
        # Device information (simplified)
        dev_info = b"2-2\0" + b"\0" * 28  # Bus ID
        dev_info += struct.pack("!IIIIIHHHBB", 
            2, 2, 2, 0x18d1, 0x5022, 0x0200, 0, 0, 0, 1
        )
        response += dev_info
        
        client.sendall(response)
    
    def _send_device_import(self, client):
        """Send a mock device import response"""
        # Version, reply code, status
        response = struct.pack("!HHI", 0x0111, 0x0003, 0)
        
        # Basic device info
        dev_info = struct.pack("!II", 0x18d1, 0x5022)  # VendorID, ProductID
        response += dev_info + b"\0" * 500  # Padding
        
        client.sendall(response)
    
    def _send_submit_response(self, client, seq_num):
        """Send a mock submit response"""
        response = struct.pack("!IIIIII",
            0x00000003,  # Reply to SUBMIT
            seq_num,
            0,  # Status
            0,  # Actual length
            0,  # Start frame
            0   # Error count
        )
        client.sendall(response)
    
    def _send_unlink_response(self, client, seq_num):
        """Send a mock unlink response"""
        response = struct.pack("!IIIIII",
            0x00000004,  # Reply to UNLINK
            seq_num,
            0,  # Status
            0, 0, 0  # Padding
        )
        client.sendall(response)
    
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        logger.info("Mock USB/IP server cleaned up")


def create_mock_hid_device():
    """Create a mock HID device file"""
    global MOCK_HID_PATH
    
    # Create a temporary file to use as the mock HID device
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    MOCK_HID_PATH = temp_file.name
    temp_file.close()
    
    logger.info(f"Created mock HID device at {MOCK_HID_PATH}")
    return MOCK_HID_PATH


def cleanup_mock_hid_device():
    """Clean up the mock HID device"""
    global MOCK_HID_PATH
    
    if MOCK_HID_PATH and os.path.exists(MOCK_HID_PATH):
        try:
            os.unlink(MOCK_HID_PATH)
            logger.info(f"Removed mock HID device at {MOCK_HID_PATH}")
        except Exception as e:
            logger.error(f"Failed to remove mock HID device: {e}")
        
        MOCK_HID_PATH = None


def mock_open_device():
    """Setup mock device environment"""
    # Create mock HID device
    mock_path = create_mock_hid_device()
    
    # Start mock USB/IP server
    server = MockUSBIPServer()
    if not server.start():
        cleanup_mock_hid_device()
        return None, None
    
    return server, mock_path


def run_tests():
    """Run Docker-specific integration tests"""
    logger.info("Running Docker integration tests")
    
    # Import the shim - do this here to avoid circular imports
    from usbip_to_gadget import USBIPShim
    
    # Setup the test environment
    server, mock_path = mock_open_device()
    if not server or not mock_path:
        logger.error("Failed to create test environment")
        return False
    
    try:
        # Create a shim using the mock device
        shim = USBIPShim("127.0.0.1", USBIP_PORT, mock_path)
        
        # Connect
        connected = shim.connect()
        if not connected:
            logger.error("Failed to connect to USB/IP server")
            return False
        
        logger.info("Successfully connected to mock USB/IP server")
        
        # Try to attach device
        attached = shim.attach_device()
        if not attached:
            logger.error("Failed to attach device")
            return False
        
        logger.info("Successfully attached mock device")
        
        # Forward a test message
        test_data = b"FIDO_TEST" + b"\0" * 56
        result = shim.forward_to_hid(test_data)
        
        logger.info("Test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Test error: {e}")
        return False
    finally:
        # Clean up
        if server:
            server.cleanup()
        
        cleanup_mock_hid_device()
        
        logger.info("Test environment cleaned up")


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)