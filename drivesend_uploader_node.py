"""
DriveSend AutoUploader Node
Monitors output folder and uploads new files to Google Drive
"""

import os
from pathlib import Path

from .monitor_output import start_monitor, stop_monitor, get_monitor


class DriveSendAutoUploaderNode:
    """ComfyUI node for automatic Google Drive uploads."""
    
    CATEGORY = "DriveSend"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "auth_method": (["oauth", "service_account"], {"default": "oauth"}),
                "run_process": ("BOOLEAN", {"default": True}),
                "enable_encryption": ("BOOLEAN", {"default": False}),
                "Subfolder_Monitor": ("BOOLEAN", {"default": True}),
                "Post_Delete_Enc": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "watch_folder": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Folder to monitor (leave blank for ComfyUI output folder)"
                }),
                "folder_id": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Google Drive folder ID (uses env var if blank)"
                }),
            }
        }
    
    def run(self, auth_method, run_process, enable_encryption, Subfolder_Monitor, 
            Post_Delete_Enc, watch_folder="", folder_id=""):
        """
        Start or stop the Google Drive upload monitor.
        
        Args:
            auth_method: 'oauth' or 'service_account'
            run_process: True to start, False to stop
            enable_encryption: Encrypt files before upload
            Subfolder_Monitor: Monitor subfolders recursively
            Post_Delete_Enc: Delete .enc files after upload
            watch_folder: Folder to monitor (default: ComfyUI output)
            folder_id: Google Drive folder ID (default: from env var)
        """
        
        # Stop if requested
        if not run_process:
            monitor = get_monitor()
            if monitor and monitor.is_running():
                stop_monitor()
                return ("⏹️ DriveSend monitor stopped.",)
            else:
                return ("ℹ️ Monitor was not running.",)
        
        # Determine watch folder
        if watch_folder:
            watch_path = Path(watch_folder)
        else:
            # Default to ComfyUI output folder
            # Try common locations
            possible_paths = [
                Path("/workspace/ComfyUI/output"),  # RunPod
                Path("./output"),  # Relative
                Path(__file__).parent.parent.parent / "output",  # Relative to node
            ]
            
            watch_path = None
            for p in possible_paths:
                if p.exists():
                    watch_path = p
                    break
            
            if not watch_path:
                return ("❌ Error: Could not find ComfyUI output folder. Please specify watch_folder.",)
        
        if not watch_path.exists():
            return (f"❌ Error: Watch folder does not exist: {watch_path}",)
        
        # Get folder ID from parameter or environment
        effective_folder_id = folder_id or os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
        if not effective_folder_id:
            return (
                "❌ Error: No folder_id provided.\n\n"
                "Either:\n"
                "1. Set the folder_id parameter in this node\n"
                "2. Set GOOGLE_DRIVE_FOLDER_ID environment variable\n"
                "3. Run the DriveSend Setup node first",
            )
        
        # Check for encryption key if encryption is enabled
        if enable_encryption:
            enc_key = os.environ.get('comfyui_encryption_key')
            if not enc_key:
                return (
                    "❌ Error: Encryption enabled but no key found.\n\n"
                    "Set comfyui_encryption_key environment variable\n"
                    "or run DriveSend Setup with encryption enabled.",
                )
        
        # Validate auth method requirements
        if auth_method == 'oauth':
            client_id = os.environ.get('GOOGLE_CLIENT_ID')
            client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
            refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')
            
            if not all([client_id, client_secret, refresh_token]):
                # Check for token.json file as fallback
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
                    "1. Set GOOGLE_SERVICE_ACCOUNT_JSON environment variable (base64)\n"
                    "2. Place service_account.json in the node folder\n\n"
                    "⚠️ NOTE: Service accounts only work with Google Workspace (paid).\n"
                    "For personal Gmail, use OAuth instead.",
                )
        
        # Start the monitor
        try:
            monitor = start_monitor(
                watch_dir=str(watch_path),
                folder_id=effective_folder_id,
                recursive=Subfolder_Monitor,
                enable_encryption=enable_encryption,
                post_delete_enc=Post_Delete_Enc,
                auth_method=auth_method
            )
            
            status_lines = [
                "✅ DriveSend monitor started!",
                "",
                f"📁 Watching: {watch_path}",
                f"☁️ Uploading to: Google Drive folder {effective_folder_id[:20]}...",
                f"🔐 Auth method: {auth_method}",
                f"🔒 Encryption: {'Enabled' if enable_encryption else 'Disabled'}",
                f"📂 Subfolder monitoring: {'Enabled' if Subfolder_Monitor else 'Disabled'}",
                "",
                "New files will be uploaded automatically.",
                "Set run_process to False to stop.",
            ]
            
            return ("\n".join(status_lines),)
            
        except Exception as e:
            return (f"❌ Error starting monitor: {e}",)


# Node registration
NODE_CLASS_MAPPINGS = {
    "DriveSendAutoUploader": DriveSendAutoUploaderNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendAutoUploader": "DriveSend AutoUploader"
}
