/**
 * a2a-proxy.cjs — Reverse proxy on port 7860
 *
 * Routes:
 *   /.well-known/*  → A2A gateway (port 18800)
 *   /a2a/*          → A2A gateway (port 18800)
 *   /api/state      → local state JSON (for Office frontend polling)
 *   everything else → OpenClaw (port 7861)
 */
'use strict';

const http = require('http');
const url = require('url');

const LISTEN_PORT = 7860;
const OPENCLAW_PORT = 7861;
const A2A_PORT = 18800;
const AGENT_NAME = process.env.AGENT_NAME || 'Agent';

let currentState = {
  state: 'syncing',
  detail: `${AGENT_NAME} is starting...`,
  progress: 0,
  updated_at: new Date().toISOString()
};

// Poll OpenClaw health to track state
async function pollOpenClawHealth() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const resp = await fetch(`http://127.0.0.1:${OPENCLAW_PORT}/`, {
      signal: controller.signal
    });
    clearTimeout(timeout);
    currentState = {
      state: resp.ok ? 'idle' : 'error',
      detail: resp.ok ? `${AGENT_NAME} is running` : `HTTP ${resp.status}`,
      progress: resp.ok ? 100 : 0,
      updated_at: new Date().toISOString()
    };
  } catch (_) {
    currentState = {
      state: 'syncing',
      detail: `${AGENT_NAME} is starting...`,
      progress: 0,
      updated_at: new Date().toISOString()
    };
  }
}

setInterval(pollOpenClawHealth, 5000);
pollOpenClawHealth();

function proxyRequest(req, res, targetPort) {
  const options = {
    hostname: '127.0.0.1',
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${targetPort}` }
  };

  const proxy = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxy.on('error', (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Backend unavailable', target: targetPort }));
    }
  });

  req.pipe(proxy, { end: true });
}

const server = http.createServer((req, res) => {
  const pathname = url.parse(req.url).pathname;

  // A2A routes → A2A gateway
  if (pathname.startsWith('/.well-known/') || pathname.startsWith('/a2a/')) {
    return proxyRequest(req, res, A2A_PORT);
  }

  // State endpoint for Office frontend polling
  if (pathname === '/api/state' || pathname === '/status') {
    res.writeHead(200, {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*'
    });
    return res.end(JSON.stringify(currentState));
  }

  // Everything else → OpenClaw
  proxyRequest(req, res, OPENCLAW_PORT);
});

// Handle WebSocket upgrades
server.on('upgrade', (req, socket, head) => {
  const pathname = url.parse(req.url).pathname;
  const targetPort = (pathname.startsWith('/.well-known/') || pathname.startsWith('/a2a/'))
    ? A2A_PORT
    : OPENCLAW_PORT;

  const options = {
    hostname: '127.0.0.1',
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${targetPort}` }
  };

  const proxy = http.request(options);
  proxy.on('upgrade', (proxyRes, proxySocket, proxyHead) => {
    socket.write(
      `HTTP/1.1 101 Switching Protocols\r\n` +
      Object.entries(proxyRes.headers).map(([k, v]) => `${k}: ${v}`).join('\r\n') +
      '\r\n\r\n'
    );
    proxySocket.write(head);
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
  });
  proxy.on('error', () => socket.end());
  proxy.end();
});

server.listen(LISTEN_PORT, '0.0.0.0', () => {
  console.log(`[a2a-proxy] Listening on port ${LISTEN_PORT}`);
  console.log(`[a2a-proxy] OpenClaw → :${OPENCLAW_PORT}, A2A → :${A2A_PORT}`);
  console.log(`[a2a-proxy] Agent: ${AGENT_NAME}`);
});
