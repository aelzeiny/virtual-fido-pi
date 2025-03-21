# Setting up a Raspberry Pi Zero 2W as a FIDO2 Authenticator

This tutorial will guide you through configuring a Raspberry Pi Zero 2W as a hardware FIDO2 authenticator using the Virtual FIDO software. The implementation connects the FIDO protocol logic from the Virtual FIDO project with the USB gadget mode functionality of the Raspberry Pi.

## Prerequisites
- Raspberry Pi Zero 2W
- MicroSD card (8GB+ recommended)
- Micro USB cable for connecting to the OTG port
- Internet connection for initial setup
- Basic familiarity with Linux and command line

## Part 1: Initial Raspberry Pi Zero 2W Setup

### Step 1: Install Raspberry Pi OS Lite
1. Download Raspberry Pi OS Lite (32-bit) from the [Raspberry Pi website](https://www.raspberrypi.org/software/operating-systems/)
   * Note: 32-bit is recommended for USB gadget mode compatibility
2. Flash the OS to your microSD card using Raspberry Pi Imager or Balena Etcher
3. Before ejecting, create these files on the boot partition:

   a. Create an empty file named `ssh` to enable SSH
   
   ```bash
   touch /media/[username]/boot/ssh
   ```
   
   b. Create a `wpa_supplicant.conf` file for Wi-Fi setup
   
   ```bash
   nano /media/[username]/boot/wpa_supplicant.conf
   ```
   
   Add the following content:
   
   ```
   country=US
   ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
   update_config=1
   
   network={
       ssid="YOUR_WIFI_NAME"
       psk="YOUR_WIFI_PASSWORD"
       key_mgmt=WPA-PSK
   }
   ```

### Step 2: Enable USB OTG Mode

1. Edit the `config.txt` file on the boot partition:

   ```bash
   nano /media/[username]/boot/config.txt
   ```

2. Add these lines at the end:

   ```
   # Enable USB OTG
   dtoverlay=dwc2
   ```

3. Edit the `cmdline.txt` file:

   ```bash
   nano /media/[username]/boot/cmdline.txt
   ```

4. After `rootwait`, add a space followed by:

   ```
   modules-load=dwc2,libcomposite
   ```

5. Insert the SD card into your Raspberry Pi Zero 2W and power it on

### Step 3: Connect to Your Raspberry Pi

1. Find your Pi's IP address (check your router's DHCP client list)
2. SSH into your Raspberry Pi:

   ```bash
   ssh pi@YOUR_PI_IP_ADDRESS
   ```

   Default password: `raspberry`

3. Secure your Pi:

   ```bash
   sudo passwd pi
   ```

## Part 2: Setting Up USB Gadget Mode for FIDO

### Step 1: Create USB Gadget Configuration Script

1. Create the configuration script:

   ```bash
   sudo nano /usr/bin/fido_gadget_setup.sh
   ```

2. Add the following content:

   ```bash
   #!/bin/bash
   
   # Make sure configfs is mounted
   mount -t configfs none /sys/kernel/config 2>/dev/null || true
   
   cd /sys/kernel/config/usb_gadget/
   
   # Remove any existing gadget configuration
   if [ -d "fido" ]; then
     # Disable the gadget
     if [ -f "fido/UDC" ]; then
       echo "" > fido/UDC
     fi
     
     # Clean up existing functions
     for func in fido/configs/c.1/*; do
       if [ -L "$func" ]; then
         rm -f "$func"
       fi
     done
     
     # Remove the gadget
     rmdir fido/configs/c.1/strings/0x409 2>/dev/null || true
     rmdir fido/configs/c.1 2>/dev/null || true
     rmdir fido/functions/hid.usb0 2>/dev/null || true
     rmdir fido/strings/0x409 2>/dev/null || true
     rmdir fido 2>/dev/null || true
   fi
   
   # Create a new gadget
   mkdir -p fido
   cd fido
   
   # Set USB identification parameters to match Google Inc. tk-x001
   echo 0x18d1 > idVendor  # Google Inc.
   echo 0x5022 > idProduct # Custom product ID
   echo 0x0200 > bcdUSB    # USB 2.0
   echo 0x0100 > bcdDevice # Device version 1.0
   
   # Setup device strings
   mkdir -p strings/0x409
   echo "Google Inc." > strings/0x409/manufacturer
   echo "tk-x001" > strings/0x409/product
   
   # Create configuration
   mkdir -p configs/c.1/strings/0x409
   echo "FIDO Configuration" > configs/c.1/strings/0x409/configuration
   echo 120 > configs/c.1/MaxPower
   
   # Create HID function for FIDO
   mkdir -p functions/hid.usb0
   
   # Configure HID function
   echo 0 > functions/hid.usb0/protocol
   echo 0 > functions/hid.usb0/subclass
   echo 64 > functions/hid.usb0/report_length
   
   # HID report descriptor for FIDO U2F/CTAP (from virtual-fido repo)
   # This matches the report descriptor in virtual-fido/usb/usb_device.go
   echo -ne \\x06\\xd0\\xf1\\x09\\x01\\xa1\\x01\\x09\\x20\\x15\\x00\\x26\\xff\\x00\\x75\\x08\\x95\\x40\\x81\\x02\\x09\\x21\\x15\\x00\\x26\\xff\\x00\\x75\\x08\\x95\\x40\\x91\\x02\\xc0 > functions/hid.usb0/report_desc
   
   # Link function to configuration
   ln -s functions/hid.usb0 configs/c.1/
   
   # Enable the gadget by binding to the UDC driver
   ls /sys/class/udc > UDC
   
   # Give proper permissions to HID device
   sleep 1
   chmod 666 /dev/hidg0
   ```

