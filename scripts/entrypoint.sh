#!/bin/sh
set -e

echo "[entrypoint] OpenClaw HuggingFace Spaces Entrypoint"
echo "[entrypoint] ======================================="

# DNS pre-resolution for WhatsApp
echo "[entrypoint] Resolving WhatsApp domains via DNS-over-HTTPS..."
python3 /home/node/scripts/dns-resolve.py /tmp/dns-resolved.json || echo "[entrypoint] DNS pre-resolve had issues (non-fatal)"

# Enable Node.js DNS fix
export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--require /home/node/scripts/dns-fix.cjs"

# Ensure extensions symlink exists
if [ ! -L /home/node/.openclaw/extensions ]; then
  rm -rf /home/node/.openclaw/extensions 2>/dev/null || true
  ln -s /app/openclaw/extensions /home/node/.openclaw/extensions
  echo "[entrypoint] Created extensions symlink -> /app/openclaw/extensions"
fi

# Check for WhatsApp credentials
if [ -d /home/node/.openclaw/credentials/whatsapp ]; then
  echo "[entrypoint] Found existing WhatsApp credentials - will use for auto-connect"
fi

# Build artifacts check
cd /app/openclaw
echo "[entrypoint] Build artifacts check:"
test -f dist/entry.js && echo "  OK dist/entry.js" || echo "  WARNING: dist/entry.js missing!"
test -f dist/plugin-sdk/index.js && echo "  OK dist/plugin-sdk/index.js" || echo "  WARNING: dist/plugin-sdk/index.js missing!"
echo "  Extensions: $(ls extensions/ 2>/dev/null | wc -l | tr -d ' ') found"
echo "  Global extensions link: $(readlink /home/node/.openclaw/extensions 2>/dev/null || echo 'NOT SET')"
echo "  DNS resolved: $(cat /tmp/dns-resolved.json 2>/dev/null || echo 'file missing')"

# Create logs directory
mkdir -p /home/node/logs
touch /home/node/logs/app.log

# Start OpenClaw via sync_hf.py
echo "[entrypoint] Starting OpenClaw via sync_hf.py..."
exec python3 -u /home/node/scripts/sync_hf.py
