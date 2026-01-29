#!/bin/bash

# ComfyUI Encryption Scripts - Encryption (Linux)
# Works with both DropSend and DriveSend nodes
# Encrypts image/video files using a key from environment variable or Secret Service
#
# NOTE: This script is for LOCAL USE ONLY

echo "=== ComfyUI File Encryption (Linux) ==="
echo ""
echo "NOTE: This script is for LOCAL USE ONLY."
echo "The ComfyUI nodes handle encryption automatically during upload."
echo ""
echo "Enter the folder path containing files to encrypt:"

read -r FOLDER
FOLDER=$(echo "$FOLDER" | sed "s/^['\"]//;s/['\"]$//")

if [ -z "$FOLDER" ] || [ ! -d "$FOLDER" ]; then
    echo "Error: '$FOLDER' is not a valid directory."
    exit 1
fi

echo "Processing folder: $FOLDER"
echo ""

echo "Would you like to encrypt files recursively (including subfolders)? (Y/N)"
read -r RECURSIVE_RESPONSE
if [[ "$RECURSIVE_RESPONSE" == "Y" || "$RECURSIVE_RESPONSE" == "y" ]]; then
    RECURSIVE="true"
else
    RECURSIVE="false"
fi

echo ""
echo "Retrieving encryption key..."

# Try multiple environment variable names for compatibility
KEY="${COMFYUI_ENCRYPTION_KEY:-}"
[ -z "$KEY" ] && KEY="${comfyui_encryption_key:-}"
[ -z "$KEY" ] && KEY="${DROPSEND_ENCRYPTION_KEY:-}"
[ -z "$KEY" ] && KEY="${DRIVESEND_ENCRYPTION_KEY:-}"

# Try Secret Service with multiple names
if [ -z "$KEY" ] && command -v secret-tool &> /dev/null; then
    KEY=$(secret-tool lookup service ComfyUI username ComfyUI 2>/dev/null)
    [ -z "$KEY" ] && KEY=$(secret-tool lookup service DropSend username DropSend 2>/dev/null)
    [ -z "$KEY" ] && KEY=$(secret-tool lookup service DriveSend username DriveSend 2>/dev/null)
    if [ -n "$KEY" ]; then
        echo "Using key from Secret Service."
    fi
fi

if [ -z "$KEY" ]; then
    echo ""
    echo "Encryption key not found."
    echo -n "Enter your encryption key: "
    read -r KEY
    
    if [ -z "$KEY" ]; then
        echo "Error: No key provided."
        exit 1
    fi
else
    echo "Key retrieved successfully."
fi

echo ""

python3 - <<EOF
import os
import sys
from cryptography.fernet import Fernet

SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.avi', '.mov')

def encrypt_file(input_path, output_path, key):
    try:
        fernet = Fernet(key.encode())
        with open(input_path, 'rb') as in_file:
            data = in_file.read()
        encrypted_data = fernet.encrypt(data)
        with open(output_path, 'wb') as out_file:
            out_file.write(encrypted_data)
        return True
    except Exception as e:
        print(f"  ✗ Error encrypting {os.path.basename(input_path)}: {e}")
        return False

folder = "$FOLDER"
key = "$KEY"
recursive = "$RECURSIVE" == "true"

files_to_encrypt = []
success_count = 0
error_count = 0

print("Scanning for supported files...")
print(f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")
print("")

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

for file_path in files_to_encrypt:
    temp_enc_path = file_path + '.tmp.enc'
    final_enc_path = file_path + '.enc'
    
    try:
        if encrypt_file(file_path, temp_enc_path, key):
            os.remove(file_path)
            os.rename(temp_enc_path, final_enc_path)
            print(f"  ✓ Encrypted: {os.path.basename(file_path)}")
            success_count += 1
        else:
            error_count += 1
            if os.path.exists(temp_enc_path):
                os.remove(temp_enc_path)
    except Exception as e:
        print(f"  ✗ Error: {e}")
        error_count += 1

print("")
print(f"Encryption complete: {success_count} successful, {error_count} failed")
EOF

if [ $? -ne 0 ]; then
    echo "Error: Encryption process encountered an error."
    exit 1
fi

echo ""
echo "Done!"
