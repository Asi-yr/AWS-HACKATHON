#!/bin/bash
# Run this ONCE on your Mac to allow phones on Wi-Fi to reach Flask.
# Double-click it or run: bash allow_flask.sh

echo "Unblocking Flask on port 5000..."

# Allow python3 through the app firewall
PYTHON=$(which python3)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$PYTHON"
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$PYTHON"

# Also punch a hole at the packet filter level for port 5000
echo "pass in proto tcp from any to any port 5000" | sudo pfctl -f - 2>/dev/null || true
sudo pfctl -e 2>/dev/null || true

echo ""
echo "Done. Now start Flask: python main.py"
echo "Your phone should connect automatically."