3. Make the script executable:

   ```bash
   sudo chmod +x /usr/bin/fido_gadget_setup.sh
   ```

### Step 2: Configure the Gadget to Start at Boot

1. Create a systemd service:

   ```bash
   sudo nano /etc/systemd/system/fido-gadget.service
   ```

2. Add the following content:

   ```
   [Unit]
   Description=FIDO USB Gadget
   After=network.target
   
   [Service]
   Type=oneshot
   ExecStart=/usr/bin/fido_gadget_setup.sh
   RemainAfterExit=yes
   
   [Install]
   WantedBy=multi-user.target
   ```

3. Enable the service:

   ```bash
   sudo systemctl enable fido-gadget.service
   sudo systemctl start fido-gadget.service
   ```

## Part 3: Installing Virtual FIDO and Building the Bridge

### Step 1: Install Required Dependencies

```bash
sudo apt update
sudo apt install -y git golang libusb-1.0-0-dev build-essential
```

### Step 2: Clone Virtual FIDO Repository

```bash
cd ~
git clone https://github.com/bulwarkid/virtual-fido.git
cd virtual-fido
```

### Step 3: Create the FIDO-HID Bridge

We'll create a custom application that bridges the Virtual FIDO functionality with the Linux HID gadget device.

1. Create a project directory:

```bash
mkdir -p ~/fido-bridge
cd ~/fido-bridge
```

2. Initialize the Go module:

```bash
go mod init fido-bridge
```

3. Create a Go mod file to import the Virtual FIDO package:

```bash
cat > go.mod << 'EOF'
module fido-bridge

go 1.18

require github.com/bulwarkid/virtual-fido v0.0.0

replace github.com/bulwarkid/virtual-fido => /home/pi/virtual-fido
EOF
```

4. Create the bridge application:

```bash
nano main.go
```

5. Add the following content to `main.go`:

