/**
 * token-redirect.cjs — Node.js preload script
 *
 * Intercepts HTTP requests to the root URL "/" and redirects to
 * "/?token=GATEWAY_TOKEN" so the Control UI auto-fills the gateway token.
 *
 * Loaded via NODE_OPTIONS --require before OpenClaw starts.
 */
'use strict';

const http = require('http');

const GATEWAY_TOKEN = process.env.GATEWAY_TOKEN || 'huggingclaw';
const origEmit = http.Server.prototype.emit;

http.Server.prototype.emit = function (event, ...args) {
  if (event === 'request') {
    const [req, res] = args;
    // Only redirect normal GET to "/" without token — skip WebSocket upgrades
    if (req.method === 'GET' && !req.headers.upgrade) {
      try {
        const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
        if (url.pathname === '/' && !url.searchParams.has('token')) {
          url.searchParams.set('token', GATEWAY_TOKEN);
          res.writeHead(302, { Location: url.pathname + url.search });
          res.end();
          return true;
        }
      } catch (_) {
        // URL parse error — pass through
      }
    }
  }
  return origEmit.apply(this, [event, ...args]);
};

console.log('[token-redirect] Gateway token redirect active');
