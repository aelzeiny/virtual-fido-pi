# Docker Integration Tests for Virtual FIDO

This directory contains Docker configuration for running integration tests for the Virtual FIDO project and the USB/IP to USB Gadget shim.

## Overview

The Docker setup provides an isolated environment for testing the virtual-fido codebase and the Python shim (`usbip_to_gadget.py`) without requiring a physical Raspberry Pi. This allows for:

1. Automated testing of the shim's unit tests
2. Integration testing of the communication between the Virtual FIDO server and the shim
3. A consistent testing environment across different development machines

## Requirements

- Docker
- Docker Compose (optional)

## Running Tests

There are two ways to run tests:

### Option 1: Using the test script

The `run_integration_tests.sh` script provides an interactive menu for running different test configurations:

```bash
./run_integration_tests.sh
```

It offers the following options:

1. Run unit tests only - Tests the Python shim without the Virtual FIDO server
2. Run integration tests - Tests the communication between the Virtual FIDO server and the shim
3. Run all tests - Runs both unit and integration tests
4. Start an interactive shell - Launches a bash shell in the container for manual testing

### Option 2: Using Docker Compose

For a more automated approach, you can use Docker Compose:

```bash
docker-compose up
```

This will:
1. Build the Docker image if needed
2. Start the Virtual FIDO server
3. Run the unit tests for the Python shim

## Advanced Usage

### Running Different Test Types

To run specific test types manually:

```bash
# Build the image
docker build -t virtual-fido-test .

# Unit tests only
docker run --rm virtual-fido-test -c "cd /app && python3 usbip_to_gadget.py --unittest"

# Start Virtual FIDO server and run connectivity tests
docker run --rm virtual-fido-test -c "cd /app && (cd cmd/demo && ./demo start &) && sleep 3 && python3 usbip_to_gadget.py --test"
```

### Modifying Test Behavior

To modify how tests run, you can edit the following files:

- `Dockerfile` - Container environment and dependencies
- `docker-compose.yml` - Services configuration
- `run_integration_tests.sh` - Test execution script

## Limitations

- The Docker environment cannot fully simulate a physical Raspberry Pi with USB gadget mode
- Functional tests requiring actual USB hardware connections cannot be run in this environment
- The Docker environment mocks socket connections and file I/O operations for testing

## Extending the Tests

To add more tests:

1. Add new test cases to `usbip_to_gadget.py` in the appropriate test classes
2. For integration tests requiring additional services, update the Docker Compose file

## Troubleshooting

If you encounter issues:

- Ensure Docker is installed and running
- Make sure you have permissions to use Docker (or run with sudo)
- Check if any required ports are already in use
- Verify the Virtual FIDO server is running inside the container before testing connections