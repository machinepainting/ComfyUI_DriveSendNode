#!/usr/bin/env python3
"""
ComfyUI Encryption Scripts - Cross-Platform Decryption
Works with both DropSend and DriveSend nodes
Compatible with macOS, Windows, and Linux

============================================================
LOCAL USE ONLY - Run this on your local machine to decrypt
.enc files downloaded/synced from Dropbox or Google Drive.
Do not run on cloud instances (RunPod, etc.)
============================================================

Key retrieval methods (checked in order):
  - COMFYUI_ENCRYPTION_KEY environment variable
  - comfyui_encryption_key environment variable
  - DROPSEND_ENCRYPTION_KEY environment variable
  - DRIVESEND_ENCRYPTION_KEY environment variable
  - macOS Keychain (ComfyUI_Encryption_Key, DropSend_Encryption_Key, or DriveSend_Encryption_Key)
  - Linux Secret Service (ComfyUI, DropSend, or DriveSend)
  - Manual input
"""

import os
import sys
import platform
import shutil

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Error: cryptography library not installed.")
    print("Run: pip install cryptography")
    sys.exit(1)


def get_key_from_macos_keychain():
    """Try to retrieve the key from macOS Keychain."""
    try:
        import subprocess
        # Try multiple keychain item names for compatibility
        for service, account in [
            ('ComfyUI_Encryption_Key', 'ComfyUI'),
            ('DropSend_Encryption_Key', 'DropSend'),
            ('DriveSend_Encryption_Key', 'DriveSend')
        ]:
            result = subprocess.run(
                ['security', 'find-generic-password', '-s', service, '-a', account, '-w'],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    except Exception:
        pass
    return None


def get_key_from_linux_secret_service():
    """Try to retrieve the key from Linux Secret Service."""
    try:
        import subprocess
        # Try multiple service names for compatibility
        for service, username in [
            ('ComfyUI', 'ComfyUI'),
            ('DropSend', 'DropSend'),
            ('DriveSend', 'DriveSend')
        ]:
            result = subprocess.run(
                ['secret-tool', 'lookup', 'service', service, 'username', username],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    except Exception:
        pass
    return None


def get_encryption_key():
    """Get encryption key from environment, platform credential store, or user input."""
    system = platform.system()
    
    # Try multiple environment variable names for compatibility
    key = (os.environ.get('COMFYUI_ENCRYPTION_KEY') or 
           os.environ.get('comfyui_encryption_key') or
           os.environ.get('DROPSEND_ENCRYPTION_KEY') or
           os.environ.get('DRIVESEND_ENCRYPTION_KEY'))
    
    if key:
        print("Using key from environment variable.")
        return key
    
    # Try platform-specific credential storage
    if system == 'Darwin':  # macOS
        key = get_key_from_macos_keychain()
        if key:
            print("Using key from macOS Keychain.")
            return key
    elif system == 'Linux':
        key = get_key_from_linux_secret_service()
        if key:
            print("Using key from Secret Service.")
            return key
    
    # Prompt user
    print("")
    print("Encryption key not found automatically.")
    print("")
    print("To set up automatic key retrieval:")
    if system == 'Darwin':
        print("  - Store in Keychain: Keychain Access > File > New Password Item")
        print("    Item Name: ComfyUI_Encryption_Key, Account: ComfyUI")
    elif system == 'Windows':
        print("  - Set environment variable COMFYUI_ENCRYPTION_KEY")
        print("    (Win+R > sysdm.cpl > Advanced > Environment Variables)")
    elif system == 'Linux':
        print("  - Set environment variable: export COMFYUI_ENCRYPTION_KEY=\"your_key\"")
        print("  - Or use secret-tool: echo -n \"key\" | secret-tool store --label=\"ComfyUI\" service ComfyUI username ComfyUI")
    print("")
    
    key = input("Enter your encryption key: ").strip()
    
    if not key:
        print("Error: No key provided.")
        sys.exit(1)
    
    return key


def decrypt_file(encrypted_path, output_path, fernet):
    """Decrypt a single file."""
    try:
        with open(encrypted_path, 'rb') as enc_file:
            encrypted_data = enc_file.read()
        decrypted_data = fernet.decrypt(encrypted_data)
        with open(output_path, 'wb') as dec_file:
            dec_file.write(decrypted_data)
        return True
    except Exception as e:
        print(f"  X Error decrypting {os.path.basename(encrypted_path)}: {e}")
        return False


def main():
    system = platform.system()
    print(f"=== ComfyUI File Decryption ({system}) ===")
    print("")
    print("Decrypts .enc files to restore original images/videos.")
    print("Works with both DropSend and DriveSend nodes.")
    print("")
    
    # Get folder path
    folder = input("Enter the folder path containing .enc files: ").strip()
    folder = folder.strip('"\'')
    folder = folder.replace('\\ ', ' ')
    
    if not folder or not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)
    
    print(f"Processing folder: {folder}")
    print("")
    
    # Recursive option
    recursive_input = input("Decrypt files recursively (including subfolders)? (Y/N): ").strip().upper()
    recursive = recursive_input == 'Y'
    
    # Get encryption key
    print("")
    key = get_encryption_key()
    
    try:
        fernet = Fernet(key.encode())
    except Exception as e:
        print(f"Error: Invalid encryption key format: {e}")
        sys.exit(1)
    
    print("")
    print("Scanning for .enc files...")
    
    # Find all .enc files
    enc_files = []
    if recursive:
        for root, _, files in os.walk(folder):
            for file in files:
                if file.endswith('.enc'):
                    enc_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(folder):
            if file.endswith('.enc'):
                enc_files.append(os.path.join(folder, file))
    
    if not enc_files:
        print("No .enc files found in the specified location.")
        sys.exit(0)
    
    print(f"Found {len(enc_files)} .enc file(s) to decrypt.")
    print("")
    
    success_count = 0
    error_count = 0
    
    for enc_path in enc_files:
        out_path = enc_path[:-4]  # Remove .enc
        
        if decrypt_file(enc_path, out_path, fernet):
            print(f"  + Decrypted: {os.path.basename(out_path)}")
            success_count += 1
        else:
            error_count += 1
    
    print("")
    print(f"Decryption complete: {success_count} successful, {error_count} failed")
    print("")
    
    # Offer to move .enc files
    move_input = input("Move all .enc files to a separate folder? (Y/N): ").strip().upper()
    if move_input == 'Y':
        enc_folder = os.path.join(folder, "_encrypted_originals")
        os.makedirs(enc_folder, exist_ok=True)
        moved_count = 0
        
        for enc_path in enc_files:
            if os.path.exists(enc_path):
                dest = os.path.join(enc_folder, os.path.basename(enc_path))
                shutil.move(enc_path, dest)
                moved_count += 1
        
        print(f"Moved {moved_count} .enc file(s) to: {enc_folder}")
    else:
        print("Leaving .enc files in place.")
    
    print("")
    print("Done!")


if __name__ == "__main__":
    main()
