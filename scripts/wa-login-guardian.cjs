/**
 * WhatsApp Login Guardian — background helper for HF Spaces.
 *
 * Problem: After QR scan, WhatsApp sends 515 (restart required). The
 * web.login.wait RPC handles this restart, but HF Spaces' proxy drops
 * WebSocket connections, so the UI's web.login.wait may not be active.
 *
 * Solution: This script connects to the local gateway and keeps calling
 * web.login.wait with long timeouts, ensuring the 515 restart is handled.
 *
 * Usage: Run as background process from entrypoint.sh
 */
"use strict";

const { WebSocket } = require("ws");
const { randomUUID } = require("node:crypto");
const { exec } = require('child_process');

const GATEWAY_URL = "ws://127.0.0.1:7860";
const TOKEN = "openclaw-space-default";
const CHECK_INTERVAL = 5000; // Check every 5s so we catch QR scan quickly
const WAIT_TIMEOUT = 120000; // 2 minute wait timeout
const POST_515_NO_LOGOUT_MS = 90000; // After 515, don't clear "401" for 90s (avoid wiping just-saved creds)

let isWaiting = false;
let last515At = 0;
let hasShownWaitMessage = false;

function createConnection() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(GATEWAY_URL);
    let resolved = false;

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());

      if (msg.type === "event" && msg.event === "connect.challenge") {
        ws.send(
          JSON.stringify({
            type: "req",
            id: randomUUID(),
            method: "connect",
            params: {
              minProtocol: 3,
              maxProtocol: 3,
              client: {
                id: "gateway-client",
                version: "1.0.0",
                platform: "linux",
                mode: "backend",
              },
              caps: [],
              auth: { token: TOKEN },
              role: "operator",
              scopes: ["operator.admin"],
            },
          })
        );
        return;
      }

      if (!resolved && msg.type === "res" && msg.ok) {
        resolved = true;
        resolve(ws);
      }
    });

    ws.on("error", (e) => {
      if (!resolved) reject(e);
    });

    setTimeout(() => {
      if (!resolved) {
        ws.close();
        reject(new Error("Connection timeout"));
      }
    }, 10000);
  });
}

async function callRpc(ws, method, params) {
  return new Promise((resolve, reject) => {
    const id = randomUUID();
    const handler = (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.id === id) {
        ws.removeListener("message", handler);
        resolve(msg);
      }
    };
    ws.on("message", handler);
    ws.send(JSON.stringify({ type: "req", id, method, params }));

    // Long timeout for web.login.wait
    setTimeout(() => {
      ws.removeListener("message", handler);
      reject(new Error("RPC timeout"));
    }, WAIT_TIMEOUT + 5000);
  });
}

async function checkAndWait() {
  if (isWaiting) return;

  let ws;
  try {
    ws = await createConnection();
  } catch {
    return; // Gateway not ready yet
  }

  try {
    // Check channel status to see if WhatsApp needs attention
    const statusRes = await callRpc(ws, "channels.status", {});
    const channels = (statusRes.payload || statusRes.result)?.channels || {};
    const wa = channels.whatsapp;

    if (!wa) {
      ws.close();
      return;
    }

    // If linked but got 401/logged out OR 440/conflict, clear invalid credentials so user can get a fresh QR —
    // but NOT within POST_515_NO_LOGOUT_MS of a 515 (channel may still report 401 and we'd wipe just-saved creds).
    const err = (wa.lastError || "").toLowerCase();
    const recently515 = Date.now() - last515At < POST_515_NO_LOGOUT_MS;
    const needsLogout = wa.linked && !wa.connected && !recently515 &&
      (err.includes("401") || err.includes("unauthorized") || err.includes("logged out") || err.includes("440") || err.includes("conflict"));

    if (needsLogout) {
      console.log("[wa-guardian] Clearing invalid session (401/440/conflict) so a fresh QR can be used...");
      try {
        await callRpc(ws, "channels.logout", { channel: "whatsapp" });
        console.log("[wa-guardian] Logged out; user can click Login again for a new QR.");
        
        // Signal sync_hf.py to delete remote credentials
        const fs = require('fs');
        const path = require('path');
        // Workspace is usually /home/node/.openclaw/workspace
        const markerPath = path.join(process.env.HOME || '/home/node', '.openclaw/workspace/.reset_credentials');
        fs.writeFileSync(markerPath, 'reset');
        console.log("[wa-guardian] Created .reset_credentials marker for sync script.");
        
      } catch (e) {
        console.log("[wa-guardian] channels.logout failed:", e.message);
      }
      ws.close();
      return;
    }

    // If WhatsApp is already connected, nothing to do
    if (wa.connected) {
      ws.close();
      return;
    }

    // Try web.login.wait — this will handle 515 restart if QR was scanned
    isWaiting = true;
    if (!hasShownWaitMessage) {
      console.log("⏳ Waiting for WhatsApp QR code scan...");
      console.log("📱 Please scan the QR code with your phone to continue.");
      hasShownWaitMessage = true;
    }
    console.log("[wa-guardian] Calling web.login.wait...");
    const waitRes = await callRpc(ws, "web.login.wait", {
      timeoutMs: WAIT_TIMEOUT,
    });
    const result = waitRes.payload || waitRes.result;
    const msg = result?.message || "";
    const linkedAfter515 = !result?.connected && msg.includes("515");
    if (linkedAfter515) last515At = Date.now();
    if (result?.connected || linkedAfter515) {
      hasShownWaitMessage = false; // Reset for next time
      if (linkedAfter515) {
        console.log("[wa-guardian] 515 after scan — credentials saved; triggering config reload to start channel...");
      } else {
        console.log("[wa-guardian] WhatsApp connected successfully! Triggering config reload to start channel...");
      }
      console.log("✅ QR code scanned successfully. Login completed.");

      // Persistence handled by sync_hf.py background loop
      try {
        const getRes = await callRpc(ws, "config.get", {});
        const raw = getRes.payload?.raw;
        const hash = getRes.payload?.hash;
        if (raw && hash) {
          await callRpc(ws, "config.apply", { raw, baseHash: hash });
          console.log("[wa-guardian] Config applied; gateway will restart with WhatsApp channel.");
        }
      } catch (e) {
        console.log("[wa-guardian] Config apply failed:", e.message);
      }
    } else {
      if (!msg.includes("No active") && !msg.includes("Still waiting")) {
        console.log("[wa-guardian] Wait result:", msg);
      }
    }
  } catch (e) {
    // Timeout or error — normal, just retry
  } finally {
    isWaiting = false;
    try {
      ws.close();
    } catch {}
  }
}

// Start checking periodically
console.log("[wa-guardian] WhatsApp login guardian started");
setInterval(checkAndWait, CHECK_INTERVAL);
// Initial check after 15s (give gateway time to start)
setTimeout(checkAndWait, 15000);