```go
package main

import (
	"crypto/sha256"
	"fmt"
	"io"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	virtual_fido "github.com/bulwarkid/virtual-fido"
	"github.com/bulwarkid/virtual-fido/ctap"
	"github.com/bulwarkid/virtual-fido/ctap_hid"
	"github.com/bulwarkid/virtual-fido/fido_client"
	"github.com/bulwarkid/virtual-fido/identities"
	"github.com/bulwarkid/virtual-fido/u2f"
	"github.com/bulwarkid/virtual-fido/util"
)

// HIDDevice represents the Linux HID gadget device
type HIDDevice struct {
	file        *os.File
	responseCh  chan []byte
	delegate    ctap_hid.CTAPHIDDelegate
	isConnected bool
	mutex       sync.Mutex
}

// NewHIDDevice creates a new HID device
func NewHIDDevice(devicePath string) (*HIDDevice, error) {
	file, err := os.OpenFile(devicePath, os.O_RDWR, 0666)
	if err != nil {
		return nil, fmt.Errorf("failed to open HID device: %v", err)
	}

	hid := &HIDDevice{
		file:        file,
		responseCh:  make(chan []byte, 10),
		isConnected: true,
	}

	return hid, nil
}

// SetDelegate sets the CTAP HID delegate
func (hid *HIDDevice) SetDelegate(delegate ctap_hid.CTAPHIDDelegate) {
	hid.delegate = delegate
}

// Start begins listening for HID messages
func (hid *HIDDevice) Start() {
	// Start the reader goroutine
	go hid.readLoop()

	// Start the writer goroutine
	go hid.writeLoop()
}

// readLoop continuously reads from the HID device
func (hid *HIDDevice) readLoop() {
	buffer := make([]byte, 64)
	for {
		n, err := hid.file.Read(buffer)
		if err != nil {
			if err != io.EOF {
				fmt.Printf("Error reading from HID device: %v\n", err)
			}
			time.Sleep(500 * time.Millisecond)
			continue
		}

		if n > 0 {
			// Make a copy of the data to avoid buffer reuse issues
			data := make([]byte, n)
			copy(data, buffer[:n])
			
			// Process the HID message
			if hid.delegate != nil {
				go hid.delegate.HandleMessage(data)
			}
		}
	}
}

// writeLoop handles sending responses back to the HID device
func (hid *HIDDevice) writeLoop() {
	for {
		select {
		case response := <-hid.responseCh:
			hid.mutex.Lock()
			_, err := hid.file.Write(response)
			hid.mutex.Unlock()
			if err != nil {
				fmt.Printf("Error writing to HID device: %v\n", err)
			}
		}
	}
}

// SendResponse sends a response back to the host
func (hid *HIDDevice) SendResponse(response []byte) {
	// Pad the response to 64 bytes if necessary
	if len(response) < 64 {
		paddedResponse := make([]byte, 64)
		copy(paddedResponse, response)
		response = paddedResponse
	}
	
	// Send in chunks of 64 bytes
	for i := 0; i < len(response); i += 64 {
		end := i + 64
		if end > len(response) {
			end = len(response)
		}
		chunk := response[i:end]
		hid.responseCh <- chunk
	}
}

// AutoApproveSupport implements the FIDO client interfaces with auto-approval
type AutoApproveSupport struct {
	vaultFilename   string
	vaultPassphrase string
}

// ApproveClientAction automatically approves all authentication requests
func (support *AutoApproveSupport) ApproveClientAction(action fido_client.ClientAction, params fido_client.ClientActionRequestParams) bool {
	fmt.Printf("Auto-approving action: %d for %s\n", action, params.RelyingParty)
	return true
}

// SaveData saves credential data to the vault file
func (support *AutoApproveSupport) SaveData(data []byte) {
	f, err := os.OpenFile(support.vaultFilename, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0755)
	if err != nil {
		fmt.Printf("Error saving vault data: %v\n", err)
		return
	}
	defer f.Close()
	
	_, err = f.Write(data)
	if err != nil {
		fmt.Printf("Error writing vault data: %v\n", err)
	}
}

// RetrieveData loads credential data from the vault file
func (support *AutoApproveSupport) RetrieveData() []byte {
	f, err := os.Open(support.vaultFilename)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		fmt.Printf("Error opening vault: %v\n", err)
		return nil
	}
	defer f.Close()
	
	data, err := io.ReadAll(f)
	if err != nil {
		fmt.Printf("Error reading vault data: %v\n", err)
		return nil
	}
	return data
}

// Passphrase returns the vault passphrase
func (support *AutoApproveSupport) Passphrase() string {
	return support.vaultPassphrase
}

func main() {
	// Configure logging
	virtual_fido.SetLogOutput(os.Stdout)
	virtual_fido.SetLogLevel(util.LogLevelDebug)
	
	// Create the HID device
	hidDevice, err := NewHIDDevice("/dev/hidg0")
	if err != nil {
		fmt.Printf("Failed to open HID device: %v\n", err)
		return
	}
	
	fmt.Println("HID device opened successfully")
	
	// Initialize the FIDO client
	vaultFilename := "vault.json"
	passphrase := "raspberry" // Consider changing this to a more secure value
	
	// Create CA keys and certificate for attestation
	caPrivateKey, err := identities.CreateCAPrivateKey()
	if err != nil {
		fmt.Printf("Error creating CA private key: %v\n", err)
		return
	}
	
	certificateAuthority, err := identities.CreateSelfSignedCA(caPrivateKey)
	if err != nil {
		fmt.Printf("Error creating CA certificate: %v\n", err)
		return
	}
	
	encryptionKey := sha256.Sum256([]byte(passphrase))
	
	// Create the client support
	support := &AutoApproveSupport{
		vaultFilename:   vaultFilename,
		vaultPassphrase: passphrase,
	}
	
	// Initialize the FIDO client
	fidoClient := fido_client.NewDefaultClient(
		certificateAuthority,
		caPrivateKey,
		encryptionKey,
		false, // Don't require PIN
		support,
		support,
	)
	
	// Initialize the CTAP and U2F servers
	ctapServer := ctap.NewCTAPServer(fidoClient)
	u2fServer := u2f.NewU2FServer(fidoClient)
	
	// Initialize the CTAP HID server
	ctapHIDServer := ctap_hid.NewCTAPHIDServer(ctapServer, u2fServer)
	
	// Connect the HID device to the CTAP HID server
	ctapHIDServer.SetResponseHandler(hidDevice.SendResponse)
	hidDevice.SetDelegate(ctapHIDServer)
	
	// Start the HID device
	hidDevice.Start()
	
	fmt.Println("FIDO Bridge started. Auto-approving all authentication requests.")
	
	// Handle SIGINT gracefully
	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c
	
	fmt.Println("Shutting down...")
	os.Exit(0)
}
```

