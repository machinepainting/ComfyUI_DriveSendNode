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
                "owner_email": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Your Gmail address (for ownership transfer)"
                }),
                "storage_method": (["display_only", "env_file"],),
                "encryption_key_method": (["off", "Display Only", "save to .env"],),
            },
            "optional": {
                "service_account_path": ("STRING", {
                    "default": "service_account.json",
                    "multiline": False,
                    "placeholder": "Path to service_account.json"
                }),
                "reconnect": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "setup"
    CATEGORY = "DriveSend"
    OUTPUT_NODE = True
    
    def setup(
        self,
        auth_method,
        folder_id,
        owner_email,
        storage_method,
        encryption_key_method,
        service_account_path="service_account.json",
        reconnect=False
    ):
        output_lines = []
        env_vars = {}
        
        print("\n" + "="*60)
        print("[DriveSend Setup] Starting configuration...")
        print("="*60)
        
        # Handle folder ID
        if folder_id:
            env_vars['GOOGLE_DRIVE_FOLDER_ID'] = folder_id
            output_lines.append(f"✓ Folder ID configured")
        else:
            output_lines.append("⚠ No Folder ID provided - will upload to Drive root")
        
        # Handle owner email (required for service account)
        if owner_email:
            env_vars['GOOGLE_OWNER_EMAIL'] = owner_email
            output_lines.append(f"✓ Owner Email: {owner_email}")
        elif auth_method == "service_account":
            output_lines.append("⚠ WARNING: No owner_email set!")
            output_lines.append("  Service accounts have 0 GB storage quota.")
            output_lines.append("  Files will fail to upload without ownership transfer.")
        
        # Handle authentication based on method
        if auth_method == "service_account":
            # Try to find service account file
            sa_path = None
            
            # Check provided path first
            if service_account_path:
                check_path = Path(service_account_path)
                if check_path.exists():
                    sa_path = check_path
                elif (NODE_DIR / service_account_path).exists():
                    sa_path = NODE_DIR / service_account_path
            
            # Fall back to default name in node directory
            if not sa_path and (NODE_DIR / 'service_account.json').exists():
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
                    
                    output_lines.append(f"✓ Service Account loaded: {client_email}")
                    output_lines.append(f"  Make sure your Drive folder is shared with this email!")
                    
                    print(f"\n[DriveSend Setup] Service Account: {client_email}")
                    print(f"[DriveSend Setup] Share your Google Drive folder with: {client_email}")
                
                except Exception as e:
                    output_lines.append(f"✗ Error loading service account: {e}")
            else:
                output_lines.append("✗ service_account.json NOT FOUND")
                output_lines.append("")
                output_lines.append("Please rename your downloaded JSON key file to:")
                output_lines.append("  service_account.json")
                output_lines.append("")
                output_lines.append("And place it in:")
                output_lines.append(f"  {NODE_DIR}/")
                return ("\n".join(output_lines),)
        
        elif auth_method == "oauth":
            output_lines.append("")
            output_lines.append("⚠ OAuth WARNING:")
            output_lines.append("  OAuth tokens expire every 7 DAYS in testing mode.")
            output_lines.append("  You will need to re-authenticate weekly.")
            output_lines.append("  Service Account is recommended for persistent use.")
            output_lines.append("")
            
            creds_path = NODE_DIR / 'credentials.json'
            token_path = NODE_DIR / 'token.json'
            
            if creds_path.exists():
                output_lines.append("✓ OAuth credentials.json found")
                
                if token_path.exists() and not reconnect:
                    output_lines.append("✓ Existing token.json found - already authenticated")
                else:
                    output_lines.append("→ Run the AutoUploader node to complete OAuth authentication")
                    if reconnect:
                        try:
                            token_path.unlink()
                            output_lines.append("  Deleted existing token for reconnection")
                        except:
                            pass
            else:
                output_lines.append("✗ credentials.json NOT FOUND")
                output_lines.append("  Download OAuth credentials from Google Cloud Console")
        
        # Handle encryption key
        if encryption_key_method != "off":
            existing_key = os.environ.get('comfyui_encryption_key')
            
            if existing_key and not reconnect:
                output_lines.append("✓ Encryption key already configured")
                env_vars['comfyui_encryption_key'] = existing_key
            else:
                new_key = generate_key()
                env_vars['comfyui_encryption_key'] = new_key
                output_lines.append("✓ New encryption key generated")
        
        # Output based on storage method
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
            
            output_lines.append(f"\n✓ Credentials saved to: {env_path}")
        
        elif storage_method == "display_only":
            output_lines.append("")
            output_lines.append("="*50)
            output_lines.append("COPY THESE TO RUNPOD SECRETS / ENV VARIABLES:")
            output_lines.append("="*50)
            
            # Print to console for copying
            print("\n" + "="*60)
            print("COPY THESE VALUES TO YOUR ENVIRONMENT VARIABLES:")
            print("="*60)
            
            for key, value in env_vars.items():
                print(f"\n{key}={value}")
            
            print("\n" + "="*60)
            print("See console output above for full values to copy")
            print("="*60)
        
        # Print summary
        print("\n" + "="*60)
        print("[DriveSend Setup] Configuration complete!")
        print("="*60 + "\n")
        
        status = "\n".join(output_lines)
        return (status,)


# Node registration
NODE_CLASS_MAPPINGS = {
    "DriveSendSetupNode": DriveSendSetupNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendSetupNode": "DriveSend Setup"
}
