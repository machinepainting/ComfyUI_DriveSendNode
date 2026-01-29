"""
Google Drive Upload Module
Handles file uploads to Google Drive with integrity verification
"""

import os
import hashlib
from pathlib import Path

from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from .gdrive_auth_manager import get_drive_service, get_folder_id


# MIME type mapping
MIME_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
    '.mp4': 'video/mp4',
    '.avi': 'video/x-msvideo',
    '.mov': 'video/quicktime',
    '.enc': 'application/octet-stream',
}


def get_mime_type(file_path):
    """Get MIME type based on file extension."""
    ext = Path(file_path).suffix.lower()
    return MIME_TYPES.get(ext, 'application/octet-stream')


def calculate_sha256(file_path):
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def upload_file(file_path, folder_id=None, service=None, auth_method='service_account', **auth_kwargs):
    """
    Upload a file to Google Drive.
    
    Args:
        file_path: Path to the file to upload
        folder_id: Google Drive folder ID (optional, uses env var or root if not provided)
        service: Existing Drive service object (optional)
        auth_method: Authentication method ('service_account' or 'oauth')
        **auth_kwargs: Additional auth arguments
    
    Returns:
        dict with upload result including file ID and verification status
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        return {'success': False, 'error': f'File not found: {file_path}'}
    
    # Get or create service
    if service is None:
        try:
            service = get_drive_service(auth_method, **auth_kwargs)
        except Exception as e:
            return {'success': False, 'error': f'Authentication failed: {e}'}
    
    # Get folder ID
    if folder_id is None:
        folder_id = get_folder_id()
    
    # Calculate local hash for verification
    local_hash = calculate_sha256(file_path)
    
    # Prepare file metadata
    file_metadata = {
        'name': file_path.name,
        'description': f'Uploaded by ComfyUI DriveSend. SHA256: {local_hash}'
    }
    
    if folder_id:
        file_metadata['parents'] = [folder_id]
    
    # Prepare media
    mime_type = get_mime_type(file_path)
    media = MediaFileUpload(
        str(file_path),
        mimetype=mime_type,
        resumable=True
    )
    
    try:
        # Upload file
        print(f"[DriveSend] Uploading: {file_path.name}")
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, size, md5Checksum'
        ).execute()
        
        file_id = file.get('id')
        remote_size = int(file.get('size', 0))
        local_size = file_path.stat().st_size
        
        # Verify upload
        size_match = remote_size == local_size
        
        if size_match:
            print(f"[DriveSend] ✓ Upload verified: {file_path.name} (ID: {file_id})")
            return {
                'success': True,
                'file_id': file_id,
                'file_name': file.get('name'),
                'size': remote_size,
                'local_hash': local_hash,
                'verified': True
            }
        else:
            print(f"[DriveSend] ⚠ Upload size mismatch: local={local_size}, remote={remote_size}")
            return {
                'success': True,
                'file_id': file_id,
                'file_name': file.get('name'),
                'size': remote_size,
                'local_hash': local_hash,
                'verified': False,
                'warning': 'Size mismatch - file may be corrupted'
            }
    
    except HttpError as e:
        error_msg = f'Google Drive API error: {e}'
        print(f"[DriveSend] ✗ {error_msg}")
        return {'success': False, 'error': error_msg}
    
    except Exception as e:
        error_msg = f'Upload failed: {e}'
        print(f"[DriveSend] ✗ {error_msg}")
        return {'success': False, 'error': error_msg}


def create_folder(folder_name, parent_folder_id=None, service=None, auth_method='service_account', **auth_kwargs):
    """
    Create a folder in Google Drive.
    
    Args:
        folder_name: Name of the folder to create
        parent_folder_id: Parent folder ID (optional)
        service: Existing Drive service object (optional)
        auth_method: Authentication method
        **auth_kwargs: Additional auth arguments
    
    Returns:
        dict with folder creation result including folder ID
    """
    if service is None:
        try:
            service = get_drive_service(auth_method, **auth_kwargs)
        except Exception as e:
            return {'success': False, 'error': f'Authentication failed: {e}'}
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    
    if parent_folder_id:
        file_metadata['parents'] = [parent_folder_id]
    
    try:
        folder = service.files().create(
            body=file_metadata,
            fields='id, name'
        ).execute()
        
        print(f"[DriveSend] Created folder: {folder_name} (ID: {folder.get('id')})")
        return {
            'success': True,
            'folder_id': folder.get('id'),
            'folder_name': folder.get('name')
        }
    
    except HttpError as e:
        return {'success': False, 'error': f'Failed to create folder: {e}'}


def find_folder(folder_name, parent_folder_id=None, service=None, auth_method='service_account', **auth_kwargs):
    """
    Find a folder by name in Google Drive.
    
    Args:
        folder_name: Name of the folder to find
        parent_folder_id: Parent folder ID to search in (optional)
        service: Existing Drive service object (optional)
        auth_method: Authentication method
        **auth_kwargs: Additional auth arguments
    
    Returns:
        Folder ID if found, None otherwise
    """
    if service is None:
        try:
            service = get_drive_service(auth_method, **auth_kwargs)
        except Exception as e:
            print(f"[DriveSend] Authentication failed: {e}")
            return None
    
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
    
    try:
        results = service.files().list(
            q=query,
            fields='files(id, name)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            return files[0].get('id')
        return None
    
    except HttpError as e:
        print(f"[DriveSend] Error finding folder: {e}")
        return None
