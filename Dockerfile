FROM golang:1.19

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    libusb-1.0-0-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Go module files first to leverage Docker caching
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the project files
COPY . .

# Install Python dependencies
RUN pip3 install pytest

# Make scripts executable
RUN chmod +x run_tests.sh run_integration_tests.sh docker_test_helper.py usbip_to_gadget.py

# Build the virtual-fido demo application
RUN cd cmd/demo && go build -o demo

# Set the entrypoint
ENTRYPOINT ["/bin/bash"]