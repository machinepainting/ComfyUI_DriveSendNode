# encrypt_file.py
# DriveSend encryption module - creates .enc copies of files (preserves originals for ComfyUI)

import os
import time
import logging
from queue import Queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from cryptography.fernet import Fernet
import threading

# logging is configured centrally in __init__.py via a FileHandler on
# the root logger.
logger = logging.getLogger(__name__)

ENCRYPT_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.avi', '.mov')
_stop_queue_processor = False  # Stop signal for queue processor


def get_encryption_key():
    """
    Get the encryption key from environment variable.
    Checks multiple possible key names for compatibility.
    
    Key retrieval order:
      - COMFYUI_ENCRYPTION_KEY (uppercase - preferred)
      - comfyui_encryption_key (lowercase - legacy)
      - DROPSEND_ENCRYPTION_KEY
      - DRIVESEND_ENCRYPTION_KEY
      - RUNPOD_SECRET_COMFYUI_ENCRYPTION_KEY (RunPod fallback)
    
    Returns:
        str: The encryption key, or None if not set
    """
    return (
        os.environ.get('COMFYUI_ENCRYPTION_KEY') or
        os.environ.get('comfyui_encryption_key') or
        os.environ.get('DROPSEND_ENCRYPTION_KEY') or
        os.environ.get('DRIVESEND_ENCRYPTION_KEY') or
        os.environ.get('RUNPOD_SECRET_COMFYUI_ENCRYPTION_KEY')
    )


def stop_queue_processor():
    """Signal the queue processor to stop."""
    global _stop_queue_processor
    _stop_queue_processor = True
    logger.info("[DriveSend] Signaled encryption queue processor to stop")


def reset_queue_processor():
    """Reset the stop signal for queue processor."""
    global _stop_queue_processor
    _stop_queue_processor = False


class FileEncryptHandler(FileSystemEventHandler):
    """
    Watches for new image/video files and creates encrypted .enc copies.
    Original files are preserved so ComfyUI maintains its sequential naming.
    """
    
    def __init__(self, watch_dir="/workspace/ComfyUI/output", delete_original=False, subfolder_monitor=True):
        self.watch_dir = watch_dir
        self.delete_original = delete_original
        self.subfolder_monitor = subfolder_monitor
        self.file_queue = Queue()
        self.start_queue_processor()

    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(ENCRYPT_EXTENSIONS):
            return
        from .safe_paths import is_safe_event_path
        if not is_safe_event_path(event.src_path):
            logger.warning(f"[DriveSend] Skipping unsafe path (symlink or outside output root): {event.src_path}")
            return
        logger.info(f"[DriveSend] Detected new file to encrypt: {event.src_path}")
        self.file_queue.put(event.src_path)

    def start_queue_processor(self):
        def process_queue():
            while not _stop_queue_processor:
                if not self.file_queue.empty():
                    file_path = self.file_queue.get()
                    try:
                        time.sleep(1)  # Ensure file is fully written
                        size1 = os.path.getsize(file_path)
                        time.sleep(0.1)
                        size2 = os.path.getsize(file_path)
                        if size1 != size2:
                            logger.warning(f"[DriveSend] File {file_path} still writing, requeueing...")
                            self.file_queue.put(file_path)
                            continue

                        ENCRYPT_KEY = get_encryption_key()
                        if not ENCRYPT_KEY:
                            logger.error("[DriveSend] Encryption key not found. Set COMFYUI_ENCRYPTION_KEY environment variable.")
                            continue
                        fernet = Fernet(ENCRYPT_KEY.encode())

                        with open(file_path, 'rb') as f:
                            file_data = f.read()

                        encrypted_data = fernet.encrypt(file_data)
                        enc_path = file_path + '.enc'
                        with open(enc_path, 'wb') as f:
                            f.write(encrypted_data)
                        logger.info(f"[DriveSend] Created encrypted file: {enc_path}")

                        # Original file is kept so ComfyUI maintains sequential naming
                        # User must manually delete originals from output folder
                    except Exception as e:
                        logger.error(f"[DriveSend] Error encrypting {file_path}: {e}")
                time.sleep(0.1)  # Small delay to avoid CPU overload
            logger.info("[DriveSend] Encryption queue processor stopped")

        threading.Thread(target=process_queue, daemon=True).start()


