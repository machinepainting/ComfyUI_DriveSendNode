"""
DriveSend Setup Node
Handles Google Drive API authentication setup and encryption key generation
"""

import os
import json
import base64
from pathlib import Path

from .encrypt_file import generate_key


NODE_DIR = Path(__file__).parent


class DriveSendSetupNode:
    """
    ComfyUI node for setting up Google Drive API access and encryption.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "auth_method": (["service_account", "oauth"],),
                "folder_id": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Google Drive Folder ID (from URL)"
                }),
                "storage_method": (["env_file", "display_only"],),
                "encryption_key_method": (["off", "Display Only", "save to .env"],),
            },
            "optional": {
                "service_account_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to service_account.json (optional)"
                }),
                "reconnect": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "setup"
    CATEGORY = "DriveSend"
    
    def setup(
        self,
        auth_method,
        folder_id,
        storage_method,
        encryption_key_method,
        service_account_path="",
        reconnect=False
    ):
        output_lines = []
        env_vars = {}
        
        # Handle folder ID
        if folder_id:
            env_vars['GOOGLE_DRIVE_FOLDER_ID'] = folder_id
            output_lines.append(f"GOOGLE_DRIVE_FOLDER_ID={folder_id}")
        
        # Handle authentication based on method
        if auth_method == "service_account":
            # Try to find and encode service account
            sa_path = None
            
            if service_account_path and Path(service_account_path).exists():
                sa_path = Path(service_account_path)
            elif (NODE_DIR / 'service_account.json').exists():
                sa_path = NODE_DIR / 'service_account.json'
            
            if sa_path:
                try:
                    with open(sa_path, 'r') as f:
                        sa_json = f.read()
                    
                    # Base64 encode for environment variable storage
                    sa_base64 = base64.b64encode(sa_json.encode()).decode()
                    env_vars['GOOGLE_SERVICE_ACCOUNT_JSON'] = sa_base64
                    
                    # Parse to get client email for display
                    sa_data = json.loads(sa_json)
                    client_email = sa_data.get('client_email', 'unknown')
                    
                    output_lines.append(f"Service Account: {client_email}")
                    output_lines.append(f"GOOGLE_SERVICE_ACCOUNT_JSON=<base64 encoded - {len(sa_base64)} chars>")
                    
                    print(f"\n[DriveSend Setup] Service Account loaded: {client_email}")
                    print(f"[DriveSend Setup] Make sure to share your Google Drive folder with: {client_email}")
                
                except Exception as e:
                    output_lines.append(f"Error loading service account: {e}")
            else:
                output_lines.append("Warning: No service_account.json found")
                output_lines.append("Please place service_account.json in the node directory or provide a path")
        
        elif auth_method == "oauth":
            # OAuth will be handled at runtime
            creds_path = NODE_DIR / 'credentials.json'
            token_path = NODE_DIR / 'token.json'
            
            if creds_path.exists():
                output_lines.append("OAuth credentials.json found")
                
                if token_path.exists() and not reconnect:
                    output_lines.append("Existing token.json found - already authenticated")
                else:
                    output_lines.append("Run the AutoUploader node to complete OAuth authentication")
                    if reconnect:
                        # Delete existing token to force re-auth
                        try:
                            token_path.unlink()
                            output_lines.append("Deleted existing token for reconnection")
                        except:
                            pass
            else:
                output_lines.append("Warning: credentials.json not found")
                output_lines.append("Please download OAuth credentials from Google Cloud Console")
        
        # Handle encryption key
        if encryption_key_method != "off":
            # Check if key already exists
            existing_key = os.environ.get('comfyui_encryption_key')
            
            if existing_key and not reconnect:
                output_lines.append("Encryption key already configured")
                env_vars['comfyui_encryption_key'] = existing_key
            else:
                # Generate new key
                new_key = generate_key()
                env_vars['comfyui_encryption_key'] = new_key
                output_lines.append(f"comfyui_encryption_key={new_key}")
                print(f"\n[DriveSend Setup] Generated encryption key: {new_key}")
        
        # Save to .env file if requested
        if storage_method == "env_file" and env_vars:
            env_path = NODE_DIR / '.env'
            
            # Load existing .env if present
            existing_vars = {}
            if env_path.exists():
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            existing_vars[key] = value
            
            # Merge with new vars
            existing_vars.update(env_vars)
            
            # Write .env file
            with open(env_path, 'w') as f:
                for key, value in existing_vars.items():
                    f.write(f"{key}={value}\n")
            
            output_lines.append(f"\nCredentials saved to: {env_path}")
            print(f"[DriveSend Setup] Credentials saved to {env_path}")
        
        elif storage_method == "display_only":
            output_lines.append("\n--- Copy these to your environment variables ---")
            for key, value in env_vars.items():
                if key == 'GOOGLE_SERVICE_ACCOUNT_JSON':
                    # Print full base64 for copying
                    print(f"\n{key}={value}")
                else:
                    print(f"{key}={value}")
        
        # Print summary
        print("\n" + "="*50)
        print("[DriveSend Setup] Configuration complete!")
        print("="*50)
        
        status = "\n".join(output_lines)
        return (status,)


# Node registration
NODE_CLASS_MAPPINGS = {
    "DriveSendSetupNode": DriveSendSetupNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendSetupNode": "DriveSend Setup"
}