### Step 4: Build the Bridge Application

```bash
cd ~/fido-bridge
go build -o fido-bridge
```

### Step 5: Create a Systemd Service for the Bridge

1. Create the service file:

```bash
sudo nano /etc/systemd/system/fido-bridge.service
```

2. Add the following content:

```
[Unit]
Description=FIDO HID Bridge Service
After=network.target fido-gadget.service
Wants=fido-gadget.service

[Service]
ExecStart=/home/pi/fido-bridge/fido-bridge
User=root
WorkingDirectory=/home/pi/fido-bridge
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:

```bash
sudo systemctl enable fido-bridge.service
sudo systemctl start fido-bridge.service
```

## Part 4: Testing Your FIDO2 Authenticator

1. Connect your Raspberry Pi Zero 2W to your computer using the Micro USB OTG port (not the power port)
   * Note: You may need a separate power source when using the OTG port for data

2. The Pi should be detected as a USB FIDO device named "tk-x001" from "Google Inc."

3. Check that it's properly recognized:
   * On Windows: Device Manager should show a "tk-x001" HID device
   * On Linux: `lsusb` should show a Google Inc. device
   * On macOS: System Information > USB should show a "tk-x001" device

4. Visit a WebAuthn test site like [webauthn.io](https://webauthn.io) or [demo.yubico.com/webauthn](https://demo.yubico.com/webauthn-technical/registration)

5. Register a new credential - the Pi will auto-approve the request

6. Test authentication to verify it's working properly

## Troubleshooting

### Viewing Logs
To see what's happening with the FIDO bridge service:
```bash
sudo journalctl -u fido-bridge.service -f
```

To check the USB gadget configuration:
```bash
sudo journalctl -u fido-gadget.service
```

### USB Device Issues
If the device isn't recognized:
```bash
# Check USB gadget status
ls -la /sys/kernel/config/usb_gadget/fido/
ls -la /dev/hidg0

# Verify USB connection
dmesg | grep -i usb

# Restart the gadget service
sudo systemctl restart fido-gadget.service
```

### HID Device Permissions
If the FIDO bridge can't access the HID device:
```bash
sudo chmod 666 /dev/hidg0
```

### Bridge Application Issues
If the bridge application fails to start:
```bash
# Check for errors
cd ~/fido-bridge
./fido-bridge

# Verify Go installation
go version

# Update dependencies
go mod tidy
```

### Restart All Services
```bash
sudo systemctl restart fido-gadget.service
sudo systemctl restart fido-bridge.service
```

## Security Considerations

1. **Auto-Approval**: This implementation automatically approves all authentication requests without user confirmation. For increased security in production:
   * Add a physical button connected to a GPIO pin
   * Modify the `ApproveClientAction` method to wait for button press

2. **Encryption Keys**: The vault password is hardcoded in this example. For production use:
   * Generate a random passphrase on first boot
   * Store it securely (e.g., in a TPM if available)

3. **Development Status**: The Virtual FIDO library is in beta. Do not use this for high-security applications without thorough testing.

## How It Works

This implementation creates a bidirectional bridge between:
1. The USB HID gadget functionality of the Raspberry Pi, which presents as a USB FIDO device to the host computer
2. The Virtual FIDO software, which implements the FIDO2/U2F protocol logic

The flow is:
1. USB HID commands come from the host computer to `/dev/hidg0`
2. Our bridge application reads these commands and passes them to the CTAP HID server
3. The CTAP HID server processes them through the FIDO client
4. Responses are sent back to the host computer via the HID device

## References
- [Virtual FIDO Repository](https://github.com/bulwarkid/virtual-fido)
- [Raspberry Pi USB Gadget Documentation](https://www.kernel.org/doc/Documentation/usb/gadget_configfs.txt)
- [Linux USB HID Gadget Documentation](https://www.kernel.org/doc/html/latest/usb/gadget_hid.html)
- [FIDO2 Specification](https://fidoalliance.org/specifications/)
- [WebAuthn Specification](https://www.w3.org/TR/webauthn-2/)