#!/usr/bin/env python3
"""
OpenClaw Sync Manager for Hugging Face Spaces
==============================================

This script manages the complete lifecycle of OpenClaw in a Hugging Face Space:
1. Restores state on startup (load)
2. Runs periodic backups (save)
3. Ensures clean shutdown with final backup

This is the main entry point for running OpenClaw in Hugging Face Spaces.

Usage:
    python3 openclaw_sync.py

Environment Variables:
    HF_TOKEN - Hugging Face access token
    OPENCLAW_DATASET_REPO - Dataset for persistence (e.g., "username/openclaw")
    OPENCLAW_HOME - OpenClaw home directory (default: ~/.openclaw)
    SYNC_INTERVAL - Seconds between automatic backups (default: 300)
"""

import os
import sys
import time
import signal
import subprocess
import threading
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from openclaw_persist import OpenClawPersistence, Config, log


class SyncManager:
    """Manages sync and app lifecycle"""

    def __init__(self):
        # Configuration
        self.sync_interval = int(os.environ.get("SYNC_INTERVAL", "300"))  # 5 minutes default
        self.app_dir = Path(os.environ.get("OPENCLAW_APP_DIR", "/app/openclaw"))
        self.node_path = os.environ.get("NODE_PATH", f"{self.app_dir}/node_modules")

        # State
        self.running = False
        self.stop_event = threading.Event()
        self.app_process = None
        self.aux_processes = []

        # Persistence
        self.persist = None
        try:
            self.persist = OpenClawPersistence()
            log("INFO", "Persistence initialized",
                sync_interval=self.sync_interval)
        except Exception as e:
            log("WARNING", "Persistence not available, running without backup",
                error=str(e))

    # -----------------------------------------------------------------------
    # Lifecycle Management
    # -----------------------------------------------------------------------

    def start(self):
        """Main entry point - restore, run app, sync loop"""
        log("INFO", "Starting OpenClaw Sync Manager")

        # 1. Initial restore
        self.restore_state()

        # 2. Setup signal handlers
        self._setup_signals()

        # 3. Start aux services (if enabled)
        self.start_aux_services()

        # 4. Start application
        self.start_application()

        # 5. Start background sync
        self.start_background_sync()

        # 6. Wait for completion
        self.wait_for_exit()

    def restore_state(self):
        """Restore state from dataset on startup"""
        if not self.persist:
            log("INFO", "Skipping restore (persistence not configured)")
            # Still need to ensure config exists
            self._ensure_default_config()
            return

        log("INFO", "Restoring state from dataset...")

        result = self.persist.load(force=False)

        if result.get("success"):
            if result.get("restored"):
                log("INFO", "State restored successfully",
                    backup_file=result.get("backup_file"))
            else:
                log("INFO", "No previous state found, starting fresh")
                # Ensure default config for fresh start
                self._ensure_default_config()
        else:
            log("ERROR", "State restore failed", error=result.get("error"))

    def _ensure_default_config(self):
        """Ensure openclaw.json exists with valid config"""
        import json
        from openclaw_persist import Config

        config_path = Config.OPENCLAW_HOME / "openclaw.json"
        default_config_path = Path(__file__).parent / "openclaw.json.default"

        if config_path.exists():
            log("INFO", "Config file exists, skipping")
            return

        log("INFO", "No config found, creating default")

        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Try to load default config
        if default_config_path.exists():
            try:
                with open(default_config_path, 'r') as f:
                    config = json.load(f)
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                log("INFO", "Default config created from template")
                return
            except Exception as e:
                log("WARNING", "Could not load default config template", error=str(e))

        # Create minimal config
        minimal_config = {
            "gateway": {
                "mode": "local",
                "bind": "lan",
                "port": 7860,
                "auth": {"token": "openclaw-space-default"},
                "controlUi": {
                    "allowInsecureAuth": True,
                    "allowedOrigins": [
                        "https://huggingface.co"
                    ]
                }
            },
            "session": {"scope": "global"},
            "models": {
                "mode": "merge",
                "providers": {}
            },
            "agents": {
                "defaults": {
                    "workspace": "~/.openclaw/workspace"
                }
            }
        }

        with open(config_path, 'w') as f:
            json.dump(minimal_config, f, indent=2)
        log("INFO", "Minimal config created")

    def start_application(self):
        """Start the main OpenClaw application"""
        log("INFO", "Starting OpenClaw application")

        # Prepare environment
        env = os.environ.copy()
        env["NODE_PATH"] = self.node_path
        env["NODE_ENV"] = "production"

        # Prepare command - use shell with tee for log capture
        cmd_str = "node dist/entry.js gateway"

        log("INFO", "Executing command",
            cmd=cmd_str,
            cwd=str(self.app_dir))

        # Start process with shell=True for proper output handling
        self.app_process = subprocess.Popen(
            cmd_str,
            shell=True,
            cwd=str(self.app_dir),
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        log("INFO", "Application started", pid=self.app_process.pid)

    def start_aux_services(self):
        """Start auxiliary services like WA guardian and QR manager"""
        env = os.environ.copy()
        env["NODE_PATH"] = self.node_path

        # Only start if explicitly enabled
        if os.environ.get("ENABLE_AUX_SERVICES", "false").lower() == "true":
            # WA Login Guardian
            wa_guardian = Path(__file__).parent / "wa-login-guardian.cjs"
            if wa_guardian.exists():
                try:
                    p = subprocess.Popen(
                        ["node", str(wa_guardian)],
                        env=env,
                        stdout=sys.stdout,
                        stderr=sys.stderr
                    )
                    self.aux_processes.append(p)
                    log("INFO", "WA Guardian started", pid=p.pid)
                except Exception as e:
                    log("WARNING", "Could not start WA Guardian", error=str(e))

            # QR Detection Manager
            qr_manager = Path(__file__).parent / "qr-detection-manager.cjs"
            space_host = os.environ.get("SPACE_HOST", "")
            if qr_manager.exists():
                try:
                    p = subprocess.Popen(
                        ["node", str(qr_manager), space_host],
                        env=env,
                        stdout=sys.stdout,
                        stderr=sys.stderr
                    )
                    self.aux_processes.append(p)
                    log("INFO", "QR Manager started", pid=p.pid)
                except Exception as e:
                    log("WARNING", "Could not start QR Manager", error=str(e))
        else:
            log("INFO", "Aux services disabled")

    def start_background_sync(self):
        """Start periodic backup in background"""
        if not self.persist:
            log("INFO", "Skipping background sync (persistence not configured)")
            return

        self.running = True

        def sync_loop():
            while not self.stop_event.is_set():
                # Wait for interval or stop
                if self.stop_event.wait(timeout=self.sync_interval):
                    break

                # Perform backup
                log("INFO", "Periodic backup triggered")
                self.do_backup()

        thread = threading.Thread(target=sync_loop, daemon=True)
        thread.start()
        log("INFO", "Background sync started",
            interval_seconds=self.sync_interval)

    def do_backup(self):
        """Perform a backup operation"""
        if not self.persist:
            return

        try:
            result = self.persist.save()
            if result.get("success"):
                log("INFO", "Backup completed successfully",
                    operation_id=result.get("operation_id"),
                    remote_path=result.get("remote_path"))
            else:
                log("ERROR", "Backup failed", error=result.get("error"))
        except Exception as e:
            log("ERROR", "Backup exception", error=str(e), exc_info=True)

    def wait_for_exit(self):
        """Wait for app process to exit"""
        if not self.app_process:
            log("ERROR", "No app process to wait for")
            return

        log("INFO", "Waiting for application to exit...")

        exit_code = self.app_process.wait()
        log("INFO", f"Application exited with code {exit_code}")

        # Stop sync
        self.stop_event.set()

        # Terminate aux processes
        for p in self.aux_processes:
            try:
                p.terminate()
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
            except Exception:
                pass

        # Final backup
        log("INFO", "Performing final backup...")
        self.do_backup()

        sys.exit(exit_code)

    def _setup_signals(self):
        """Setup signal handlers for graceful shutdown"""
        def handle_signal(signum, frame):
            log("INFO", f"Received signal {signum}, initiating shutdown...")

            # Stop sync
            self.stop_event.set()

            # Terminate app
            if self.app_process:
                log("INFO", "Terminating application...")
                self.app_process.terminate()
                try:
                    self.app_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.app_process.kill()

            # Terminate aux
            for p in self.aux_processes:
                try:
                    p.terminate()
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                except Exception:
                    pass

            # Final backup
            if self.persist:
                log("INFO", "Performing final backup on shutdown...")
                self.do_backup()

            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    log("INFO", "OpenClaw Sync Manager starting...")
    log("INFO", "Configuration",
        home_dir=str(Config.OPENCLAW_HOME),
        repo_id=os.environ.get("OPENCLAW_DATASET_REPO", "not set"),
        sync_interval=os.environ.get("SYNC_INTERVAL", "300"))

    manager = SyncManager()
    manager.start()


if __name__ == "__main__":
    main()
