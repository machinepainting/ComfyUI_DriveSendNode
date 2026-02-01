# monitor_output.py
# DriveSend upload monitor - watches for files and uploads to Google Drive

import os
import time
import threading
import logging
from queue import Queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .gdrive_upload import upload_file
from .encrypt_file import ENCRYPT_EXTENSIONS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('drivesend.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

watcher_observer = None
watcher_handler = None
encryption_enabled = False
_stop_queue_processor = False  # Stop signal for queue processor
_drive_service = None  # Cached Drive service


def wait_for_complete_write(file_path, timeout=10):
    """Wait for a file to be completely written before processing."""
    last_size = -1
    stable_count = 0
    checks = 0

    while checks < timeout * 2:
        try:
            current_size = os.path.getsize(file_path)
            if current_size == last_size:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0
                last_size = current_size
        except FileNotFoundError:
            pass
        time.sleep(0.5)
        checks += 1

    logger.warning(f"[DriveSend] Timeout: File may still be writing: {file_path}")
    return False


def stop_queue_processor():
    """Signal the queue processor to stop."""
    global _stop_queue_processor
    _stop_queue_processor = True
    logger.info("[DriveSend] Signaled upload queue processor to stop")


def reset_queue_processor():
    """Reset the stop signal for queue processor."""
    global _stop_queue_processor
    _stop_queue_processor = False


class NewFileHandler(FileSystemEventHandler):
    """
    Handles new file events and queues them for upload.
    When encryption is enabled, only uploads .enc files.
    When encryption is disabled, uploads image/video files directly.
    """
    
    def __init__(self, folder_id, auth_method='oauth', delete_enc=False):
        super().__init__()
        self.folder_id = folder_id
        self.auth_method = auth_method
        self.delete_enc = delete_enc
        self.file_queue = Queue()
        self.start_queue_processor()

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        
        # When encryption is enabled, only process .enc files
        if encryption_enabled and not file_path.lower().endswith('.enc'):
            logger.debug(f"[DriveSend] Skipping non-.enc file (encryption enabled): {file_path}")
            return
        
        # When encryption is disabled, skip .enc files and only process supported extensions
        if not encryption_enabled:
            if file_path.lower().endswith('.enc'):
                logger.debug(f"[DriveSend] Skipping .enc file (encryption disabled): {file_path}")
                return
            if not file_path.lower().endswith(ENCRYPT_EXTENSIONS):
                logger.debug(f"[DriveSend] Skipping unsupported file type: {file_path}")
                return
        
        logger.info(f"[DriveSend] Detected new file: {file_path}")
        self.file_queue.put(file_path)

    def start_queue_processor(self):
        def process_queue():
            global _drive_service
            
            # Initialize Drive service once
            if _drive_service is None:
                try:
                    from .gdrive_auth_manager import get_drive_service
                    _drive_service = get_drive_service(self.auth_method)
                    logger.info("[DriveSend] Drive service initialized")
                except Exception as e:
                    logger.error(f"[DriveSend] Failed to initialize Drive service: {e}")
                    return
            
            while not _stop_queue_processor:
                if not self.file_queue.empty():
                    file_path = self.file_queue.get()
                    if wait_for_complete_write(file_path):
                        try:
                            result = upload_file(
                                file_path,
                                folder_id=self.folder_id,
                                service=_drive_service
                            )
                            if result.get('success'):
                                logger.info(f"[DriveSend] ✓ Uploaded: {os.path.basename(file_path)}")
                                # Delete .enc file after successful upload if requested
                                if self.delete_enc and file_path.lower().endswith('.enc'):
                                    os.remove(file_path)
                                    logger.info(f"[DriveSend] Deleted .enc file after upload: {file_path}")
                            else:
                                logger.error(f"[DriveSend] Upload failed: {result.get('error')}")
                                self.file_queue.put(file_path)  # Requeue on failure
                        except Exception as e:
                            logger.error(f"[DriveSend] Upload failed: {e}")
                            self.file_queue.put(file_path)  # Requeue on failure
                time.sleep(0.1)  # Small delay to avoid CPU overload
            logger.info("[DriveSend] Upload queue processor stopped")

        threading.Thread(target=process_queue, daemon=True).start()


def start_monitoring(watch_folder, folder_id, auth_method='oauth', enable_encryption=False, 
                     delete_enc=False, subfolder_monitor=True):
    """
    Start monitoring a folder for new files to upload.
    
    Args:
        watch_folder: Directory to monitor
        folder_id: Google Drive folder ID
        auth_method: 'oauth' or 'service_account'
        enable_encryption: If True, only upload .enc files (created by separate encrypt watcher)
        delete_enc: Delete .enc files after successful upload
        subfolder_monitor: Monitor subfolders recursively
    """
    global watcher_observer, watcher_handler, encryption_enabled, _stop_queue_processor, _drive_service
    
    encryption_enabled = enable_encryption
    _stop_queue_processor = False  # Reset stop signal when starting
    _drive_service = None  # Reset service to force re-auth

    if watcher_observer and watcher_observer.is_alive():
        logger.info("[DriveSend] Restarting monitor to update settings.")
        watcher_observer.stop()
        watcher_observer.join()

    watcher_handler = NewFileHandler(folder_id, auth_method, delete_enc)
    watcher_observer = Observer()
    watcher_observer.schedule(watcher_handler, watch_folder, recursive=subfolder_monitor)
    watcher_observer.start()

    logger.info(f"[DriveSend] Now watching: {watch_folder} (Subfolder_Monitor: {'Yes' if subfolder_monitor else 'No'})")
    logger.info(f"[DriveSend] Upload target: Google Drive folder {folder_id}")
    logger.info(f"[DriveSend] Encryption mode: {'Yes - uploading .enc files only' if encryption_enabled else 'No - uploading images directly'}")

    def keep_alive():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            watcher_observer.stop()
        watcher_observer.join()

    threading.Thread(target=keep_alive, daemon=True).start()


def stop_monitoring():
    """Stop the upload monitor."""
    global watcher_observer, _drive_service
    
    stop_queue_processor()
    
    if watcher_observer and watcher_observer.is_alive():
        watcher_observer.stop()
        watcher_observer.join()
        logger.info("[DriveSend] Upload monitor stopped")
    
    _drive_service = None  # Clear cached service


# Legacy function names for compatibility
def start_monitor(**kwargs):
    """Alias for start_monitoring."""
    # Map new param names to old function
    watch_dir = kwargs.pop('watch_dir', kwargs.pop('watch_folder', None))
    recursive = kwargs.pop('recursive', kwargs.pop('subfolder_monitor', True))
    post_delete_enc = kwargs.pop('post_delete_enc', kwargs.pop('delete_enc', False))
    
    return start_monitoring(
        watch_folder=watch_dir,
        subfolder_monitor=recursive,
        delete_enc=post_delete_enc,
        **kwargs
    )


def stop_monitor():
    """Alias for stop_monitoring."""
    return stop_monitoring()


def get_monitor():
    """Get the current watcher observer."""
    global watcher_observer
    
    class MonitorWrapper:
        def is_running(self):
            return watcher_observer and watcher_observer.is_alive()
    
    return MonitorWrapper()
