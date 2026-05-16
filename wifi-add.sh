#!/usr/bin/env bash
# Add a WiFi network to known connections (auto-connect when in range).
# Usage: bash wifi-add.sh "SSID" "PASSWORD"

set -euo pipefail

SSID="${1:-}"
PASS="${2:-}"

[[ -z "$SSID" ]] && { echo "Usage: $0 \"SSID\" \"PASSWORD\""; exit 1; }

# Remove existing connection with same name to avoid duplicates
nmcli con delete "$SSID" 2>/dev/null || true

if [[ -z "$PASS" ]]; then
    # Open network
    nmcli con add type wifi con-name "$SSID" ssid "$SSID" \
        connection.autoconnect yes
else
    nmcli con add type wifi con-name "$SSID" ssid "$SSID" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$PASS" \
        connection.autoconnect yes
fi

echo "✓ Réseau \"$SSID\" ajouté — connexion automatique activée"
echo ""
nmcli con show "$SSID" | grep -E "connection\.(id|autoconnect)|802-11|ipv4.method"
