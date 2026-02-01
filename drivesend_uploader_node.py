"""
DriveSend AutoUploader Node
Monitors ComfyUI output directory and uploads files to Google Drive
"""

import os
from pathlib import Path

from .monitor_output import start_monitor, stop_monitor, get_monitor


# Default output directory
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"


class DriveSendAutoUploaderNode:
    """
    ComfyUI node for automatic Google Drive uploads with optional encryption.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "watch_directory": ("STRING", {
                    "default": str(DEFAULT_OUTPUT_DIR),
                    "multiline": False,
                    "placeholder": "Directory to monitor for new files"
                }),
                "auth_method": (["service_account", "oauth"],),
                "run_process": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "folder_id": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Google Drive Folder ID (uses env var if blank)"
                }),
                "owner_email": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Your Gmail address (required for service account)"
                }),
                "enable_encryption": ("BOOLEAN", {"default": False}),
                "Post_Delete_Enc": ("BOOLEAN", {"default": False}),
                "Subfolder_Monitor": ("BOOLEAN", {"default": True}),
                "any_input": ("*", {}),  # Passthrough for workflow chaining
            }
        }
    
    RETURN_TYPES = ("STRING", "*")
    RETURN_NAMES = ("status", "passthrough")
    FUNCTION = "run"
    CATEGORY = "DriveSend"
    
    def run(
        self,
        watch_directory,
        auth_method,
        run_process,
        folder_id="",
        owner_email="",
        enable_encryption=False,
        Post_Delete_Enc=False,
        Subfolder_Monitor=True,
        any_input=None
    ):
        status_lines = []
        
        # Get current monitor state
        current_monitor = get_monitor()
        
        if run_process:
            # Start or restart monitor
            if current_monitor and current_monitor.is_running():
                stop_monitor()
                status_lines.append("Stopped existing monitor")
            
            # Validate watch directory
            watch_path = Path(watch_directory)
            if not watch_path.exists():
                try:
                    watch_path.mkdir(parents=True, exist_ok=True)
                    status_lines.append(f"Created watch directory: {watch_path}")
                except Exception as e:
                    status_lines.append(f"Error: Could not create watch directory: {e}")
                    return ("\n".join(status_lines), any_input)
            
            # Get owner email from field or environment
            effective_owner_email = owner_email if owner_email else os.environ.get('GOOGLE_OWNER_EMAIL', '')
            
            # Warn if using service account without owner email
            if auth_method == 'service_account' and not effective_owner_email:
                status_lines.append("⚠ WARNING: No owner_email set!")
                status_lines.append("  Service accounts have 0 GB storage quota.")
                status_lines.append("  Set owner_email to your Gmail or set GOOGLE_OWNER_EMAIL env var.")
                status_lines.append("")
            
            # Set owner email in environment for upload module
            if effective_owner_email:
                os.environ['GOOGLE_OWNER_EMAIL'] = effective_owner_email
            
            # Start monitor
            try:
                monitor = start_monitor(
                    watch_dir=str(watch_path),
                    folder_id=folder_id if folder_id else None,
                    recursive=Subfolder_Monitor,
                    enable_encryption=enable_encryption,
                    post_delete_enc=Post_Delete_Enc,
                    auth_method=auth_method,
                    owner_email=effective_owner_email
                )
                
                status_lines.append(f"✓ Monitor started")
                status_lines.append(f"  Directory: {watch_path}")
                status_lines.append(f"  Auth: {auth_method}")
                status_lines.append(f"  Recursive: {Subfolder_Monitor}")
                status_lines.append(f"  Encryption: {enable_encryption}")
                
                if effective_owner_email:
                    status_lines.append(f"  Owner Email: {effective_owner_email}")
                
                if folder_id:
                    status_lines.append(f"  Folder ID: {folder_id}")
                else:
                    env_folder = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
                    if env_folder:
                        status_lines.append(f"  Folder ID: {env_folder} (from env)")
                    else:
                        status_lines.append("  Folder ID: Root (no folder specified)")
            
            except Exception as e:
                status_lines.append(f"Error starting monitor: {e}")
        
        else:
            # Stop monitor
            if current_monitor and current_monitor.is_running():
                stop_monitor()
                status_lines.append("✓ Monitor stopped")
            else:
                status_lines.append("Monitor not running")
        
        status = "\n".join(status_lines)
        return (status, any_input)


# Node registration
NODE_CLASS_MAPPINGS = {
    "DriveSendAutoUploaderNode": DriveSendAutoUploaderNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendAutoUploaderNode": "DriveSend AutoUploader"
}
