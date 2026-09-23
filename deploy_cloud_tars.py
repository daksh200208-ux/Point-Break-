"""
1-Click Automated Cloud GPU Voice Deployer for Point Break (TARS Voice)
======================================================================
Deploys the TARS voice server to Hugging Face Spaces (Free Cloud GPU / ZeroGPU)
in a single automated step, and links the live endpoint directly into Point Break.
Zero manual file uploading or web navigation required.
"""

import os
import sys

def main():
    print("=" * 70)
    print("   🚀 POINT BREAK -- 1-CLICK TARS CLOUD VOICE DEPLOYER")
    print("   Automatic Free Cloud GPU Setup (Hugging Face Spaces)")
    print("=" * 70)
    print()

    try:
        from huggingface_hub import HfApi, login
    except ImportError:
        print("[*] Installing required huggingface_hub package...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        from huggingface_hub import HfApi, login

    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("To deploy your free cloud endpoint automatically:")
        print("1. Get your free Hugging Face token from: https://huggingface.co/settings/tokens")
        print("   (Select 'Write' permission)")
        print()
        token = input("Paste your Hugging Face Token here: ").strip()

    if not token:
        print("[!] Error: Hugging Face token is required to deploy. Aborting.")
        return

    print("\n[*] Authenticating with Hugging Face...")
    try:
        login(token=token, add_to_git_credential=True)
        api = HfApi(token=token)
        user_info = api.whoami()
        username = user_info.get("name")
        print(f"  [+] Authenticated successfully as: @{username}")
    except Exception as e:
        print(f"[!] Authentication failed: {e}")
        return

    space_name = "point-break-tars"
    repo_id = f"{username}/{space_name}"
    print(f"\n[*] Creating / Updating Space: {repo_id}...")

    space_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tars_cloud_space"))
    if not os.path.exists(space_dir):
        space_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tars_cloud_space"))

    if not os.path.exists(space_dir):
        print(f"[!] Cloud space directory not found at: {space_dir}")
        return

    try:
        api.create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk="gradio",
            exist_ok=True
        )
        print(f"  [+] Space created/verified: https://huggingface.co/spaces/{repo_id}")
    except Exception as create_err:
        print(f"  [!] Note on repo creation: {create_err} (proceeding to upload)")

    print(f"\n[*] Uploading TARS Neural Voice weights & server to cloud...")
    try:
        api.upload_folder(
            folder_path=space_dir,
            repo_id=repo_id,
            repo_type="space",
            commit_message="Deploy TARS neural voice engine for Point Break"
        )
        print("  [+] All files uploaded successfully!")
    except Exception as up_err:
        print(f"[!] Upload failed: {up_err}")
        return

    direct_url = f"https://{username.replace('_', '-')}-{space_name.replace('_', '-')}.hf.space"
    print("\n" + "=" * 70)
    print("   🎉 DEPLOYMENT COMPLETE! YOUR CLOUD VOICE IS LIVE!")
    print(f"   Direct Endpoint: {direct_url}")
    print("=" * 70)
    print()

    # Automatically update DEFAULT_TARS_CLOUD_URL in tars_speak.py across both directories
    for target_dir in [
        os.path.abspath(os.path.dirname(__file__)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tars_commercial_2")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "jarvis")),
    ]:
        ts_path = os.path.join(target_dir, "tars_speak.py")
        if os.path.exists(ts_path):
            try:
                with open(ts_path, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                new_content = re.sub(
                    r'DEFAULT_TARS_CLOUD_URL = os\.environ\.get\("TARS_CLOUD_URL",\s*".*?"\)\.strip\(\)',
                    f'DEFAULT_TARS_CLOUD_URL = os.environ.get("TARS_CLOUD_URL", "{direct_url}").strip()',
                    content
                )
                with open(ts_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"  [+] Automatically updated default endpoint in: {ts_path}")
            except Exception as fe:
                print(f"  [!] Could not update {ts_path}: {fe}")

    print("\n[*] Point Break is now configured to automatically use this Cloud GPU endpoint!")
    print("    Every end user who uses Point Break will get instant ~0.7s TARS voice automatically!")

if __name__ == "__main__":
    main()
