#!/usr/bin/env node

/**
 * QR Detection Manager for OpenClaw AI
 * MANDATORY QR Wait/Notify Implementation
 * 
 * When WhatsApp login requires QR code scan:
 * - STOP all debug operations
 * - Wait for QR code scan
 * - Clear user prompts
 * - Only continue after successful scan
 */

const fs = require('fs');
const path = require('path');
const { WebSocket } = require('ws');
const readline = require('readline');

class QRDetectionManager {
    constructor() {
        this.ws = null;
        this.isPaused = false;
        this.qrDetected = false;
        this.qrSourcePath = null;
        this.scanCompleted = false;
        this.timeout = null;
        this.qrTimeout = 300000; // 5 minutes timeout
        
        // Setup structured logging
        this.log = (level, message, data = {}) => {
            const logEntry = {
                timestamp: new Date().toISOString(),
                level,
                module: 'qr-detection-manager',
                message,
                ...data
            };
            console.log(JSON.stringify(logEntry));
        };
        
        this.log('info', 'QR Detection Manager initialized');
    }
    
    async connectWebSocket(spaceUrl) {
        try {
            // Handle spaceUrl being just a hostname or full URL
            let host = spaceUrl.replace(/^https?:\/\//, '').replace(/\/$/, '');
            const wsUrl = `wss://${host}`;
            const fullWsUrl = `${wsUrl}/queue/join`;
            
            this.log('info', 'Connecting to WebSocket', { url: fullWsUrl });
            
            this.ws = new WebSocket(fullWsUrl);
            
            this.ws.on('open', () => {
                this.log('info', 'WebSocket connection established');
                this.startMonitoring();
            });
            
            this.ws.on('message', (data) => {
                this.handleWebSocketMessage(data);
            });
            
            this.ws.on('error', (error) => {
                this.log('error', 'WebSocket error', { error: error.message });
            });
            
            this.ws.on('close', () => {
                this.log('info', 'WebSocket connection closed');
            });
            
        } catch (error) {
            this.log('error', 'Failed to connect to WebSocket', { error: error.message });
        }
    }

    handleWebSocketMessage(data) {
        // Placeholder for future WS message handling if needed
        // Currently we rely mostly on log/file monitoring
    }

    startMonitoring() {
        this.log('info', 'Starting QR code monitoring');
        
        // Send initial ping to keep connection alive
        const pingInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.ping();
            } else {
                clearInterval(pingInterval);
            }
        }, 30000);
        
        // Watch for QR code detection
        this.setupQRDetection();
    }
    
    setupQRDetection() {
        this.log('info', 'Setting up QR code detection');
        
        // Start timeout for QR scan
        this.timeout = setTimeout(() => {
            if (!this.scanCompleted) {
                this.log('warning', 'QR scan timeout reached');
                this.outputQRPrompt('❌ QR scan timeout. Please restart the process.', 'timeout');
                process.exit(1);
            }
        }, this.qrTimeout);
        
        // Monitor for QR code in logs or filesystem
        this.monitorForQR();
    }
    
    monitorForQR() {
        const homeDir = process.env.HOME || '/home/node';
        // Check for QR code file in actual HF Spaces paths
        const qrCheckInterval = setInterval(() => {
            if (this.scanCompleted) {
                clearInterval(qrCheckInterval);
                return;
            }

            // Check actual QR code file locations for HF Spaces OpenClaw
            const qrPaths = [
                path.join(homeDir, '.openclaw/credentials/whatsapp/qr.png'),
                path.join(homeDir, '.openclaw/workspace/qr.png'),
                path.join(homeDir, 'logs/qr.png'),
            ];

            for (const qrPath of qrPaths) {
                if (fs.existsSync(qrPath)) {
                    this.qrSourcePath = qrPath;
                    this.handleQRDetected(qrPath);
                    break;
                }
            }

            // Also check for QR code in recent logs
            this.checkLogsForQR();
        }, 2000); // Check every 2 seconds
    }
    
    checkLogsForQR() {
        try {
            const homeDir = process.env.HOME || '/home/node';
            const logPaths = [
                path.join(homeDir, 'logs/app.log'),
                path.join(homeDir, '.openclaw/workspace/startup.log'),
                path.join(homeDir, '.openclaw/workspace/sync.log'),
            ];
            
            for (const logPath of logPaths) {
                if (fs.existsSync(logPath)) {
                    const logContent = fs.readFileSync(logPath, 'utf8');
                    if (this.isQRInLogContent(logContent)) {
                        this.handleQRDetected('log');
                        break;
                    }
                }
            }
        } catch (error) {
            // Ignore log reading errors
        }
    }
    
    isQRInLogContent(content) {
        // Look for QR-related log entries
        const qrPatterns = [
            /qr code/i,
            /scan.*qr/i,
            /please scan/i,
            /waiting.*qr/i,
            /login.*qr/i,
            /whatsapp.*qr/i,
            /authentication.*qr/i
        ];
        
        return qrPatterns.some(pattern => pattern.test(content));
    }
    
    handleQRDetected(source) {
        if (this.qrDetected) {
            return; // Already detected
        }
        
        this.qrDetected = true;
        this.log('info', 'QR code detected', { source });
        
        // MANDATORY: Stop all debug operations
        this.isPaused = true;
        
        // MANDATORY: Clear user prompts
        this.outputQRPrompt('⏳ Waiting for WhatsApp QR code scan...', 'waiting');
        this.outputQRPrompt('📱 Please scan the QR code with your phone to continue.', 'qr');
        
        // Start monitoring for scan completion
        this.monitorScanCompletion();
    }
    
    outputQRPrompt(message, type) {
        // Clear console for better visibility
        process.stdout.write('\x1b[2J\x1b[0f');
        
        // Output formatted QR prompt
        const separator = '='.repeat(60);
        console.log(`\n${separator}`);
        console.log(`🔐 WHATSAPP LOGIN REQUIRED`);
        console.log(`${separator}\n`);
        console.log(message);
        console.log(`\n${separator}`);
        
        // Add visual indicators based on type
        if (type === 'waiting') {
            console.log('⏳ Operation paused - waiting for QR scan...');
        } else if (type === 'qr') {
            console.log('📱 Use your WhatsApp app to scan the QR code');
        } else if (type === 'success') {
            console.log('✅ QR scan completed successfully!');
        } else if (type === 'timeout') {
            console.log('❌ QR scan timeout - please try again');
        }
        
        console.log(`${separator}\n`);
        
        // Also log as JSON for structured processing
        this.log(type === 'success' ? 'info' : 'warning', 'QR prompt output', { 
            message, 
            type,
            isPaused: this.isPaused 
        });
    }
    
    monitorScanCompletion() {
        this.log('info', 'Monitoring for QR scan completion');
        
        // Monitor for scan completion signals
        const completionCheck = setInterval(() => {
            if (this.checkScanCompletion()) {
                clearInterval(completionCheck);
                this.handleScanCompleted();
            }
        }, 1000);
    }
    
    checkScanCompletion() {
        const homeDir = process.env.HOME || '/home/node';

        // 1. Check if QR file was removed (only if we know which file was detected)
        if (this.qrSourcePath && !fs.existsSync(this.qrSourcePath)) {
            return true;
        }

        // 2. Check for successful login in logs
        try {
            const logPaths = [
                path.join(homeDir, 'logs/app.log'),
                path.join(homeDir, '.openclaw/workspace/startup.log'),
                path.join(homeDir, '.openclaw/workspace/sync.log'),
            ];

            for (const logPath of logPaths) {
                if (fs.existsSync(logPath)) {
                    const logContent = fs.readFileSync(logPath, 'utf8');
                    if (this.isLoginInLogContent(logContent)) {
                        return true;
                    }
                }
            }
        } catch (error) {
            // Ignore log reading errors
        }

        // 3. Check for WhatsApp session/creds files in actual HF Spaces paths
        const sessionPaths = [
            path.join(homeDir, '.openclaw/credentials/whatsapp/creds.json'),
            path.join(homeDir, '.openclaw/credentials/whatsapp/session.json'),
        ];

        for (const sessionPath of sessionPaths) {
            if (fs.existsSync(sessionPath)) {
                return true;
            }
        }

        return false;
    }
    
    isLoginInLogContent(content) {
        // Look for successful login patterns
        const loginPatterns = [
            /login.*successful/i,
            /authentication.*success/i,
            /session.*established/i,
            /connected.*whatsapp/i,
            /qr.*scanned/i,
            /scan.*completed/i,
            /user.*authenticated/i
        ];
        
        return loginPatterns.some(pattern => pattern.test(content));
    }
    
    handleScanCompleted() {
        this.scanCompleted = true;
        this.isPaused = false;
        
        // Clear timeout
        if (this.timeout) {
            clearTimeout(this.timeout);
        }
        
        // MANDATORY: Clear success notification
        this.outputQRPrompt('✅ QR code scanned successfully. Login completed.', 'success');
        
        this.log('info', 'QR scan completed, resuming operations');
        
        // Wait a moment for user to see the success message
        setTimeout(() => {
            // Exit the process to allow main application to continue
            process.exit(0);
        }, 3000);
    }
    
    async waitForQRScan() {
        return new Promise((resolve, reject) => {
            const checkInterval = setInterval(() => {
                if (this.scanCompleted) {
                    clearInterval(checkInterval);
                    resolve();
                }
            }, 1000);
            
            // Timeout after 5 minutes
            setTimeout(() => {
                clearInterval(checkInterval);
                reject(new Error('QR scan timeout'));
            }, this.qrTimeout);
        });
    }
    
    close() {
        if (this.ws) {
            this.ws.close();
        }
        if (this.timeout) {
            clearTimeout(this.timeout);
        }
        this.log('info', 'QR Detection Manager closed');
    }
}

// Command line interface
async function main() {
    const args = process.argv.slice(2);
    const spaceUrl = args[0] || process.env.SPACE_HOST || '';
    
    const manager = new QRDetectionManager();
    
    try {
        await manager.connectWebSocket(spaceUrl);
        
        // Keep the process running
        process.on('SIGINT', () => {
            manager.log('info', 'Received SIGINT, shutting down gracefully');
            manager.close();
            process.exit(0);
        });
        
        process.on('SIGTERM', () => {
            manager.log('info', 'Received SIGTERM, shutting down gracefully');
            manager.close();
            process.exit(0);
        });
        
    } catch (error) {
        manager.log('error', 'QR Detection Manager failed', { error: error.message });
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}

module.exports = QRDetectionManager;