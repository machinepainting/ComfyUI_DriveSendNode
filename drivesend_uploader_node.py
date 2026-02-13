# drivesend_uploader_node.py
# DriveSend AutoUploader Node - monitors output folder and uploads to Google Drive

import os
import threading
import logging
import time
from pathlib import Path
from watchdog.observers import Observer
from .monitor_output import start_monitoring, stop_monitoring, watcher_observer, stop_queue_processor
from .encrypt_file import FileEncryptHandler, ENCRYPT_EXTENSIONS, get_encryption_key
from .encrypt_file import stop_queue_processor as stop_encrypt_queue_processor
from .encrypt_file import reset_queue_processor as reset_encrypt_queue_processor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('drivesend.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Define encrypt_observer at module level
encrypt_observer = None


class DriveSendAutoUploaderNode:
    """ComfyUI node for automatic Google Drive uploads."""
    
    CATEGORY = "DriveSend"
    FUNCTION = "start"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        # Try to get default watch folder
        default_watch = os.path.join(os.getcwd(), "output")
        
        return {
            "required": {
                "watch_folder": ("STRING", {"default": default_watch}),
                "auth_method": (["oauth", "service_account"], {"default": "oauth"}),
                "enable_encryption": ("BOOLEAN", {"default": True}),
                "Post_Delete_Enc": ("BOOLEAN", {"default": False}),
                "Subfolder_Monitor": ("BOOLEAN", {"default": True}),
                "run_process": ("BOOLEAN", {"default": True, "label": "Run Process"}),
            }
        }
    
    def start(self, watch_folder, auth_method, enable_encryption, Post_Delete_Enc, 
              Subfolder_Monitor, run_process):
        """
        Start or stop the Google Drive upload monitor.
        
        When encryption is enabled, two watchers run:
        1. Encrypt watcher: Creates .enc copies of new images (preserves originals)
        2. Upload watcher: Uploads .enc files to Google Drive
        
        This preserves original files so ComfyUI maintains sequential naming.
        """
        global encrypt_observer
        
        logger.info(f"[DriveSend] Starting AutoUploader: watch_folder={watch_folder}, "
                   f"auth_method={auth_method}, encryption={enable_encryption}, "
                   f"Post_Delete_Enc={Post_Delete_Enc}, Subfolder_Monitor={Subfolder_Monitor}, "
                   f"run_process={run_process}")

        # Handle stopping the process
        if not run_process:
            logger.info("[DriveSend] Stopping AutoUploader monitoring")
            
            # Stop upload watcher
            if watcher_observer and watcher_observer.is_alive():
                stop_monitoring()
                logger.info("[DriveSend] Upload watcher stopped")
            
            # Stop encryption watcher
            if encrypt_observer and encrypt_observer.is_alive():
                encrypt_observer.stop()
                encrypt_observer.join()
                logger.info("[DriveSend] Encryption watcher stopped")
            
            # Stop queue processors
            stop_queue_processor()
            stop_encrypt_queue_processor()
            
            stop_message = f"""
=====================================================================
🚙🛑 DriveSend - AutoUploader - STOPPED
=====================================================================
All monitoring, uploading, and encryption processes for {watch_folder} have been stopped.
Set 'run_process' to True and run the node again to resume.
=====================================================================
"""
            print(stop_message)
            return (f"All monitoring stopped for {watch_folder}",)

        # Validate watch_folder
        watch_path = Path(watch_folder)
        if not watch_path.exists():
            logger.error(f"[DriveSend] Watch folder does not exist: {watch_folder}")
            return (f"❌ Error: Watch folder does not exist: {watch_folder}",)
        if not watch_path.is_dir():
            logger.error(f"[DriveSend] Watch folder is not a directory: {watch_folder}")
            return (f"❌ Error: Watch folder is not a directory: {watch_folder}",)

        # Get folder ID from environment
        folder_id = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
        if not folder_id:
            return (
                "❌ Error: GOOGLE_DRIVE_FOLDER_ID not set.\n\n"
                "Run the DriveSend Setup node first, then:\n"
                "1. Copy credentials to RunPod Secrets\n"
                "2. Restart pod with environment variables loaded",
            )

        # Validate auth method requirements
        if auth_method == 'oauth':
            client_id = os.environ.get('GOOGLE_CLIENT_ID')
            client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
            refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')
            
            if not all([client_id, client_secret, refresh_token]):
                token_file = Path(__file__).parent / 'token.json'
                if not token_file.exists():
                    return (
                        "❌ Error: OAuth credentials not found.\n\n"
                        "Set these environment variables:\n"
                        "- GOOGLE_CLIENT_ID\n"
                        "- GOOGLE_CLIENT_SECRET\n"
                        "- GOOGLE_REFRESH_TOKEN\n\n"
                        "Or run DriveSend Setup to authorize.",
                    )
        
        elif auth_method == 'service_account':
            sa_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
            sa_file = Path(__file__).parent / 'service_account.json'
            
            if not sa_json and not sa_file.exists():
                return (
                    "❌ Error: Service account credentials not found.\n\n"
                    "Either:\n"
                    "1. Set GOOGLE_SERVICE_ACCOUNT_JSON environment variable\n"
                    "2. Place service_account.json in the node folder\n\n"
                    "⚠️ NOTE: Service accounts only work with Google Workspace.\n"
                    "For personal Gmail, use OAuth instead.",
                )

        # Validate encryption key if enabled
        if enable_encryption:
            enc_key = get_encryption_key()
            if not enc_key:
                logger.error("[DriveSend] Encryption enabled but no encryption key found")
                return (
                    "❌ Error: Encryption enabled but no key found.\n\n"
                    "Set COMFYUI_ENCRYPTION_KEY environment variable\n"
                    "or run DriveSend Setup with encryption enabled.",
                )

        # Reset queue processors before starting
        from .monitor_output import reset_queue_processor as reset_upload_queue
        reset_upload_queue()
        reset_encrypt_queue_processor()

        # Start upload monitor
        try:
            start_monitoring(
                watch_folder=watch_folder,
                folder_id=folder_id,
                auth_method=auth_method,
                enable_encryption=enable_encryption,
                delete_enc=Post_Delete_Enc,
                subfolder_monitor=Subfolder_Monitor
            )
        except Exception as e:
            logger.error(f"[DriveSend] Failed to start upload monitor: {e}")
            return (f"❌ Error starting upload monitor: {e}",)

        # Start encryption watcher if enabled (separate from upload watcher)
        if enable_encryption:
            # Stop existing encrypt observer if running
            if encrypt_observer and encrypt_observer.is_alive():
                encrypt_observer.stop()
                encrypt_observer.join()
            
            encrypt_handler = FileEncryptHandler(watch_folder, False, Subfolder_Monitor)
            encrypt_observer = Observer()
            encrypt_observer.schedule(encrypt_handler, watch_folder, recursive=Subfolder_Monitor)
            encrypt_observer.start()
            logger.info(f"[DriveSend] Starting encryption monitor for {watch_folder}")

            def keep_encrypt_alive():
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    if encrypt_observer:
                        encrypt_observer.stop()
                if encrypt_observer:
                    encrypt_observer.join()

            threading.Thread(target=keep_encrypt_alive, daemon=True).start()

        # Build status message
        status_lines = [
            "✅ DriveSend AutoUploader started!",
            "",
            f"📁 Watching: {watch_folder}",
            f"☁️ Uploading to: Google Drive folder {folder_id[:20]}...",
            f"🔐 Auth method: {auth_method}",
            f"🔒 Encryption: {'Enabled (creating .enc copies)' if enable_encryption else 'Disabled'}",
            f"📂 Subfolder monitoring: {'Enabled' if Subfolder_Monitor else 'Disabled'}",
            f"🗑️ Delete .enc after upload: {'Yes' if Post_Delete_Enc else 'No'}",
            "",
        ]
        
        if enable_encryption:
            status_lines.extend([
                "⚠️ Note: Original files are preserved for ComfyUI naming.",
                "   You must manually delete files from output folder.",
                "",
            ])
        
        status_lines.extend([
            "New files will be uploaded automatically.",
            "Set run_process to False to stop.",
        ])

        return ("\n".join(status_lines),)


# Node registration
NODE_CLASS_MAPPINGS = {
    "DriveSendAutoUploader": DriveSendAutoUploaderNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendAutoUploader": "🚙📤 DriveSend - AutoUploader"
}
