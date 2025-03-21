#!/bin/bash
# CI/CD test script for Virtual FIDO in Docker
# This script runs all tests in a non-interactive way for CI/CD pipelines

set -e  # Exit on error

echo "===== Virtual FIDO CI/CD Tests ====="

# Build Docker image
echo "Building Docker image..."
docker build -t virtual-fido-test .

# Run unit tests
echo "===== Running unit tests ====="
docker run --rm virtual-fido-test -c "cd /app && python3 usbip_to_gadget.py --unittest"

# Run the Virtual FIDO server and Docker integration tests
echo "===== Running integration tests ====="
docker run --rm virtual-fido-test -c "cd /app && \
    (cd cmd/demo && ./demo start &) && \
    sleep 3 && \
    python3 docker_test_helper.py"

echo "===== All tests passed! ====="
exit 0