"""
DriveSend Setup Node
Handles Google Drive API authentication setup for both OAuth and Service Account methods
"""

import os
import json
import base64
from pathlib import Path
from cryptography.fernet import Fernet


NODE_DIR = Path(__file__).parent


class DriveSendSetupNode:
    """Setup node for configuring Google Drive authentication."""
    
    CATEGORY = "DriveSend"
    FUNCTION = "setup"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "auth_method": (["oauth", "service_account"], {"default": "oauth"}),
                "folder_id": ("STRING", {
                    "default": "", 
                    "multiline": False,
                    "tooltip": "Google Drive folder ID from URL (after /folders/)"
                }),
                "storage_method": (["display_only", "env_file"], {"default": "display_only"}),
                "encryption_key_method": (["off", "display_only", "save_to_env"], {"default": "off"}),
            },
            "optional": {
                "client_id": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "OAuth Client ID (from Google Cloud Console)"
                }),
                "client_secret": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "OAuth Client Secret (from Google Cloud Console)"
                }),
                "auth_code": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Authorization code from OAuth flow (leave blank first run)"
                }),
            }
        }
    
    def setup(self, auth_method, folder_id, storage_method, encryption_key_method,
              client_id="", client_secret="", auth_code=""):
        """
        Set up Google Drive authentication.
        
        For OAuth:
        - First run: Opens browser for authorization, displays auth URL
        - Second run: Exchanges auth code for refresh token
        
        For Service Account:
        - Validates service_account.json exists
        - Displays environment variable format for RunPod
        """
        
        results = []
        env_vars = {}
        
        # Validate folder_id
        if not folder_id:
            return ("❌ Error: folder_id is required. Get it from your Google Drive folder URL.",)
        
        env_vars['GOOGLE_DRIVE_FOLDER_ID'] = folder_id
        
        # Handle encryption key
        encryption_key = None
        if encryption_key_method != "off":
            # Check for existing key
            # Check for existing key (multiple possible names)
            existing_key = (
                os.environ.get('COMFYUI_ENCRYPTION_KEY') or
                os.environ.get('comfyui_encryption_key') or
                os.environ.get('DROPSEND_ENCRYPTION_KEY') or
                os.environ.get('DRIVESEND_ENCRYPTION_KEY')
            )
            if existing_key:
                encryption_key = existing_key
                results.append("Using existing encryption key from environment")
            else:
                # Generate new key
                encryption_key = Fernet.generate_key().decode('utf-8')
                results.append("Generated new encryption key")
            
            env_vars['COMFYUI_ENCRYPTION_KEY'] = encryption_key
        
        # === OAuth Setup ===
        if auth_method == 'oauth':
            if not client_id or not client_secret:
                return (
                    "❌ Error: OAuth requires client_id and client_secret.\n\n"
                    "To get these:\n"
                    "1. Go to Google Cloud Console → APIs & Services → Credentials\n"
                    "2. Create OAuth 2.0 Client ID (Desktop app)\n"
                    "3. Copy Client ID and Client Secret here",
                )
            
            from .gdrive_auth_manager import get_oauth_credentials_for_setup
            
            if not auth_code:
                # First run - generate auth URL
                result = get_oauth_credentials_for_setup(client_id, client_secret)
                
                if 'auth_url' in result:
                    auth_url = result['auth_url']
                    
                    print("\n" + "="*60)
                    print("[DriveSend Setup] OAuth Authorization Required")
                    print("="*60)
                    print("\nClick the URL below to authorize DriveSend:\n")
                    print(auth_url)
                    print("\n" + "="*60)
                    print("After authorizing, copy the authorization code and paste")
                    print("it into the 'auth_code' field, then run this node again.")
                    print("="*60 + "\n")
                    
                    return (
                        f"🔐 OAuth Step 1: Authorization Required\n\n"
                        f"1. Click the URL in the terminal/console\n"
                        f"2. Sign in to Google and authorize DriveSend\n"
                        f"3. Copy the authorization code shown\n"
                        f"4. Paste it in the 'auth_code' field\n"
                        f"5. Run this node again",
                    )
                else:
                    return (f"❌ Error generating auth URL: {result.get('error', 'Unknown error')}",)
            
            else:
                # Second run - exchange code for tokens
                result = get_oauth_credentials_for_setup(client_id, client_secret, auth_code)
                
                if 'error' in result:
                    return (
                        f"❌ Error: {result['error']}\n\n"
                        f"The auth code may have expired or already been used.\n"
                        f"To fix:\n"
                        f"1. Clear the 'auth_code' field (delete the code)\n"
                        f"2. Run this node again to get a new URL\n"
                        f"3. Click the URL and authorize again\n"
                        f"4. Paste the new auth code",
                    )
                
                if 'credentials' in result:
                    creds = result['credentials']
                    
                    env_vars['GOOGLE_CLIENT_ID'] = creds['client_id']
                    env_vars['GOOGLE_CLIENT_SECRET'] = creds['client_secret']
                    env_vars['GOOGLE_REFRESH_TOKEN'] = creds['refresh_token']
                    
                    results.append("✓ OAuth authorization successful!")
                    results.append(f"✓ Refresh token obtained")
        
        # === Service Account Setup ===
        elif auth_method == 'service_account':
            sa_file = NODE_DIR / 'service_account.json'
            
            if not sa_file.exists():
                return (
                    "❌ Error: service_account.json not found.\n\n"
                    "To create one:\n"
                    "1. Go to Google Cloud Console → IAM & Admin → Service Accounts\n"
                    "2. Create a service account\n"
                    "3. Create a JSON key\n"
                    "4. Rename to 'service_account.json'\n"
                    "5. Place in: ComfyUI/custom_nodes/ComfyUI_DriveSendNode/\n\n"
                    "⚠️ NOTE: Service accounts only work with Google Workspace (paid).\n"
                    "For personal Gmail accounts, use OAuth instead.",
                )
            
            # Read and encode service account JSON
            try:
                with open(sa_file, 'r') as f:
                    sa_data = json.load(f)
                
                sa_email = sa_data.get('client_email', 'unknown')
                sa_json_b64 = base64.b64encode(json.dumps(sa_data).encode()).decode()
                
                env_vars['GOOGLE_SERVICE_ACCOUNT_JSON'] = sa_json_b64
                
                results.append("✓ Service account loaded")
                results.append(f"✓ Service account email: {sa_email}")
                results.append("")
                results.append("⚠️ IMPORTANT: Share your Google Drive folder with:")
                results.append(f"   {sa_email}")
                results.append("")
                results.append("⚠️ NOTE: Service accounts require Google Workspace.")
                results.append("   They do NOT work with personal Gmail accounts!")
                
            except Exception as e:
                return (f"❌ Error reading service_account.json: {e}",)
        
        # === Output Results ===
        print("\n" + "="*60)
        print("[DriveSend Setup] Configuration Complete!")
        print("="*60)
        print("\nCopy these values to your Environment Variables:\n")
        
        # Print FULL values (not truncated)
        for key, value in env_vars.items():
            print(f"{key}={value}")
        
        print("\n" + "="*60)
        print("Copy the values above to your RunPod Secrets")
        print("="*60 + "\n")
        
        # Save token.json for local use
        if auth_method == 'oauth' and 'GOOGLE_REFRESH_TOKEN' in env_vars:
            token_file = NODE_DIR / 'token.json'
            try:
                token_data = {
                    "token": None,
                    "refresh_token": env_vars['GOOGLE_REFRESH_TOKEN'],
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": env_vars['GOOGLE_CLIENT_ID'],
                    "client_secret": env_vars['GOOGLE_CLIENT_SECRET'],
                    "scopes": ["https://www.googleapis.com/auth/drive.file"]
                }
                with open(token_file, 'w') as f:
                    json.dump(token_data, f, indent=2)
                results.append(f"✓ Saved token.json for local use")
            except Exception as e:
                results.append(f"⚠️ Could not save token.json: {e}")
        
        # Save to .env file if requested
        if storage_method == 'env_file':
            env_file = NODE_DIR / '.env'
            try:
                with open(env_file, 'w') as f:
                    for key, value in env_vars.items():
                        f.write(f"{key}={value}\n")
                results.append(f"✓ Saved to {env_file}")
            except Exception as e:
                results.append(f"⚠️ Could not save .env file: {e}")
        
        # Build status message
        status_lines = [
            "✅ DriveSend Setup Complete!",
            "",
            f"Auth Method: {auth_method}",
            f"Folder ID: {folder_id}",
            f"Encryption: {'Enabled' if encryption_key else 'Disabled'}",
            "",
        ]
        status_lines.extend(results)
        status_lines.extend([
            "",
            "Check the console/terminal for credentials to copy.",
        ])
        
        if storage_method == 'display_only':
            status_lines.extend([
                "",
                "For RunPod: Copy the values from console to RunPod Secrets.",
            ])
        
        return ("\n".join(status_lines),)


# Node registration
NODE_CLASS_MAPPINGS = {
    "DriveSendSetup": DriveSendSetupNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendSetup": "DriveSend Setup"
}
