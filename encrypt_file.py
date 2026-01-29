"""
File Encryption Module
Handles Fernet (AES-128) encryption for files
"""

import os
from pathlib import Path
from cryptography.fernet import Fernet


def generate_key():
    """Generate a new Fernet encryption key."""
    return Fernet.generate_key().decode('utf-8')


def get_encryption_key():
    """
    Get the encryption key from environment variable.
    
    Returns:
        str: The encryption key, or None if not set
    """
    return os.environ.get('comfyui_encryption_key')


def encrypt_file(input_path, output_path=None, key=None):
    """
    Encrypt a file using Fernet (AES-128).
    
    Args:
        input_path: Path to the file to encrypt
        output_path: Path for the encrypted file (default: input_path + '.enc')
        key: Encryption key (default: from environment variable)
    
    Returns:
        dict with encryption result
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        return {'success': False, 'error': f'File not found: {input_path}'}
    
    if key is None:
        key = get_encryption_key()
    
    if not key:
        return {'success': False, 'error': 'No encryption key provided'}
    
    if output_path is None:
        output_path = input_path.with_suffix(input_path.suffix + '.enc')
    else:
        output_path = Path(output_path)
    
    try:
        fernet = Fernet(key.encode() if isinstance(key, str) else key)
        
        with open(input_path, 'rb') as f:
            data = f.read()
        
        encrypted_data = fernet.encrypt(data)
        
        with open(output_path, 'wb') as f:
            f.write(encrypted_data)
        
        print(f"[DriveSend] Encrypted: {input_path.name} → {output_path.name}")
        return {
            'success': True,
            'input_path': str(input_path),
            'output_path': str(output_path),
            'original_size': len(data),
            'encrypted_size': len(encrypted_data)
        }
    
    except Exception as e:
        return {'success': False, 'error': f'Encryption failed: {e}'}


def decrypt_file(input_path, output_path=None, key=None):
    """
    Decrypt a file using Fernet (AES-128).
    
    Args:
        input_path: Path to the encrypted file
        output_path: Path for the decrypted file (default: removes .enc extension)
        key: Encryption key (default: from environment variable)
    
    Returns:
        dict with decryption result
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        return {'success': False, 'error': f'File not found: {input_path}'}
    
    if key is None:
        key = get_encryption_key()
    
    if not key:
        return {'success': False, 'error': 'No encryption key provided'}
    
    if output_path is None:
        # Remove .enc extension
        if input_path.suffix == '.enc':
            output_path = input_path.with_suffix('')
        else:
            output_path = input_path.with_suffix('.decrypted')
    else:
        output_path = Path(output_path)
    
    try:
        fernet = Fernet(key.encode() if isinstance(key, str) else key)
        
        with open(input_path, 'rb') as f:
            encrypted_data = f.read()
        
        decrypted_data = fernet.decrypt(encrypted_data)
        
        with open(output_path, 'wb') as f:
            f.write(decrypted_data)
        
        print(f"[DriveSend] Decrypted: {input_path.name} → {output_path.name}")
        return {
            'success': True,
            'input_path': str(input_path),
            'output_path': str(output_path),
            'encrypted_size': len(encrypted_data),
            'decrypted_size': len(decrypted_data)
        }
    
    except Exception as e:
        return {'success': False, 'error': f'Decryption failed: {e}'}
