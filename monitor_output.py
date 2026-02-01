"""
Output Monitor Module
Watches a directory for new files and triggers uploads
"""

import os
import time
import threading
import queue
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .gdrive_upload import upload_file
from .encrypt_file import encrypt_file, get_encryption_key


# Supported file extensions
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.avi', '.mov'}


class UploadHandler(FileSystemEventHandler):
    """Handles file system events and queues files for upload."""
    
    def __init__(self, upload_queue, recursive=True):
        super().__init__()
        self.upload_queue = upload_queue
        self.recursive = recursive
        self.processed_files = set()
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Check if file extension is supported
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        
        # Avoid processing the same file multiple times
        if str(file_path) in self.processed_files:
            return
        
        self.processed_files.add(str(file_path))
        
        # Wait a moment for file to be fully written
        time.sleep(0.5)
        
        # Add to queue
        self.upload_queue.put(str(file_path))
        print(f"[DriveSend] Queued: {file_path.name}")


class OutputMonitor:
    """Monitors a directory and uploads new files to Google Drive."""
    
    def __init__(
        self,
        watch_dir,
        folder_id=None,
        recursive=True,
        enable_encryption=False,
        post_delete_enc=False,
        auth_method='service_account',
        owner_email=None,
        **auth_kwargs
    ):
        self.watch_dir = Path(watch_dir)
        self.folder_id = folder_id or os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
        self.recursive = recursive
        self.enable_encryption = enable_encryption
        self.post_delete_enc = post_delete_enc
        self.auth_method = auth_method
        self.owner_email = owner_email or os.environ.get('GOOGLE_OWNER_EMAIL')
        self.auth_kwargs = auth_kwargs
        
        self.upload_queue = queue.Queue()
        self.observer = None
        self.upload_thread = None
        self.running = False
        self.service = None
    
    def _upload_worker(self):
        """Worker thread that processes the upload queue."""
        from .gdrive_auth_manager import get_drive_service
        
        # Get authenticated service
        try:
            self.service = get_drive_service(self.auth_method, **self.auth_kwargs)
        except Exception as e:
            print(f"[DriveSend] Failed to authenticate: {e}")
            return
        
        while self.running:
            try:
                # Get file from queue with timeout
                file_path = self.upload_queue.get(timeout=1)
            except queue.Empty:
                continue
            
            try:
                file_to_upload = file_path
                encrypted_file = None
                
                # Encrypt if enabled
                if self.enable_encryption:
                    key = get_encryption_key()
                    if key:
                        result = encrypt_file(file_path, key=key)
                        if result['success']:
                            file_to_upload = result['output_path']
                            encrypted_file = file_to_upload
                        else:
                            print(f"[DriveSend] Encryption failed: {result.get('error')}")
                    else:
                        print("[DriveSend] Warning: Encryption enabled but no key found")
                
                # Upload file with owner_email for ownership transfer
                result = upload_file(
                    file_to_upload,
                    folder_id=self.folder_id,
                    service=self.service,
                    auth_method=self.auth_method,
                    owner_email=self.owner_email
                )
                
                if result['success']:
                    # Clean up encrypted file if requested
                    if encrypted_file and self.post_delete_enc:
                        try:
                            os.remove(encrypted_file)
                            print(f"[DriveSend] Deleted encrypted file: {Path(encrypted_file).name}")
                        except Exception as e:
                            print(f"[DriveSend] Failed to delete encrypted file: {e}")
                else:
                    print(f"[DriveSend] Upload failed: {result.get('error')}")
            
            except Exception as e:
                print(f"[DriveSend] Error processing {file_path}: {e}")
            
            finally:
                self.upload_queue.task_done()
    
    def start(self):
        """Start monitoring the directory."""
        if self.running:
            print("[DriveSend] Monitor already running")
            return
        
        if not self.watch_dir.exists():
            print(f"[DriveSend] Watch directory does not exist: {self.watch_dir}")
            return
        
        self.running = True
        
        # Start upload worker thread
        self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
        self.upload_thread.start()
        
        # Set up file system observer
        handler = UploadHandler(self.upload_queue, self.recursive)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.watch_dir), recursive=self.recursive)
        self.observer.start()
        
        print(f"[DriveSend] Started monitoring: {self.watch_dir}")
        if self.recursive:
            print("[DriveSend] Recursive monitoring enabled")
        if self.enable_encryption:
            print("[DriveSend] Encryption enabled")
        if self.owner_email:
            print(f"[DriveSend] Ownership will transfer to: {self.owner_email}")
        elif self.auth_method == 'service_account':
            print("[DriveSend] WARNING: No owner_email set - uploads may fail due to quota!")
    
    def stop(self):
        """Stop monitoring the directory."""
        if not self.running:
            return
        
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        
        if self.upload_thread:
            self.upload_thread.join(timeout=5)
            self.upload_thread = None
        
        print("[DriveSend] Stopped monitoring")
    
    def is_running(self):
        """Check if the monitor is running."""
        return self.running


# Global monitor instance
_monitor = None


def get_monitor():
    """Get the global monitor instance."""
    global _monitor
    return _monitor


def start_monitor(**kwargs):
    """Start a new global monitor instance."""
    global _monitor
    
    if _monitor and _monitor.is_running():
        _monitor.stop()
    
    _monitor = OutputMonitor(**kwargs)
    _monitor.start()
    return _monitor


def stop_monitor():
    """Stop the global monitor instance."""
    global _monitor
    
    if _monitor:
        _monitor.stop()
        _monitor = None
