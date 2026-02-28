import os
import tarfile
import sys

from huggingface_hub import hf_hub_download, HfApi


def main() -> None:
    """
    从 Hugging Face Dataset 恢复 ~/.openclaw 目录到本地。

    依赖环境变量：
    - HF_TOKEN: 具有写入/读取权限的 HF Access Token
    - OPENCLAW_DATASET_REPO: 数据集 repo_id，例如 "username/dataset-name"
    """
    repo_id = os.environ.get("OPENCLAW_DATASET_REPO")
    token = os.environ.get("HF_TOKEN")

    if not repo_id or not token:
        # 未配置就直接跳过，不报错以免阻塞网关启动
        return

    state_dir = os.path.expanduser("~/.openclaw")
    os.makedirs(state_dir, exist_ok=True)

    try:
        # List all files and find the latest backup
        api = HfApi(token=token)
        files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
        
        # Filter for our backup pattern (support both .tar and .tar.gz)
        backups = sorted([f for f in files if f.startswith("state/backup-") and (f.endswith(".tar") or f.endswith(".tar.gz"))], reverse=True)
        
        if not backups:
            # Fallback to legacy filename if no rolling backups exist
            if "state/openclaw.tar" in files:
                backups = ["state/openclaw.tar"]
            else:
                print("[restore_from_dataset] No backups found.", file=sys.stderr)
                return

        # Try to restore from the latest backup, falling back to older ones if needed
        success = False
        for backup_file in backups:
            print(f"[restore_from_dataset] Attempting to restore from: {backup_file}")
            try:
                tar_path = hf_hub_download(
                    repo_id=repo_id,
                    repo_type="dataset",
                    filename=backup_file,
                    token=token,
                )
                
                # Auto-detect compression based on file extension or header (r:*)
                with tarfile.open(tar_path, "r:*") as tf:
                    tf.extractall(state_dir)
                
                print(f"[restore_from_dataset] Successfully restored from {backup_file}")
                success = True
                break
            except Exception as e:
                print(f"[restore_from_dataset] Failed to restore {backup_file}: {e}", file=sys.stderr)
                # Continue to next backup
        
        if not success:
             print("[restore_from_dataset] All backup restore attempts failed.", file=sys.stderr)
             return

    except Exception as e:
        # General failure (network, auth, etc)
        print(f"[restore_from_dataset] Restore process failed: {e}", file=sys.stderr)
        return

    # 重要：不要删除 credentials/whatsapp。恢复的凭证用于自动连接；
    # 若在此处删除会导致每次启动都需重新扫码，且 dataset 中的好状态无法被使用。


if __name__ == "__main__":
    main()
