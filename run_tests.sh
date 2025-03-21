#!/bin/bash
# Test runner script for the USB/IP to USB Gadget Shim

set -e  # Exit on error

echo "===== Running tests for USB/IP to USB Gadget Shim ====="

# Display test options
echo "Test options:"
echo "  1. Unit tests (no root required)"
echo "  2. Connectivity tests (requires root and configured environment)"
echo "  3. Functional tests (requires root, Virtual FIDO server, and configured USB gadget)"
echo "  4. All tests"

# Get user choice
read -p "Enter test number (1-4): " test_choice

case $test_choice in
  1)
    echo "===== Running unit tests ====="
    python3 usbip_to_gadget.py --unittest
    ;;
  2)
    echo "===== Running connectivity tests ====="
    echo "Note: This requires root access and properly configured environment"
    sudo python3 usbip_to_gadget.py --test
    ;;
  3)
    echo "===== Running functional tests ====="
    echo "Note: This requires root access, running Virtual FIDO server, and configured USB gadget"
    sudo python3 usbip_to_gadget.py --functional-test
    ;;
  4)
    echo "===== Running all tests ====="
    
    echo "First: Unit tests (no root required)"
    python3 usbip_to_gadget.py --unittest
    
    echo "Second: Connectivity tests"
    sudo python3 usbip_to_gadget.py --test
    
    echo "Third: Functional tests"
    sudo python3 usbip_to_gadget.py --functional-test
    ;;
  *)
    echo "Invalid option. Exiting."
    exit 1
    ;;
esac

echo "===== Tests completed ====="