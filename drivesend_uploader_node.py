# drivesend_uploader_node.py
# DriveSend AutoUploader Node - monitors output folder and uploads to Google Drive

import os
import threading
import logging
import time
from pathlib import Path
from dotenv import dotenv_values, load_dotenv
from watchdog.observers import Observer
from .monitor_output import start_monitoring, stop_monitoring, watcher_observer, stop_queue_processor
from .encrypt_file import FileEncryptHandler, ENCRYPT_EXTENSIONS, get_encryption_key
from .encrypt_file import stop_queue_processor as stop_encrypt_queue_processor
from .encrypt_file import reset_queue_processor as reset_encrypt_queue_processor
from .safe_paths import resolve_safe_watch_folder

# logging is configured centrally in __init__.py via a FileHandler on
# the root logger. Use a named logger here so records carry the module
# name into drivesend.log.
logger = logging.getLogger(__name__)

NODE_DIR = Path(__file__).parent
encrypt_observer = None


# ---------------------------------------------------------------------------
# Secure persistence for non-credential uploader settings
# ---------------------------------------------------------------------------
# The uploader persists watch_folder, auth_method, and behavior toggles
# to .env so the next session can defaults them in INPUT_TYPES. This is
# unconditional (not gated by COMFYUI_DRIVESEND_ALLOW_SETUP) because
# none of these values are credentials. Race-free 0o600 open keeps the
# file from being world/group-readable in the open->chmod window.

_UPLOADER_KEYS = {
    "DRIVESEND_WATCH_FOLDER",
    "DRIVESEND_AUTH_METHOD",
    "ENABLE_ENCRYPTION",
    "POST_DELETE_ENC",
    "SUBFOLDER_MONITOR",
    "RUN_PROCESS",
}


