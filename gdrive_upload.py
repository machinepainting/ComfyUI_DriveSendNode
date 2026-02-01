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


def upload_file(file_path, folder_id=None, service=None, auth_method='oauth', **kwargs):
    """
    Upload a file to Google Drive.
    
    Args:
        file_path: Path to the file to upload
        folder_id: Google Drive folder ID (optional, uses env var or root if not provided)
        service: Existing Drive service object (optional)
        auth_method: Authentication method ('oauth' or 'service_account')
        **kwargs: Additional arguments (for compatibility)
    
    Returns:
        dict with upload result including file ID and verification status
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        return {'success': False, 'error': f'File not found: {file_path}'}
    
    # Get or create service
    if service is None:
        try:
            service = get_drive_service(auth_method)
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
            fields='id, name, size, md5Checksum',
            supportsAllDrives=True
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
        error_msg = str(e)
        
        # Provide helpful error messages
        if 'storageQuotaExceeded' in error_msg:
            print(f"[DriveSend] ✗ Storage quota exceeded!")
            print(f"[DriveSend]   If using service account with personal Gmail, this won't work.")
            print(f"[DriveSend]   Service accounts require Google Workspace (paid).")
            print(f"[DriveSend]   For personal Gmail, use OAuth authentication instead.")
            return {
                'success': False, 
                'error': 'Storage quota exceeded. Service accounts do not work with personal Gmail. Use OAuth instead.'
            }
        
        print(f"[DriveSend] ✗ Google Drive API error: {error_msg}")
        return {'success': False, 'error': f'Google Drive API error: {error_msg}'}
    
    except Exception as e:
        error_msg = f'Upload failed: {e}'
        print(f"[DriveSend] ✗ {error_msg}")
        return {'success': False, 'error': error_msg}


def create_folder(folder_name, parent_folder_id=None, service=None, auth_method='oauth'):
    """
    Create a folder in Google Drive.
    
    Args:
        folder_name: Name of the folder to create
        parent_folder_id: Parent folder ID (optional)
        service: Existing Drive service object (optional)
        auth_method: Authentication method
    
    Returns:
        dict with folder creation result including folder ID
    """
    if service is None:
        try:
            service = get_drive_service(auth_method)
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
            fields='id, name',
            supportsAllDrives=True
        ).execute()
        
        print(f"[DriveSend] Created folder: {folder_name} (ID: {folder.get('id')})")
        return {
            'success': True,
            'folder_id': folder.get('id'),
            'folder_name': folder.get('name')
        }
    
    except HttpError as e:
        return {'success': False, 'error': f'Failed to create folder: {e}'}


def list_files(folder_id=None, service=None, auth_method='oauth', max_results=100):
    """
    List files in a Google Drive folder.
    
    Args:
        folder_id: Folder ID to list (optional, lists root if not provided)
        service: Existing Drive service object (optional)
        auth_method: Authentication method
        max_results: Maximum number of files to return
    
    Returns:
        dict with list of files or error
    """
    if service is None:
        try:
            service = get_drive_service(auth_method)
        except Exception as e:
            return {'success': False, 'error': f'Authentication failed: {e}'}
    
    if folder_id is None:
        folder_id = get_folder_id()
    
    query = f"'{folder_id}' in parents and trashed=false" if folder_id else "trashed=false"
    
    try:
        results = service.files().list(
            q=query,
            fields='files(id, name, size, mimeType, createdTime)',
            pageSize=max_results,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        files = results.get('files', [])
        return {
            'success': True,
            'files': files,
            'count': len(files)
        }
    
    except HttpError as e:
        return {'success': False, 'error': f'Failed to list files: {e}'}
