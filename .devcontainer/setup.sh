#!/bin/bash
set -e

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Connect to Tailscale (use secret from environment)
tailscale up --auth-key="$TAILSCALE_AUTH_KEY"

# Get IP and print
IP=$(tailscale ip -4)
echo "✅ Tailscale IP: $IP"

# Set password for RDP (if using xrdp later, but for Linux we'll use SSH)
# For Windows RDP, we'd need Windows runner — but Codespaces are Linux.
# We'll set up xrdp for remote desktop (optional)
