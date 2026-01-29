#!/usr/bin/env python3
"""
ComfyUI Encryption Scripts - Decryption (Windows)
Works with both DropSend and DriveSend nodes
Decrypts .enc files using a key from environment variable or manual input
"""

import os
import sys
import shutil

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Error: cryptography library not installed.")
    print("Run: pip install cryptography")
    sys.exit(1)


def get_encryption_key():
    """Get encryption key from environment variable or user input."""
    # Try multiple environment variable names for compatibility
    key = (os.environ.get('COMFYUI_ENCRYPTION_KEY') or 
           os.environ.get('comfyui_encryption_key') or
           os.environ.get('DROPSEND_ENCRYPTION_KEY') or
           os.environ.get('DRIVESEND_ENCRYPTION_KEY'))
    
    if key:
        print("Using key from environment variable.")
        return key
    
    # Prompt user
    print("")
    print("Encryption key not found in environment.")
    print("")
    print("To set up automatic key retrieval:")
    print("  1. Press Win + R, type 'sysdm.cpl', press Enter")
    print("  2. Go to Advanced tab > Environment Variables")
    print("  3. Under User variables, click New")
    print("  4. Variable name: COMFYUI_ENCRYPTION_KEY")
    print("  5. Variable value: [your encryption key]")
    print("  6. Click OK and restart any open terminals")
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
    print("=== ComfyUI File Decryption (Windows) ===")
    print("")
    
    # Get folder path
    folder = input("Enter the folder path containing .enc files: ").strip()
    folder = folder.strip('"\'')
    
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
