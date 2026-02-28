#!/usr/bin/env python3

import os
import sys
import json
import hashlib
import time
import tarfile
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
import logging

from huggingface_hub import HfApi
from huggingface_hub.utils import RepositoryNotFoundError
from huggingface_hub import hf_hub_download

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "atomic-restore", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

class AtomicDatasetRestorer:
    
    def __init__(self, repo_id: str, dataset_path: str = "state"):
        self.repo_id = repo_id
        self.dataset_path = Path(dataset_path)
        self.api = HfApi()
        self.max_retries = 3
        self.base_delay = 1.0
        
        logger.info("init", {
            "repo_id": repo_id,
            "dataset_path": dataset_path,
            "max_retries": self.max_retries
        })
    
    def calculate_checksum(self, file_path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def validate_integrity(self, metadata: Dict[str, Any], state_files: List[Path]) -> bool:
        """Validate data integrity using checksums"""
        try:
            if "checksum" not in metadata:
                logger.warning("no_checksum_in_metadata", {"action": "skipping_validation"})
                return True
            
            state_data = metadata.get("state_data", {})
            calculated_checksum = hashlib.sha256(
                json.dumps(state_data, sort_keys=True).encode()
            ).hexdigest()
            
            expected_checksum = metadata["checksum"]
            
            is_valid = calculated_checksum == expected_checksum
            
            logger.info("integrity_check", {
                "expected": expected_checksum,
                "calculated": calculated_checksum,
                "valid": is_valid
            })
            
            return is_valid
            
        except Exception as e:
            logger.error("integrity_validation_failed", {"error": str(e)})
            return False
    
    def create_backup_before_restore(self, target_dir: Path) -> Optional[Path]:
        try:
            if not target_dir.exists():
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = target_dir.parent / f"state_backup_{timestamp}"
            
            logger.info("creating_local_backup", {
                "source": str(target_dir),
                "backup": str(backup_dir)
            })
            
            shutil.copytree(target_dir, backup_dir)
            return backup_dir
            
        except Exception as e:
            logger.error("local_backup_failed", {"error": str(e)})
            return None
    
    def restore_from_commit(self, commit_sha: str, target_dir: Path, force: bool = False) -> Dict[str, Any]:
        """
        Restore state from specific commit
        
        Args:
            commit_sha: Git commit hash to restore from
            target_dir: Directory to restore state to
            force: Force restore without confirmation
            
        Returns:
            Dictionary with operation result
        """
        operation_id = f"restore_{int(time.time())}"
        
        logger.info("starting_atomic_restore", {
            "operation_id": operation_id,
            "commit_sha": commit_sha,
            "target_dir": str(target_dir),
            "force": force
        })
        
        try:
            # Validate commit exists
            try:
                repo_info = self.api.repo_info(
                    repo_id=self.repo_id,
                    repo_type="dataset",
                    revision=commit_sha
                )
                logger.info("commit_validated", {"commit": commit_sha})
            except Exception as e:
                error_result = {
                    "success": False,
                    "operation_id": operation_id,
                    "error": f"Invalid commit: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
                logger.error("commit_validation_failed", error_result)
                return error_result
            
            # Create backup before restore
            backup_dir = self.create_backup_before_restore(target_dir)
            
            # Create temporary directory for download
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # List files in the commit
                files = self.api.list_repo_files(
                    repo_id=self.repo_id,
                    repo_type="dataset",
                    revision=commit_sha
                )
                
                # Find state files
                state_files = [f for f in files if f.startswith(str(self.dataset_path))]
                if not state_files:
                    error_result = {
                        "success": False,
                        "operation_id": operation_id,
                        "error": "No state files found in commit",
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.error("no_state_files", error_result)
                    return error_result
                
                # Download state files
                downloaded_files = []
                metadata = None
                
                for file_path in state_files:
                    try:
                        local_path = hf_hub_download(
                            repo_id=self.repo_id,
                            repo_type="dataset",
                            filename=file_path,
                            revision=commit_sha,
                            local_files_only=False
                        )
                        
                        if local_path:
                            downloaded_files.append(Path(local_path))
                            
                            # Load metadata if this is metadata.json
                            if file_path.endswith("metadata.json"):
                                with open(local_path, "r") as f:
                                    metadata = json.load(f)
                                    
                    except Exception as e:
                        logger.error("file_download_failed", {"file": file_path, "error": str(e)})
                        continue
                
                if not metadata:
                    error_result = {
                        "success": False,
                        "operation_id": operation_id,
                        "error": "Metadata not found in state files",
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.error("metadata_not_found", error_result)
                    return error_result
                
                # Validate data integrity
                if not self.validate_integrity(metadata, downloaded_files):
                    error_result = {
                        "success": False,
                        "operation_id": operation_id,
                        "error": "Data integrity validation failed",
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.error("integrity_validation_failed", error_result)
                    return error_result
                
                # Create target directory
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # Restore files (except metadata.json which is for reference)
                restored_files = []
                for file_path in downloaded_files:
                    if file_path.name != "metadata.json":
                        dest_path = target_dir / file_path.name
                        shutil.copy2(file_path, dest_path)
                        restored_files.append(str(dest_path))
                        
                        logger.info("file_restored", {
                            "source": str(file_path),
                            "destination": str(dest_path)
                        })
                
                result = {
                    "success": True,
                    "operation_id": operation_id,
                    "commit_sha": commit_sha,
                    "backup_dir": str(backup_dir) if backup_dir else None,
                    "timestamp": datetime.now().isoformat(),
                    "restored_files": restored_files,
                    "metadata": metadata
                }
                
                logger.info("atomic_restore_completed", result)
                return result
                
        except Exception as e:
            error_result = {
                "success": False,
                "operation_id": operation_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.error("atomic_restore_failed", error_result)
            return error_result
    
    def restore_latest(self, target_dir: Path, force: bool = False) -> Dict[str, Any]:
        """Restore from the latest commit"""
        try:
            repo_info = self.api.repo_info(
                repo_id=self.repo_id,
                repo_type="dataset"
            )
            
            if not repo_info.sha:
                error_result = {
                    "success": False,
                    "error": "No commit found in repository",
                    "timestamp": datetime.now().isoformat()
                }
                logger.error("no_commit_found", error_result)
                return error_result
            
            return self.restore_from_commit(repo_info.sha, target_dir, force)
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to get latest commit: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
            logger.error("latest_commit_failed", error_result)
            return error_result

def main():
    """Main function for command line usage"""
    if len(sys.argv) < 3:
        print(json.dumps({
            "error": "Usage: python restore_from_dataset_atomic.py <repo_id> <target_dir> [--force]",
            "status": "error"
        }, indent=2))
        sys.exit(1)
    
    repo_id = sys.argv[1]
    target_dir = sys.argv[2]
    force = "--force" in sys.argv
    
    try:
        target_path = Path(target_dir)
        restorer = AtomicDatasetRestorer(repo_id)
        result = restorer.restore_latest(target_path, force)
        
        print(json.dumps(result, indent=2))
        
        if not result.get("success", False):
            sys.exit(1)
            
    except Exception as e:
        print(json.dumps({
            "error": str(e),
            "status": "error"
        }, indent=2))
        sys.exit(1)

if __name__ == "__main__":
    main()