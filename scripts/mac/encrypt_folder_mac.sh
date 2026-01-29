#!/bin/bash

# ComfyUI Encryption Scripts - Encryption (macOS)
# Works with both DropSend and DriveSend nodes
# Encrypts image/video files using a key stored in macOS Keychain
#
# NOTE: This script is for LOCAL USE ONLY - for encrypting files on your local machine
# outside of ComfyUI. The nodes handle encryption automatically during upload.

echo "=== ComfyUI File Encryption (macOS) ==="
echo ""
echo "NOTE: This script is for LOCAL USE ONLY."
echo "The ComfyUI nodes handle encryption automatically during upload."
echo ""
echo "Drag in the folder of files to encrypt, or type the path:"

# Read folder path (supports drag-and-drop)
read -r FOLDER
# Remove any surrounding quotes and trailing backslash from drag-and-drop
FOLDER=$(echo "$FOLDER" | sed "s/^['\"]//;s/['\"]$//;s/\\\\$//" | xargs)

# Validate folder path
if [ -z "$FOLDER" ] || [ ! -d "$FOLDER" ]; then
    echo "Error: '$FOLDER' is not a valid directory."
    exit 1
fi

echo "Processing folder: $FOLDER"
echo ""

# Prompt for recursive option
echo "Would you like to encrypt files recursively (including subfolders)? (Y/N)"
read -r RECURSIVE_RESPONSE
if [[ "$RECURSIVE_RESPONSE" == "Y" || "$RECURSIVE_RESPONSE" == "y" ]]; then
    RECURSIVE="true"
else
    RECURSIVE="false"
fi

# Retrieve key from Keychain (try multiple names for compatibility)
echo ""
echo "Retrieving key from Keychain..."
KEY=$(security find-generic-password -s "ComfyUI_Encryption_Key" -a "ComfyUI" -w 2>/dev/null)
if [ -z "$KEY" ]; then
    KEY=$(security find-generic-password -s "DropSend_Encryption_Key" -a "DropSend" -w 2>/dev/null)
fi
if [ -z "$KEY" ]; then
    KEY=$(security find-generic-password -s "DriveSend_Encryption_Key" -a "DriveSend" -w 2>/dev/null)
fi

if [ -z "$KEY" ]; then
    echo ""
    echo "Error: Failed to retrieve key from Keychain."
    echo ""
    echo "To store your encryption key in Keychain:"
    echo "  1. Open Keychain Access (search in Spotlight)"
    echo "  2. Click File > New Password Item"
    echo "  3. Set Keychain Item Name: ComfyUI_Encryption_Key"
    echo "  4. Set Account Name: ComfyUI"
    echo "  5. Set Password: [your encryption key]"
    echo "  6. Click Add"
    echo ""
    exit 1
fi
echo "Key retrieved successfully."
echo ""

# Python script to encrypt supported files
python3 - <<EOF
import os
import sys
from cryptography.fernet import Fernet

# Supported file extensions
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

# Process files
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
    print("No supported files found in the specified location.")
    sys.exit(0)

print(f"Found {len(files_to_encrypt)} file(s) to encrypt.")
print("")

for file_path in files_to_encrypt:
    # Create temp file first, then rename
    temp_enc_path = file_path + '.tmp.enc'
    final_enc_path = file_path + '.enc'
    
    try:
        if encrypt_file(file_path, temp_enc_path, key):
            os.remove(file_path)  # Delete original
            os.rename(temp_enc_path, final_enc_path)  # Rename to final
            print(f"  ✓ Encrypted: {os.path.basename(file_path)} → {os.path.basename(final_enc_path)}")
            success_count += 1
        else:
            error_count += 1
            if os.path.exists(temp_enc_path):
                os.remove(temp_enc_path)
    except Exception as e:
        print(f"  ✗ Error processing {os.path.basename(file_path)}: {e}")
        error_count += 1
        if os.path.exists(temp_enc_path):
            os.remove(temp_enc_path)

print("")
print(f"Encryption complete: {success_count} successful, {error_count} failed")
EOF

# Check if encryption was successful
if [ $? -ne 0 ]; then
    echo "Error: Encryption process encountered an error."
    exit 1
fi

echo ""
echo "Done!"