def _persist_uploader_settings(updates):
    """Merge non-credential uploader settings into .env with 0o600."""
    env_path = NODE_DIR / ".env"
    existing = {}
    if env_path.exists():
        existing = dict(dotenv_values(env_path))
    merged = dict(existing)
    for k, v in updates.items():
        merged[k] = str(v)
    if merged:
        fd = os.open(str(env_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            for k, v in merged.items():
                f.write(f"{k}={v}\n")
        load_dotenv(env_path, override=True)


class DriveSendAutoUploaderNode:
    """ComfyUI node for automatic Google Drive uploads."""

    CATEGORY = "DriveSend"
    FUNCTION = "start"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        # Default-from-.env so the user does not have to retype settings
        # across sessions.
        env_path = NODE_DIR / ".env"
        cfg = {}
        if env_path.exists():
            cfg = dict(dotenv_values(env_path))

        default_watch = cfg.get("DRIVESEND_WATCH_FOLDER") or os.path.join(os.getcwd(), "output")
        default_auth = cfg.get("DRIVESEND_AUTH_METHOD", "oauth")
        if default_auth not in ("oauth", "service_account"):
            default_auth = "oauth"
        default_encrypt = cfg.get("ENABLE_ENCRYPTION", "True").lower() == "true"
        default_delete_enc = cfg.get("POST_DELETE_ENC", "False").lower() == "true"
        default_subfolder = cfg.get("SUBFOLDER_MONITOR", "True").lower() == "true"
        default_run = cfg.get("RUN_PROCESS", "True").lower() == "true"

        return {
            "required": {
                "watch_folder": ("STRING", {"default": default_watch}),
                "auth_method": (["oauth", "service_account"], {"default": default_auth}),
                "enable_encryption": ("BOOLEAN", {"default": default_encrypt}),
                "Post_Delete_Enc": ("BOOLEAN", {"default": default_delete_enc}),
                "Subfolder_Monitor": ("BOOLEAN", {"default": default_subfolder}),
                "run_process": ("BOOLEAN", {"default": default_run, "label": "Run Process"}),
            }
        }

    def start(self, watch_folder, auth_method, enable_encryption, Post_Delete_Enc,
              Subfolder_Monitor, run_process):
        """
        Start or stop the Google Drive upload monitor.

        When encryption is enabled, two watchers run:
        1. Encrypt watcher: creates .enc copies of new images (preserves originals)
        2. Upload watcher: uploads .enc files to Google Drive
        """
        global encrypt_observer

        logger.info(
            "Starting DriveSend AutoUploader: watch_folder=%s, auth_method=%s, "
            "encryption=%s, Post_Delete_Enc=%s, Subfolder_Monitor=%s, run_process=%s",
            watch_folder, auth_method, enable_encryption, Post_Delete_Enc,
            Subfolder_Monitor, run_process,
        )

        # ----- Stop path -----
        if not run_process:
            logger.info("Stopping DriveSend AutoUploader monitoring")

            if watcher_observer and watcher_observer.is_alive():
                stop_monitoring()
                logger.info("Upload watcher stopped")

            if encrypt_observer and encrypt_observer.is_alive():
                encrypt_observer.stop()
                encrypt_observer.join()
                logger.info("Encryption watcher stopped")

            stop_queue_processor()
            stop_encrypt_queue_processor()

            stop_message = (
                "=====================================================================\n"
                "🚙🛑 DriveSend - AutoUploader - STOPPED\n"
                "=====================================================================\n"
                f"All monitoring, uploading, and encryption processes for {watch_folder} have been stopped.\n"
                "Set 'run_process' to True and run the node again to resume.\n"
                "====================================================================="
            )
            print(stop_message)
            logger.info(stop_message)
            return (f"All monitoring stopped for {watch_folder}",)

        # ----- Validate watch_folder against the allowed roots -----
        try:
            watch_folder = resolve_safe_watch_folder(watch_folder)
        except ValueError as e:
            logger.error(str(e))
            return (f"Error: {e}",)

        watch_path = Path(watch_folder)
        if not watch_path.exists():
            logger.error(f"Watch folder does not exist: {watch_folder}")
            return (f"Error: Watch folder does not exist: {watch_folder}",)
        if not watch_path.is_dir():
            logger.error(f"Watch folder is not a directory: {watch_folder}")
            return (f"Error: Watch folder is not a directory: {watch_folder}",)

        # ----- folder_id required -----
        folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            return (
                "Error: GOOGLE_DRIVE_FOLDER_ID not set.\n\n"
                "Run the DriveSend Setup node first, then:\n"
                "  1. Copy credentials to RunPod Secrets / your secrets manager\n"
                "  2. Restart your pod / container so the env vars load",
            )

        # ----- Auth method requirements -----
        if auth_method == "oauth":
            client_id = os.environ.get("GOOGLE_CLIENT_ID")
            client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
            refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")

            if not all([client_id, client_secret, refresh_token]):
                token_file = NODE_DIR / "token.json"
                if not token_file.exists():
                    return (
                        "Error: OAuth credentials not found.\n\n"
                        "Set these environment variables:\n"
                        "  - GOOGLE_CLIENT_ID\n"
                        "  - GOOGLE_CLIENT_SECRET\n"
                        "  - GOOGLE_REFRESH_TOKEN\n\n"
                        "Or run DriveSend Setup to authorize.",
                    )

        elif auth_method == "service_account":
            sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
            sa_file = NODE_DIR / "service_account.json"

            if not sa_json and not sa_file.exists():
                return (
                    "Error: Service account credentials not found.\n\n"
                    "Either:\n"
                    "  1. Set GOOGLE_SERVICE_ACCOUNT_JSON environment variable\n"
                    "  2. Place service_account.json in the node folder\n\n"
                    "Note: service accounts only work with Google Workspace.\n"
                    "For personal Gmail, use OAuth instead.",
                )

        # ----- Encryption key requirement -----
        if enable_encryption:
            enc_key = get_encryption_key()
            if not enc_key:
                logger.error("Encryption enabled but no encryption key found")
                return (
                    "Error: Encryption enabled but no key found.\n\n"
                    "Set COMFYUI_ENCRYPTION_KEY environment variable\n"
                    "or run DriveSend Setup with encryption enabled.",
                )

        # ----- Persist (non-credential) uploader settings -----
        _persist_uploader_settings({
            "DRIVESEND_WATCH_FOLDER": watch_folder,
            "DRIVESEND_AUTH_METHOD": auth_method,
            "ENABLE_ENCRYPTION": enable_encryption,
            "POST_DELETE_ENC": Post_Delete_Enc,
            "SUBFOLDER_MONITOR": Subfolder_Monitor,
            "RUN_PROCESS": run_process,
        })

        # ----- Reset queue processors before starting -----
        from .monitor_output import reset_queue_processor as reset_upload_queue
        reset_upload_queue()
        reset_encrypt_queue_processor()

        # ----- Start upload monitor -----
        try:
            start_monitoring(
                watch_folder=watch_folder,
                folder_id=folder_id,
                auth_method=auth_method,
                enable_encryption=enable_encryption,
                delete_enc=Post_Delete_Enc,
                subfolder_monitor=Subfolder_Monitor,
            )
        except Exception as e:
            logger.error(f"Failed to start upload monitor: {e}")
            return (f"Error starting upload monitor: {e}",)

        # ----- Start encryption watcher if enabled -----
        if enable_encryption:
            if encrypt_observer and encrypt_observer.is_alive():
                encrypt_observer.stop()
                encrypt_observer.join()

            encrypt_handler = FileEncryptHandler(watch_folder, False, Subfolder_Monitor)
            encrypt_observer = Observer()
            encrypt_observer.schedule(encrypt_handler, watch_folder, recursive=Subfolder_Monitor)
            encrypt_observer.start()
            logger.info(f"Starting encryption monitor for {watch_folder}")

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

        # ----- Status message (no credentials) -----
        status_lines = [
            "DriveSend AutoUploader started.",
            "",
            f"Watching: {watch_folder}",
            f"Drive folder: {folder_id[:20]}...",
            f"Auth method: {auth_method}",
            f"Encryption: {'Enabled (creating .enc copies)' if enable_encryption else 'Disabled'}",
            f"Subfolder monitoring: {'Enabled' if Subfolder_Monitor else 'Disabled'}",
            f"Delete .enc after upload: {'Yes' if Post_Delete_Enc else 'No'}",
        ]

        if enable_encryption:
            status_lines.extend([
                "",
                "Note: original files are preserved for ComfyUI naming.",
                "You must manually delete files from the output folder.",
            ])

        status_lines.extend([
            "",
            "New files will be uploaded automatically.",
            "Set run_process to False to stop.",
        ])

        banner = "\n".join(status_lines)
        print(banner)
        logger.info(banner)
        return (banner,)


NODE_CLASS_MAPPINGS = {
    "DriveSendAutoUploader": DriveSendAutoUploaderNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendAutoUploader": "🚙📤 DriveSend - AutoUploader"
}
