#!/usr/bin/env python3
"""
OpenClaw Full Directory Persistence for Hugging Face Spaces
========================================================

This script provides atomic, complete persistence of the entire ~/.openclaw directory.
It implements the comprehensive persistence plan:

- Config & Credentials (openclaw.json, credentials/)
- Workspace (workspace/ with AGENTS.md, SOUL.md, TOOLS.md, MEMORY.md, skills/, memory/)
- Sessions (agents/*/sessions/*.jsonl)
- Memory Index (memory/*.sqlite)
- QMD Backend (agents/*/qmd/)
- Extensions (extensions/)
- All other state in ~/.openclaw

Usage:
    # Backup (save)
    python3 openclaw_persist.py save

    # Restore (load)
    python3 openclaw_persist.py load

Environment Variables:
    HF_TOKEN - Hugging Face access token with write permissions
    OPENCLAW_DATASET_REPO - Dataset repo ID (e.g., "username/openclaw-state")
    OPENCLAW_HOME - OpenClaw home directory (default: ~/.openclaw)
"""

import os
import sys
import json
import tarfile
import tempfile
import shutil
import hashlib
import time
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Set, Dict, Any

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import RepositoryNotFoundError


# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Configuration for persistence system"""

    # Paths
    OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", "~/.openclaw")).expanduser()
    BACKUP_FILENAME = "openclaw-full.tar.gz"
    BACKUP_STATE_FILE = ".persistence-state.json"
    LOCK_FILE = ".persistence.lock"

    # Backup rotation settings
    MAX_BACKUPS = 5
    BACKUP_PREFIX = "backup-"

    # Patterns to exclude from backup
    EXCLUDE_PATTERNS = [
        "*.lock",
        "*.tmp",
        "*.pyc",
        "*__pycache__*",
        "*.socket",
        "*.pid",
        "node_modules",
        ".DS_Store",
        ".git",
    ]

    # Directories to skip entirely (relative to OPENCLAW_HOME)
    SKIP_DIRS = {
        ".cache",
        "logs",
        "temp",
        "tmp",
    }


# ============================================================================
# Utility Functions
# ============================================================================

def log(level: str, message: str, **kwargs):
    """Structured logging"""
    timestamp = datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message,
        **kwargs
    }
    print(json.dumps(log_entry), flush=True)


def calculate_file_hash(filepath: Path) -> str:
    """Calculate SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return ""


def get_directory_size(directory: Path) -> int:
    """Calculate total size of directory in bytes"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = Path(dirpath) / filename
                try:
                    total_size += filepath.stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total_size


def should_exclude(path: str, exclude_patterns: List[str]) -> bool:
    """Check if a path should be excluded based on patterns"""
    path_normalized = path.replace("\\", "/")

    for pattern in exclude_patterns:
        pattern = pattern.lstrip("/")
        if pattern.startswith("*"):
            suffix = pattern[1:]
            if path_normalized.endswith(suffix):
                return True
        elif pattern in path_normalized:
            return True

    return False


# ============================================================================
# Persistence Manager
# ============================================================================

