# USB/IP to USB Gadget Shim for Virtual FIDO

This guide explains how to set up a Raspberry Pi Zero 2W as a FIDO2 authenticator using the Virtual FIDO project and a simple USB/IP to USB Gadget shim.

## Overview

This implementation uses:

1. The existing Virtual FIDO codebase with its USB/IP implementation
2. A Python shim that connects the USB/IP protocol to the USB gadget HID device
3. Raspberry Pi Zero 2W in USB gadget mode

This approach minimizes changes to the Virtual FIDO codebase while allowing the Raspberry Pi to present itself as a USB FIDO2 authenticator device.

## Prerequisites

- Raspberry Pi Zero 2W
- MicroSD card (8GB+ recommended)
- Micro USB cable for the OTG port
- Internet connection for initial setup
- Basic familiarity with Linux and command line

## Setup Instructions

### Step 1: Install Raspberry Pi OS Lite

1. Download Raspberry Pi OS Lite (32-bit) from the [Raspberry Pi website](https://www.raspberrypi.org/software/operating-systems/)
2. Flash the OS to your microSD card using Raspberry Pi Imager or Balena Etcher
3. Enable SSH by creating an empty file named `ssh` in the boot partition
4. Configure Wi-Fi by creating a `wpa_supplicant.conf` file in the boot partition:

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

1. Edit `config.txt` in the boot partition and add:
```
# Enable USB OTG
dtoverlay=dwc2
```

2. Edit `cmdline.txt` and add after `rootwait`:
```
modules-load=dwc2,libcomposite
```

3. Insert the SD card and boot the Raspberry Pi

### Step 3: Configure USB Gadget Mode

1. SSH into your Raspberry Pi:
```bash
ssh pi@YOUR_PI_IP_ADDRESS
```

2. Create a script to configure the USB gadget:
```bash
sudo nano /usr/bin/fido_gadget_setup.sh
```

3. Add the following content:
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
echo -ne \\x06\\xd0\\xf1\\x09\\x01\\xa1\\x01\\x09\\x20\\x15\\x00\\x26\\xff\\x00\\x75\\x08\\x95\\x40\\x81\\x02\\x09\\x21\\x15\\x00\\x26\\xff\\x00\\x75\\x08\\x95\\x40\\x91\\x02\\xc0 > functions/hid.usb0/report_desc

# Link function to configuration
ln -s functions/hid.usb0 configs/c.1/

# Enable the gadget by binding to the UDC driver
ls /sys/class/udc > UDC

# Give proper permissions to HID device
sleep 1
chmod 666 /dev/hidg0
```

4. Make the script executable:
```bash
sudo chmod +x /usr/bin/fido_gadget_setup.sh
```

5. Create a systemd service:
```bash
sudo nano /etc/systemd/system/fido-gadget.service
```

6. Add the following content:
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

7. Enable and start the service:
```bash
sudo systemctl enable fido-gadget.service
sudo systemctl start fido-gadget.service
```

### Step 4: Install Virtual FIDO

1. Install required packages:
```bash
sudo apt update
sudo apt install -y git golang python3 python3-pip libusb-1.0-0-dev
```

2. Clone the Virtual FIDO repository:
```bash
git clone https://github.com/bulwarkid/virtual-fido.git
cd virtual-fido
```

3. Build the Virtual FIDO demo (which includes the USB/IP server):
```bash
cd cmd/demo
go build
```

### Step 5: Install the USB/IP to USB Gadget Shim

1. Copy the shim script to your Raspberry Pi:
```bash
# Copy usbip_to_gadget.py from wherever you downloaded it
chmod +x usbip_to_gadget.py
```

2. Test the shim:
```bash
sudo python3 usbip_to_gadget.py --test
```

3. Create a systemd service for the Virtual FIDO server:
```bash
sudo nano /etc/systemd/system/virtual-fido.service
```

4. Add the following content:
```
[Unit]
Description=Virtual FIDO Service
After=network.target
Before=usbip-shim.service

[Service]
ExecStart=/home/pi/virtual-fido/cmd/demo/demo start
User=root
WorkingDirectory=/home/pi/virtual-fido
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

5. Create a systemd service for the shim:
```bash
sudo nano /etc/systemd/system/usbip-shim.service
```

6. Add the following content:
```
[Unit]
Description=USB/IP to USB Gadget Shim
After=network.target virtual-fido.service
Wants=virtual-fido.service

[Service]
ExecStart=/usr/bin/python3 /home/pi/usbip_to_gadget.py
User=root
WorkingDirectory=/home/pi
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

7. Enable and start the services:
```bash
sudo systemctl enable virtual-fido.service
sudo systemctl enable usbip-shim.service
sudo systemctl start virtual-fido.service
sudo systemctl start usbip-shim.service
```

## Testing Your FIDO2 Authenticator

1. Connect your Raspberry Pi Zero 2W to your computer using the Micro USB OTG port
   * Note: You may need a separate power source when using the OTG port for data

2. The Pi should be detected as a USB FIDO device named "tk-x001" from "Google Inc."

3. Visit a WebAuthn test site like [webauthn.io](https://webauthn.io) or [demo.yubico.com/webauthn](https://demo.yubico.com/webauthn-technical/registration)

4. Register a new credential - if using the default Virtual FIDO demo, it will prompt for approval in the terminal.
   * To auto-approve all requests, modify the `ApproveClientAction` method in the demo client.

## Troubleshooting

### Check Services Status
```bash
sudo systemctl status fido-gadget.service
sudo systemctl status virtual-fido.service
sudo systemctl status usbip-shim.service
```

### View Logs
```bash
sudo journalctl -u fido-gadget.service
sudo journalctl -u virtual-fido.service -f
sudo journalctl -u usbip-shim.service -f
```

### Check USB Gadget Setup
```bash
ls -la /sys/kernel/config/usb_gadget/fido/
ls -la /dev/hidg0
```

### Check USB/IP Server
```bash
sudo netstat -tulpn | grep 3240
```

### Restart Everything
```bash
sudo systemctl restart fido-gadget.service
sudo systemctl restart virtual-fido.service
sudo systemctl restart usbip-shim.service
```

## How It Works

The implementation follows this data flow:

1. USB HID commands from the host computer arrive at the Raspberry Pi's OTG port
2. The USB gadget driver routes these to `/dev/hidg0`
3. The Python shim reads from `/dev/hidg0` and forwards to the Virtual FIDO USB/IP server on localhost:3240
4. The Virtual FIDO software processes the FIDO/CTAP protocol commands
5. Responses flow back through the same path in reverse

This approach minimizes code changes while leveraging the existing Virtual FIDO functionality.

## Security Considerations

- The Virtual FIDO software is still in beta - use caution for security-critical applications
- Consider implementing additional authentication or approval mechanisms for production use
- Be aware that the default demo implementation stores credentials in a file with a fixed passphrase

## References
- [Virtual FIDO Repository](https://github.com/bulwarkid/virtual-fido)
- [Linux USB Gadget API Documentation](https://www.kernel.org/doc/Documentation/usb/gadget_configfs.txt)
- [FIDO2 Specification](https://fidoalliance.org/specifications/)