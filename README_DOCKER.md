# Docker Testing Environment for Virtual FIDO

This directory contains Docker configuration for testing the Virtual FIDO project and the USB/IP to USB Gadget shim.

## Overview

The Docker environment provided here allows for different types of testing:

1. **Unit Tests**: Test the Python shim functionality in isolation
2. **Integration Tests**: Test the communication between the Virtual FIDO server and the Python shim
3. **CI/CD Tests**: Non-interactive tests for continuous integration pipelines

## Files

- `Dockerfile` - Container definition with Go and Python dependencies
- `docker-compose.yml` - Service configuration for running tests
- `docker_test_helper.py` - Helper script for mocking USB/IP and HID functionality in Docker
- `run_integration_tests.sh` - Interactive script for running tests in Docker
- `ci_test.sh` - Non-interactive script for CI/CD pipelines

## Usage

### Option 1: Interactive Testing

Run the interactive test script which provides a menu of options:

```bash
./run_integration_tests.sh
```

### Option 2: Docker Compose

Run tests using Docker Compose:

```bash
docker-compose up
```

### Option 3: CI/CD Testing

Run all tests non-interactively:

```bash
./ci_test.sh
```

## What Gets Tested

The Docker environment tests:

1. **Python Shim Code**: The core logic of the USB/IP to HID gadget bridge
2. **Server Connectivity**: Communication with the Virtual FIDO USB/IP server
3. **Protocol Handling**: USB/IP protocol message handling and responses
4. **Error Handling**: Proper response to error conditions and edge cases

## Docker Environment vs. Real Hardware

The Docker tests use mock objects to simulate hardware:

- Mock USB/IP server for testing client connections
- Temporary files as stand-ins for HID devices
- Simulated device responses for protocol testing

While this approach allows for thorough testing without physical hardware, some aspects can only be fully tested on actual Raspberry Pi hardware:

- Real USB HID gadget functionality
- Host computer detection of the FIDO device
- End-to-end WebAuthn registration and authentication

## Contributing

When adding new features or fixing bugs, please:

1. Add appropriate test cases to the Python shim
2. Update the Docker test environment if needed
3. Verify that both Docker tests and (if possible) physical hardware tests pass

## Troubleshooting

If you encounter issues with the Docker tests:

- Ensure Docker is installed and running
- Check that port 3240 is not in use by another application
- Verify that the Virtual FIDO server is running inside the container when testing connections
- For persistent issues, try building a fresh Docker image: `docker build --no-cache -t virtual-fido-test .`