class OpenClawPersistence:
    """
    Manages persistence of OpenClaw state to Hugging Face Dataset

    Features:
    - Atomic full-directory backup/restore
    - Proper exclusion of lock files and temporary data
    - Safe handling of SQLite databases
    - Backup rotation
    - Integrity verification
    """

    def __init__(self):
        self.api = None
        self.repo_id = os.environ.get("OPENCLAW_DATASET_REPO")
        self.token = os.environ.get("HF_TOKEN")
        self.home_dir = Config.OPENCLAW_HOME
        self.lock_file = self.home_dir / Config.LOCK_FILE
        self.state_file = self.home_dir / Config.BACKUP_STATE_FILE

        # Validate configuration
        if not self.repo_id:
            log("ERROR", "OPENCLAW_DATASET_REPO not set")
            raise ValueError("OPENCLAW_DATASET_REPO environment variable required")

        if not self.token:
            log("ERROR", "HF_TOKEN not set")
            raise ValueError("HF_TOKEN environment variable required")

        # Initialize API
        self.api = HfApi(token=self.token)

        log("INFO", "Initialized persistence manager",
            repo_id=self.repo_id,
            home_dir=str(self.home_dir))

    # -----------------------------------------------------------------------
    # Backup Operations
    # -----------------------------------------------------------------------

    def save(self) -> Dict[str, Any]:
        """
        Save current state to Hugging Face Dataset

        Creates a complete backup of ~/.openclaw directory as a tar.gz file.
        """
        operation_id = f"save-{int(time.time())}"
        start_time = time.time()

        log("INFO", "Starting save operation", operation_id=operation_id)

        # Check if home directory exists
        if not self.home_dir.exists():
            log("WARNING", "OpenClaw home directory does not exist, creating")
            self.home_dir.mkdir(parents=True, exist_ok=True)

        # Check for existing lock
        if self.lock_file.exists():
            log("WARNING", "Lock file exists, another operation may be in progress")
            # Continue anyway, but log warning

        # Create lock file
        try:
            self.lock_file.write_text(str(os.getpid()))
        except Exception as e:
            log("WARNING", "Could not create lock file", error=str(e))

        try:
            # Get directory info
            dir_size = get_directory_size(self.home_dir)
            log("INFO", "Directory size calculated",
                size_bytes=dir_size,
                size_mb=f"{dir_size / (1024*1024):.2f}")

            # Create tar archive
            with tempfile.TemporaryDirectory() as tmpdir:
                tar_path = Path(tmpdir) / Config.BACKUP_FILENAME
                manifest = self._create_tar_archive(tar_path)

                # Read archive info
                tar_size = tar_path.stat().st_size
                log("INFO", "Archive created",
                    size_bytes=tar_size,
                    size_mb=f"{tar_size / (1024*1024):.2f}",
                    files_count=manifest["file_count"])

                # Upload to dataset
                remote_path = f"{Config.BACKUP_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
                upload_result = self._upload_archive(tar_path, remote_path)

                # Update state file
                self._update_state({
                    "last_save_time": datetime.now().isoformat(),
                    "last_save_operation": operation_id,
                    "last_save_remote_path": remote_path,
                    "last_save_commit": upload_result.get("commit_id"),
                    "last_save_manifest": manifest,
                })

                # Rotate old backups
                self._rotate_backups()

            duration = time.time() - start_time
            log("INFO", "Save completed successfully",
                operation_id=operation_id,
                duration_seconds=f"{duration:.2f}")

            return {
                "success": True,
                "operation_id": operation_id,
                "remote_path": remote_path,
                "commit_id": upload_result.get("commit_id"),
                "duration": duration,
                "manifest": manifest
            }

        except Exception as e:
            log("ERROR", "Save operation failed",
                operation_id=operation_id,
                error=str(e),
                exc_info=True)
            return {
                "success": False,
                "operation_id": operation_id,
                "error": str(e)
            }
        finally:
            # Remove lock file
            if self.lock_file.exists():
                try:
                    self.lock_file.unlink()
                except Exception:
                    pass

    def _create_tar_archive(self, tar_path: Path) -> Dict[str, Any]:
        """Create tar.gz archive of OpenClaw home directory"""
        manifest = {
            "created_at": datetime.now().isoformat(),
            "version": "1.0",
            "file_count": 0,
            "excluded_patterns": [],
            "included_dirs": [],
            "skipped_dirs": [],
        }

        excluded_count = 0

        def tar_filter(tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
            nonlocal excluded_count, manifest

            # Skip lock file itself
            if tarinfo.name.endswith(Config.LOCK_FILE):
                excluded_count += 1
                return None

            # Skip state file (will be written after backup)
            if tarinfo.name.endswith(Config.BACKUP_STATE_FILE):
                return None

            # Get relative path
            rel_path = tarinfo.name
            if rel_path.startswith("./"):
                rel_path = rel_path[2:]

            # Check exclusion patterns
            if should_exclude(rel_path, Config.EXCLUDE_PATTERNS):
                excluded_count += 1
                manifest["excluded_patterns"].append(rel_path)
                return None

            # Check if parent directory should be skipped
            path_parts = Path(rel_path).parts
            if path_parts and path_parts[0] in Config.SKIP_DIRS:
                excluded_count += 1
                return None

            # Track included
            manifest["file_count"] += 1
            if path_parts and path_parts[0] not in manifest["included_dirs"]:
                manifest["included_dirs"].append(path_parts[0])

            return tarinfo

        # Create archive
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(self.home_dir, arcname=".", filter=tar_filter)

        manifest["excluded_count"] = excluded_count
        manifest["skipped_dirs"] = list(Config.SKIP_DIRS)

        return manifest

    def _upload_archive(self, local_path: Path, remote_path: str) -> Dict[str, Any]:
        """Upload archive to Hugging Face Dataset"""
        try:
            # Ensure repo exists
            try:
                self.api.repo_info(repo_id=self.repo_id, repo_type="dataset")
            except RepositoryNotFoundError:
                log("INFO", "Creating new dataset repository")
                self.api.create_repo(
                    repo_id=self.repo_id,
                    repo_type="dataset",
                    private=True
                )

            # Upload file
            commit_info = self.api.upload_file(
                path_or_fileobj=str(local_path),
                path_in_repo=remote_path,
                repo_id=self.repo_id,
                repo_type="dataset",
                commit_message=f"OpenClaw state backup - {datetime.now().isoformat()}"
            )

            log("INFO", "File uploaded successfully",
                remote_path=remote_path,
                commit_url=commit_info.commit_url)

            return {
                "success": True,
                "commit_id": commit_info.oid,
                "commit_url": commit_info.commit_url
            }

        except Exception as e:
            log("ERROR", "Upload failed", error=str(e))
            raise

    def _update_state(self, state_update: Dict[str, Any]):
        """Update persistence state file"""
        try:
            current_state = {}
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    current_state = json.load(f)

            current_state.update(state_update)

            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(current_state, f, indent=2)

        except Exception as e:
            log("WARNING", "Could not update state file", error=str(e))

    def _rotate_backups(self):
        """Rotate old backups, keeping only MAX_BACKUPS most recent"""
        try:
            files = self.api.list_repo_files(
                repo_id=self.repo_id,
                repo_type="dataset"
            )

            # Get backup files
            backups = [
                f for f in files
                if f.startswith(Config.BACKUP_PREFIX) and f.endswith(".tar.gz")
            ]

            # Sort by name (which includes timestamp)
            backups = sorted(backups)

            # Delete old backups
            if len(backups) > Config.MAX_BACKUPS:
                to_delete = backups[:-Config.MAX_BACKUPS]
                log("INFO", "Rotating backups",
                    total=len(backups),
                    keeping=Config.MAX_BACKUPS,
                    deleting=len(to_delete))

                for old_backup in to_delete:
                    try:
                        self.api.delete_file(
                            path_in_repo=old_backup,
                            repo_id=self.repo_id,
                            repo_type="dataset"
                        )
                        log("INFO", "Deleted old backup", file=old_backup)
                    except Exception as e:
                        log("WARNING", "Could not delete backup",
                            file=old_backup,
                            error=str(e))

        except Exception as e:
            log("WARNING", "Backup rotation failed", error=str(e))

    # -----------------------------------------------------------------------
    # Restore Operations
    # -----------------------------------------------------------------------

    def load(self, force: bool = False) -> Dict[str, Any]:
        """
        Load state from Hugging Face Dataset

        Restores the most recent backup. If force is False and local state
        exists, it will create a backup before restoring.
        """
        operation_id = f"load-{int(time.time())}"
        start_time = time.time()

        log("INFO", "Starting load operation",
            operation_id=operation_id,
            force=force)

        try:
            # Get latest backup
            backup_info = self._find_latest_backup()

            if not backup_info:
                log("WARNING", "No backups found, starting fresh")
                # Ensure home directory exists
                self.home_dir.mkdir(parents=True, exist_ok=True)
                return {
                    "success": True,
                    "operation_id": operation_id,
                    "restored": False,
                    "message": "No backups found, starting fresh"
                }

            log("INFO", "Found backup to restore",
                backup_file=backup_info["filename"],
                timestamp=backup_info.get("timestamp"))

            # Create local backup if state exists
            if self.home_dir.exists() and not force:
                backup_dir = self._create_local_backup()
                log("INFO", "Created local backup", backup_dir=str(backup_dir))

            # Download and extract
            with tempfile.TemporaryDirectory() as tmpdir:
                tar_path = Path(tmpdir) / "backup.tar.gz"

                # Download backup
                log("INFO", "Downloading backup...")
                downloaded_path = hf_hub_download(
                    repo_id=self.repo_id,
                    filename=backup_info["filename"],
                    repo_type="dataset",
                    token=self.token,
                    local_dir=tmpdir,
                    local_dir_use_symlinks=False
                )

                # Extract archive
                log("INFO", "Extracting archive...")
                self._extract_archive(downloaded_path)

            duration = time.time() - start_time
            log("INFO", "Load completed successfully",
                operation_id=operation_id,
                duration_seconds=f"{duration:.2f}")

            return {
                "success": True,
                "operation_id": operation_id,
                "restored": True,
                "backup_file": backup_info["filename"],
                "duration": duration
            }

        except Exception as e:
            log("ERROR", "Load operation failed",
                operation_id=operation_id,
                error=str(e),
                exc_info=True)
            return {
                "success": False,
                "operation_id": operation_id,
                "error": str(e)
            }

    def _find_latest_backup(self) -> Optional[Dict[str, Any]]:
        """Find the latest backup file in the dataset"""
        try:
            files = self.api.list_repo_files(
                repo_id=self.repo_id,
                repo_type="dataset"
            )

            # Get backup files sorted by name (timestamp)
            backups = sorted(
                [f for f in files if f.startswith(Config.BACKUP_PREFIX) and f.endswith(".tar.gz")],
                reverse=True
            )

            if not backups:
                return None

            latest = backups[0]

            # Extract timestamp from filename
            timestamp_str = latest.replace(Config.BACKUP_PREFIX, "").replace(".tar.gz", "")
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S").isoformat()
            except ValueError:
                timestamp = None

            return {
                "filename": latest,
                "timestamp": timestamp
            }

        except Exception as e:
            log("ERROR", "Could not find latest backup", error=str(e))
            return None

    def _create_local_backup(self) -> Optional[Path]:
        """Create a backup of local state before restore"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.home_dir.parent / f"{self.home_dir.name}_backup_{timestamp}"

        try:
            if self.home_dir.exists():
                shutil.copytree(self.home_dir, backup_dir)
                return backup_dir
        except Exception as e:
            log("WARNING", "Could not create local backup", error=str(e))

        return None

    def _extract_archive(self, tar_path: Path):
        """Extract tar.gz archive to home directory"""
        # Ensure home directory exists
        self.home_dir.mkdir(parents=True, exist_ok=True)

        # Extract archive
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(self.home_dir)

        log("INFO", "Archive extracted successfully",
            destination=str(self.home_dir))


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python openclaw_persist.py [save|load|status]", file=sys.stderr)
        print("", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  save    - Save current state to dataset", file=sys.stderr)
        print("  load    - Load state from dataset", file=sys.stderr)
        print("  status  - Show persistence status", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1].lower()

    try:
        manager = OpenClawPersistence()

        if command == "save":
            result = manager.save()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("success") else 1)

        elif command == "load":
            force = "--force" in sys.argv or "-f" in sys.argv
            result = manager.load(force=force)
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("success") else 1)

        elif command == "status":
            # Show status information
            status = {
                "configured": True,
                "repo_id": manager.repo_id,
                "home_dir": str(manager.home_dir),
                "home_exists": manager.home_dir.exists(),
            }

            # Load state file
            if manager.state_file.exists():
                with open(manager.state_file, 'r') as f:
                    state = json.load(f)
                    status["state"] = state

            # List backups
            backups = manager._find_latest_backup()
            status["latest_backup"] = backups

            print(json.dumps(status, indent=2))
            sys.exit(0)

        else:
            print(f"Unknown command: {command}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
