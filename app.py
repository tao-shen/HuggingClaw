import subprocess
import sys

if __name__ == "__main__":
    # In a generic Docker Space, this might not be executed if CMD is set in Dockerfile.
    # But if the user switches to generic Python SDK or wants to run it manually:
    print("Starting OpenClaw Sync Wrapper...")
    subprocess.run([sys.executable, "scripts/sync_hf.py"], check=True)
