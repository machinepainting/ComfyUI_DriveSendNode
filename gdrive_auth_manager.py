"""
Google Drive Authentication Manager
Handles OAuth 2.0 and Service Account authentication with auto-refresh support
"""

import os
import json
import base64
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Scopes required for Google Drive uploads
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Path to credential files
NODE_DIR = Path(__file__).parent
SERVICE_ACCOUNT_FILE = NODE_DIR / 'service_account.json'
CLIENT_SECRET_FILE = NODE_DIR / 'client_secret.json'
TOKEN_FILE = NODE_DIR / 'token.json'


def get_folder_id():
    """Get the Google Drive folder ID from environment or return None."""
    return os.environ.get('GOOGLE_DRIVE_FOLDER_ID')


def get_service_account_credentials():
    """
    Get credentials from service account JSON file or environment variable.
    
    Returns:
        google.oauth2.service_account.Credentials or None
    """
    # Try environment variable first (base64 encoded JSON)
    sa_json_b64 = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if sa_json_b64:
        try:
            sa_json = base64.b64decode(sa_json_b64).decode('utf-8')
            sa_info = json.loads(sa_json)
            credentials = service_account.Credentials.from_service_account_info(
                sa_info, scopes=SCOPES
            )
            print("[DriveSend] Using service account from environment variable")
            return credentials
        except Exception as e:
            print(f"[DriveSend] Failed to load service account from env: {e}")
    
    # Try file
    if SERVICE_ACCOUNT_FILE.exists():
        try:
            credentials = service_account.Credentials.from_service_account_file(
                str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
            )
            print("[DriveSend] Using service account from file")
            return credentials
        except Exception as e:
            print(f"[DriveSend] Failed to load service account file: {e}")
    
    return None


def get_oauth_credentials():
    """
    Get OAuth 2.0 credentials with automatic refresh.
    
    Checks for credentials in this order:
    1. Environment variables (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN)
    2. Saved token.json file
    3. Interactive OAuth flow (requires browser)
    
    Returns:
        google.oauth2.credentials.Credentials or None
    """
    credentials = None
    
    # Option 1: Try environment variables (for RunPod)
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')
    
    if client_id and client_secret and refresh_token:
        try:
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES
            )
            # Force refresh to get a valid access token
            credentials.refresh(Request())
            print("[DriveSend] OAuth credentials loaded from environment variables")
            print("[DriveSend] ✓ Access token refreshed successfully")
            return credentials
        except Exception as e:
            print(f"[DriveSend] Failed to refresh OAuth token from env: {e}")
    
    # Option 2: Try saved token file
    if TOKEN_FILE.exists():
        try:
            credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                # Save refreshed token
                with open(TOKEN_FILE, 'w') as token:
                    token.write(credentials.to_json())
                print("[DriveSend] OAuth credentials loaded and refreshed from token file")
            elif credentials and credentials.valid:
                print("[DriveSend] OAuth credentials loaded from token file")
            return credentials
        except Exception as e:
            print(f"[DriveSend] Failed to load token file: {e}")
    
    # Option 3: Interactive OAuth flow (only works with browser)
    if CLIENT_SECRET_FILE.exists():
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            
            print("[DriveSend] Starting OAuth authorization flow...")
            print("[DriveSend] A browser window will open for authorization.")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            credentials = flow.run_local_server(port=0)
            
            # Save the credentials for future use
            with open(TOKEN_FILE, 'w') as token:
                token.write(credentials.to_json())
            
            print("[DriveSend] ✓ OAuth authorization complete")
            print(f"[DriveSend] Token saved to: {TOKEN_FILE}")
            return credentials
            
        except Exception as e:
            print(f"[DriveSend] OAuth flow failed: {e}")
            print("[DriveSend] Note: OAuth flow requires a browser. For headless servers,")
            print("[DriveSend] complete setup locally first and copy credentials to environment variables.")
    
    return None


def get_drive_service(auth_method='oauth', **kwargs):
    """
    Get an authenticated Google Drive service.
    
    Args:
        auth_method: 'oauth' or 'service_account'
        **kwargs: Additional arguments (unused, for compatibility)
    
    Returns:
        Google Drive API service object
    
    Raises:
        Exception if authentication fails
    """
    credentials = None
    
    if auth_method == 'service_account':
        credentials = get_service_account_credentials()
        if not credentials:
            raise Exception(
                "Service account credentials not found. "
                "Place service_account.json in the node folder or set GOOGLE_SERVICE_ACCOUNT_JSON environment variable.\n"
                "NOTE: Service accounts only work with Google Workspace accounts (paid). "
                "For personal Gmail, use OAuth instead."
            )
    
    elif auth_method == 'oauth':
        credentials = get_oauth_credentials()
        if not credentials:
            raise Exception(
                "OAuth credentials not found. Options:\n"
                "1. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN environment variables\n"
                "2. Place client_secret.json in the node folder and run setup to authorize\n"
                "3. Run setup locally first if using a headless server"
            )
    
    else:
        raise Exception(f"Unknown auth method: {auth_method}. Use 'oauth' or 'service_account'")
    
    # Build and return the Drive service
    service = build('drive', 'v3', credentials=credentials)
    return service


def get_oauth_credentials_for_setup(client_id, client_secret, auth_code=None):
    """
    Get OAuth credentials during setup process.
    
    If auth_code is provided, exchanges it for tokens.
    Otherwise, returns the authorization URL.
    
    Args:
        client_id: OAuth client ID
        client_secret: OAuth client secret
        auth_code: Authorization code from OAuth flow (optional)
    
    Returns:
        dict with either 'auth_url' or 'credentials' containing token info
    """
    from google_auth_oauthlib.flow import Flow
    
    # Create flow from client config
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }
    
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    
    if not auth_code:
        # Generate authorization URL
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent to get refresh token
        )
        return {'auth_url': auth_url}
    
    else:
        # Exchange auth code for tokens
        try:
            flow.fetch_token(code=auth_code)
            credentials = flow.credentials
            
            return {
                'credentials': {
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'refresh_token': credentials.refresh_token,
                    'token': credentials.token,
                    'token_uri': credentials.token_uri,
                    'scopes': list(credentials.scopes) if credentials.scopes else SCOPES
                }
            }
        except Exception as e:
            return {'error': str(e)}


def refresh_access_token(client_id, client_secret, refresh_token):
    """
    Refresh an access token using the refresh token.
    
    This is called automatically but can also be used to verify credentials.
    
    Args:
        client_id: OAuth client ID
        client_secret: OAuth client secret
        refresh_token: OAuth refresh token
    
    Returns:
        dict with 'access_token' or 'error'
    """
    import requests
    
    try:
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token'
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            return {'access_token': data.get('access_token')}
        else:
            return {'error': f"Token refresh failed: {response.text}"}
    
    except Exception as e:
        return {'error': str(e)}
