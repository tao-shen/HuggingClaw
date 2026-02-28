/**
 * Structured Logger for OpenClaw
 * Provides consistent JSON logging for HF Spaces
 */

const fs = require('fs');
const path = require('path');

// Ensure logs directory exists
const LOG_DIR = path.join(process.env.HOME || '/home/node', 'logs');
if (!fs.existsSync(LOG_DIR)) {
    try {
        fs.mkdirSync(LOG_DIR, { recursive: true });
    } catch (e) {
        // Ignore if we can't create it (might be read-only or race condition)
    }
}

const LOG_FILE = path.join(LOG_DIR, 'app.json.log');

class Logger {
    constructor(moduleName) {
        this.module = moduleName;
    }

    _log(level, message, data = {}) {
        const entry = {
            timestamp: new Date().toISOString(),
            level: level.toUpperCase(),
            module: this.module,
            message,
            ...data
        };

        const jsonLine = JSON.stringify(entry);
        
        // Write to stdout for HF Logs visibility
        console.log(jsonLine);

        // Also append to local file for persistence within container life
        try {
            fs.appendFileSync(LOG_FILE, jsonLine + '\n');
        } catch (e) {
            // Fallback if file write fails
            console.error(`[LOGGER_FAIL] Could not write to log file: ${e.message}`);
        }
    }

    info(message, data) { this._log('INFO', message, data); }
    warn(message, data) { this._log('WARN', message, data); }
    error(message, data) { this._log('ERROR', message, data); }
    debug(message, data) { this._log('DEBUG', message, data); }
    
    // Special method for critical state changes
    state(stateName, previousState, newState, data) {
        this._log('STATE_CHANGE', `State changed: ${stateName}`, {
            previousState,
            newState,
            ...data
        });
    }
}

module.exports = (moduleName) => new Logger(moduleName);
