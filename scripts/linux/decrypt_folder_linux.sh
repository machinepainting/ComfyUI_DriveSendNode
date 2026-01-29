#!/bin/bash

# ComfyUI Encryption Scripts - Decryption (Linux)
# Works with both DropSend and DriveSend nodes
# Decrypts .enc files using a key from environment variable or Secret Service

echo "=== ComfyUI File Decryption (Linux) ==="
echo ""
echo "Enter the folder path containing .enc files:"

read -r FOLDER
FOLDER=$(echo "$FOLDER" | sed "s/^['\"]//;s/['\"]$//")

if [ -z "$FOLDER" ] || [ ! -d "$FOLDER" ]; then
    echo "Error: '$FOLDER' is not a valid directory."
    exit 1
fi

echo "Processing folder: $FOLDER"
echo ""

echo "Would you like to decrypt files recursively (including subfolders)? (Y/N)"
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
    echo "Encryption key not found in environment or Secret Service."
    echo ""
    echo "To set up automatic key retrieval, either:"
    echo "  1. Set environment variable: export COMFYUI_ENCRYPTION_KEY=\"your_key\""
    echo "  2. Store with secret-tool: echo -n \"your_key\" | secret-tool store --label=\"ComfyUI\" service ComfyUI username ComfyUI"
    echo ""
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

def decrypt_file(encrypted_path, output_path, key):
    try:
        fernet = Fernet(key.encode())
        with open(encrypted_path, 'rb') as enc_file:
            encrypted_data = enc_file.read()
        decrypted_data = fernet.decrypt(encrypted_data)
        with open(output_path, 'wb') as dec_file:
            dec_file.write(decrypted_data)
        print(f"  ✓ Decrypted: {os.path.basename(output_path)}")
        return True
    except Exception as e:
        print(f"  ✗ Error decrypting {os.path.basename(encrypted_path)}: {e}")
        return False

folder = "$FOLDER"
key = "$KEY"
recursive = "$RECURSIVE" == "true"

enc_files = []
success_count = 0
error_count = 0

print("Scanning for .enc files...")

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
    print("No .enc files found.")
    sys.exit(0)

print(f"Found {len(enc_files)} .enc file(s) to decrypt.")
print("")

for enc_path in enc_files:
    out_path = enc_path[:-4]
    if decrypt_file(enc_path, out_path, key):
        success_count += 1
    else:
        error_count += 1

print("")
print(f"Decryption complete: {success_count} successful, {error_count} failed")
EOF

if [ $? -ne 0 ]; then
    echo "Error: Decryption process encountered an error."
    exit 1
fi

echo ""
echo "Would you like to move all .enc files to a separate folder? (Y/N)"
read -r MOVE_RESPONSE
if [[ "$MOVE_RESPONSE" == "Y" || "$MOVE_RESPONSE" == "y" ]]; then
    ENC_FOLDER="$FOLDER/_encrypted_originals"
    mkdir -p "$ENC_FOLDER"
    MOVED_COUNT=0
    
    if [ "$RECURSIVE" = "true" ]; then
        while IFS= read -r -d '' file; do
            if [ -f "$file" ]; then
                mv "$file" "$ENC_FOLDER/$(basename "$file")"
                ((MOVED_COUNT++))
            fi
        done < <(find "$FOLDER" -type f -name "*.enc" -print0)
    else
        for file in "$FOLDER"/*.enc; do
            if [ -f "$file" ]; then
                mv "$file" "$ENC_FOLDER/$(basename "$file")"
                ((MOVED_COUNT++))
            fi
        done
    fi
    
    echo "Moved $MOVED_COUNT .enc file(s) to: $ENC_FOLDER"
else
    echo "Leaving .enc files in place."
fi

echo ""
echo "Done!"
