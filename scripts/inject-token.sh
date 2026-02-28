#!/bin/sh
# Inject auto-token config into Control UI so the browser auto-connects
TOKEN_SCRIPT='<script>!function(){var K="openclaw.control.settings.v1";try{var s=JSON.parse(localStorage.getItem(K)||"{}")||{};if(!s.token){s.token="openclaw-space-default";localStorage.setItem(K,JSON.stringify(s))}}catch(e){}}()</script>'

OPENCLAW_APP_DIR="${OPENCLAW_APP_DIR:-/usr/local/lib/node_modules/openclaw}"

for f in "$OPENCLAW_APP_DIR/dist/control-ui/index.html" "$OPENCLAW_APP_DIR/control-ui/index.html" /app/openclaw/dist/control-ui/index.html; do
  if [ -f "$f" ]; then
    sed -i "s|</head>|${TOKEN_SCRIPT}</head>|" "$f"
    echo "[build] Token auto-config injected into $f"
    exit 0
  fi
done

echo "[build] WARNING: control-ui/index.html not found, skipping token injection"
