"""
File encryption module for DriveSend
Uses Fernet (AES-128) symmetric encryption
"""

import os
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet


def get_encryption_key():
    """
    Get the encryption key from environment variable.
    Checks multiple possible key names for compatibility with DropSend.
    
    Key retrieval order:
      - COMFYUI_ENCRYPTION_KEY (uppercase - preferred)
      - comfyui_encryption_key (lowercase - DropSend compatibility)
      - DROPSEND_ENCRYPTION_KEY
      - DRIVESEND_ENCRYPTION_KEY
    
    Returns:
        str: The encryption key, or None if not set
    """
    return (
        os.environ.get('COMFYUI_ENCRYPTION_KEY') or
        os.environ.get('comfyui_encryption_key') or
        os.environ.get('DROPSEND_ENCRYPTION_KEY') or
        os.environ.get('DRIVESEND_ENCRYPTION_KEY')
    )


def encrypt_file(input_path, output_path=None, key=None):
    """
    Encrypt a file using Fernet (AES-128).
    
    Args:
        input_path: Path to the file to encrypt
        output_path: Path for the encrypted file (default: input_path + '.enc')
        key: Encryption key (default: from environment variable)
    
    Returns:
        dict with encryption result:
            - success: bool
            - encrypted_path: str (if successful)
            - checksum: str (SHA256 of original file)
            - error: str (if failed)
    """
    try:
        input_path = Path(input_path)
        
        if not input_path.exists():
            return {"success": False, "error": f"File not found: {input_path}"}
        
        # Get encryption key
        if key is None:
            key = get_encryption_key()
        
        if not key:
            return {"success": False, "error": "No encryption key found. Set COMFYUI_ENCRYPTION_KEY environment variable."}
        
        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()
        
        # Create Fernet cipher
        try:
            fernet = Fernet(key)
        except Exception as e:
            return {"success": False, "error": f"Invalid encryption key: {e}"}
        
        # Read file
        with open(input_path, 'rb') as f:
            data = f.read()
        
        # Calculate checksum of original file
        checksum = hashlib.sha256(data).hexdigest()
        
        # Encrypt
        encrypted_data = fernet.encrypt(data)
        
        # Determine output path
        if output_path is None:
            output_path = Path(str(input_path) + '.enc')
        else:
            output_path = Path(output_path)
        
        # Write encrypted file
        with open(output_path, 'wb') as f:
            f.write(encrypted_data)
        
        return {
            "success": True,
            "encrypted_path": str(output_path),
            "original_path": str(input_path),
            "checksum": checksum,
            "original_size": len(data),
            "encrypted_size": len(encrypted_data)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def decrypt_file(input_path, output_path=None, key=None):
    """
    Decrypt a file using Fernet (AES-128).
    
    Args:
        input_path: Path to the encrypted file
        output_path: Path for the decrypted file (default: removes .enc extension)
        key: Encryption key (default: from environment variable)
    
    Returns:
        dict with decryption result:
            - success: bool
            - decrypted_path: str (if successful)
            - checksum: str (SHA256 of decrypted file)
            - error: str (if failed)
    """
    try:
        input_path = Path(input_path)
        
        if not input_path.exists():
            return {"success": False, "error": f"File not found: {input_path}"}
        
        # Get encryption key
        if key is None:
            key = get_encryption_key()
        
        if not key:
            return {"success": False, "error": "No encryption key found. Set COMFYUI_ENCRYPTION_KEY environment variable."}
        
        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()
        
        # Create Fernet cipher
        try:
            fernet = Fernet(key)
        except Exception as e:
            return {"success": False, "error": f"Invalid encryption key: {e}"}
        
        # Read encrypted file
        with open(input_path, 'rb') as f:
            encrypted_data = f.read()
        
        # Decrypt
        try:
            decrypted_data = fernet.decrypt(encrypted_data)
        except Exception as e:
            return {"success": False, "error": f"Decryption failed (wrong key?): {e}"}
        
        # Calculate checksum of decrypted file
        checksum = hashlib.sha256(decrypted_data).hexdigest()
        
        # Determine output path
        if output_path is None:
            # Remove .enc extension if present
            if input_path.suffix == '.enc':
                output_path = input_path.with_suffix('')
            else:
                output_path = Path(str(input_path) + '.decrypted')
        else:
            output_path = Path(output_path)
        
        # Write decrypted file
        with open(output_path, 'wb') as f:
            f.write(decrypted_data)
        
        return {
            "success": True,
            "decrypted_path": str(output_path),
            "encrypted_path": str(input_path),
            "checksum": checksum,
            "decrypted_size": len(decrypted_data)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}
