#!/bin/bash
# Integration test script for Virtual FIDO using Docker

set -e  # Exit on error

echo "===== Virtual FIDO Integration Tests ====="

# Build Docker image
echo "Building Docker image..."
docker build -t virtual-fido-test .

# Display test options
echo
echo "Test options:"
echo "  1. Run unit tests only"
echo "  2. Run integration tests (requires Virtual FIDO server)"
echo "  3. Run all tests"
echo "  4. Start an interactive shell"
echo

# Get user choice
read -p "Enter test number (1-4): " test_choice

case $test_choice in
  1)
    echo "===== Running unit tests ====="
    docker run --rm virtual-fido-test -c "cd /app && python3 usbip_to_gadget.py --unittest"
    ;;
  2)
    echo "===== Running integration tests ====="
    docker run --rm virtual-fido-test -c "cd /app && \
      (cd cmd/demo && ./demo start &) && \
      sleep 3 && \
      python3 usbip_to_gadget.py --test"
    ;;
  3)
    echo "===== Running all tests ====="
    docker run --rm virtual-fido-test -c "cd /app && \
      python3 usbip_to_gadget.py --unittest && \
      (cd cmd/demo && ./demo start &) && \
      sleep 3 && \
      python3 usbip_to_gadget.py --test"
    ;;
  4)
    echo "===== Starting interactive shell ====="
    echo "Note: To manually run tests:"
    echo "  1. Start the Virtual FIDO server: cd cmd/demo && ./demo start"
    echo "  2. In another terminal: python3 usbip_to_gadget.py --unittest"
    echo "  3. To run connectivity tests: python3 usbip_to_gadget.py --test"
    echo
    docker run --rm -it virtual-fido-test
    ;;
  *)
    echo "Invalid option. Exiting."
    exit 1
    ;;
esac

echo "===== Tests completed ====="