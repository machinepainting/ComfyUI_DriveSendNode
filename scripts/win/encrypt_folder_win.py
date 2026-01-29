#!/usr/bin/env python3
"""
ComfyUI Encryption Scripts - Encryption (Windows)
Works with both DropSend and DriveSend nodes
Encrypts image/video files using a key from environment variable or manual input

NOTE: This script is for LOCAL USE ONLY - for encrypting files on your local machine
outside of ComfyUI. The nodes handle encryption automatically during upload.
"""

import os
import sys

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Error: cryptography library not installed.")
    print("Run: pip install cryptography")
    sys.exit(1)


SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.avi', '.mov')


def get_encryption_key():
    """Get encryption key from environment variable or user input."""
    key = (os.environ.get('COMFYUI_ENCRYPTION_KEY') or 
           os.environ.get('comfyui_encryption_key') or
           os.environ.get('DROPSEND_ENCRYPTION_KEY') or
           os.environ.get('DRIVESEND_ENCRYPTION_KEY'))
    
    if key:
        print("Using key from environment variable.")
        return key
    
    print("")
    print("Encryption key not found in environment.")
    print("")
    key = input("Enter your encryption key: ").strip()
    
    if not key:
        print("Error: No key provided.")
        sys.exit(1)
    
    return key


def encrypt_file(input_path, output_path, fernet):
    """Encrypt a single file."""
    try:
        with open(input_path, 'rb') as in_file:
            data = in_file.read()
        encrypted_data = fernet.encrypt(data)
        with open(output_path, 'wb') as out_file:
            out_file.write(encrypted_data)
        return True
    except Exception as e:
        print(f"  X Error encrypting {os.path.basename(input_path)}: {e}")
        return False


def main():
    print("=== ComfyUI File Encryption (Windows) ===")
    print("")
    print("NOTE: This script is for LOCAL USE ONLY.")
    print("The ComfyUI nodes handle encryption automatically during upload.")
    print("")
    
    folder = input("Enter the folder path containing files to encrypt: ").strip().strip('"\'')
    
    if not folder or not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)
    
    recursive_input = input("Encrypt files recursively? (Y/N): ").strip().upper()
    recursive = recursive_input == 'Y'
    
    key = get_encryption_key()
    
    try:
        fernet = Fernet(key.encode())
    except Exception as e:
        print(f"Error: Invalid encryption key format: {e}")
        sys.exit(1)
    
    print("")
    print(f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")
    
    files_to_encrypt = []
    if recursive:
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(SUPPORTED_EXTENSIONS):
                    files_to_encrypt.append(os.path.join(root, file))
    else:
        for file in os.listdir(folder):
            if file.lower().endswith(SUPPORTED_EXTENSIONS):
                files_to_encrypt.append(os.path.join(folder, file))
    
    if not files_to_encrypt:
        print("No supported files found.")
        sys.exit(0)
    
    print(f"Found {len(files_to_encrypt)} file(s) to encrypt.")
    print("")
    
    success_count = 0
    error_count = 0
    
    for file_path in files_to_encrypt:
        temp_enc_path = file_path + '.tmp.enc'
        final_enc_path = file_path + '.enc'
        
        try:
            if encrypt_file(file_path, temp_enc_path, fernet):
                os.remove(file_path)
                os.rename(temp_enc_path, final_enc_path)
                print(f"  + Encrypted: {os.path.basename(file_path)}")
                success_count += 1
            else:
                error_count += 1
                if os.path.exists(temp_enc_path):
                    os.remove(temp_enc_path)
        except Exception as e:
            print(f"  X Error: {e}")
            error_count += 1
    
    print(f"\nEncryption complete: {success_count} successful, {error_count} failed")


if __name__ == "__main__":
    main()
