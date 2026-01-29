"""
Google Drive Authentication Manager
Handles both Service Account and OAuth 2.0 authentication methods
"""

import os
import json
import base64
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If modifying scopes, delete token.json
SCOPES = ['https://www.googleapis.com/auth/drive.file']

NODE_DIR = Path(__file__).parent


def get_service_from_service_account(service_account_path=None, service_account_json=None):
    """
    Authenticate using a Service Account.
    
    Args:
        service_account_path: Path to service_account.json file
        service_account_json: Base64-encoded service account JSON (for env var storage)
    
    Returns:
        Google Drive API service object
    """
    credentials = None
    
    # Try environment variable first (base64 encoded)
    env_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if env_json:
        try:
            # Check if it's base64 encoded
            try:
                decoded = base64.b64decode(env_json).decode('utf-8')
                service_account_info = json.loads(decoded)
            except:
                # Maybe it's just raw JSON
                service_account_info = json.loads(env_json)
            
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
            print("[DriveSend] Authenticated using service account from environment variable")
        except Exception as e:
            print(f"[DriveSend] Failed to parse service account from env: {e}")
    
    # Try provided JSON string
    if not credentials and service_account_json:
        try:
            try:
                decoded = base64.b64decode(service_account_json).decode('utf-8')
                service_account_info = json.loads(decoded)
            except:
                service_account_info = json.loads(service_account_json)
            
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
            print("[DriveSend] Authenticated using provided service account JSON")
        except Exception as e:
            print(f"[DriveSend] Failed to parse provided service account JSON: {e}")
    
    # Try file path
    if not credentials and service_account_path:
        path = Path(service_account_path)
        if path.exists():
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    str(path), scopes=SCOPES
                )
                print(f"[DriveSend] Authenticated using service account file: {path}")
            except Exception as e:
                print(f"[DriveSend] Failed to load service account file: {e}")
    
    # Try default location
    if not credentials:
        default_path = NODE_DIR / 'service_account.json'
        if default_path.exists():
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    str(default_path), scopes=SCOPES
                )
                print(f"[DriveSend] Authenticated using default service account file")
            except Exception as e:
                print(f"[DriveSend] Failed to load default service account file: {e}")
    
    if not credentials:
        raise ValueError(
            "No valid service account credentials found. Please provide:\n"
            "  - GOOGLE_SERVICE_ACCOUNT_JSON environment variable (base64 encoded), or\n"
            "  - service_account.json file in the node directory, or\n"
            "  - Path to service account JSON file"
        )
    
    return build('drive', 'v3', credentials=credentials)


def get_service_from_oauth(credentials_path=None):
    """
    Authenticate using OAuth 2.0 (for local/personal use).
    
    Args:
        credentials_path: Path to credentials.json file (OAuth client ID)
    
    Returns:
        Google Drive API service object
    """
    creds = None
    token_path = NODE_DIR / 'token.json'
    
    # Try to load existing token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            print("[DriveSend] Loaded existing OAuth token")
        except Exception as e:
            print(f"[DriveSend] Failed to load token: {e}")
    
    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("[DriveSend] Refreshed OAuth token")
            except Exception as e:
                print(f"[DriveSend] Failed to refresh token: {e}")
                creds = None
        
        if not creds:
            # Need to do full OAuth flow
            creds_file = credentials_path or (NODE_DIR / 'credentials.json')
            
            if not Path(creds_file).exists():
                raise ValueError(
                    f"OAuth credentials file not found: {creds_file}\n"
                    "Please download credentials.json from Google Cloud Console."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)
            print("[DriveSend] Completed OAuth authentication")
        
        # Save the credentials for next time
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            print(f"[DriveSend] Saved OAuth token to {token_path}")
    
    return build('drive', 'v3', credentials=creds)


def get_drive_service(auth_method='service_account', **kwargs):
    """
    Get an authenticated Google Drive API service.
    
    Args:
        auth_method: 'service_account' or 'oauth'
        **kwargs: Additional arguments for the specific auth method
    
    Returns:
        Google Drive API service object
    """
    if auth_method == 'service_account':
        return get_service_from_service_account(
            service_account_path=kwargs.get('service_account_path'),
            service_account_json=kwargs.get('service_account_json')
        )
    elif auth_method == 'oauth':
        return get_service_from_oauth(
            credentials_path=kwargs.get('credentials_path')
        )
    else:
        raise ValueError(f"Unknown auth method: {auth_method}. Use 'service_account' or 'oauth'")


def get_folder_id():
    """Get the target folder ID from environment or return None (root)."""
    return os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
