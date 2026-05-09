"""
ComfyUI DriveSend Node
Automatic Google Drive uploads with optional encryption
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Attach a FileHandler to the root logger so every child logger in this
# plugin (logging.getLogger(__name__) in our modules) gets its records
# persisted to drivesend.log alongside ComfyUI's own stdout. We do NOT
# use logging.basicConfig() here: ComfyUI's main.py configures the root
# logger before our package is imported, and basicConfig is a no-op
# once any caller has already configured root.
#
# Race-free perms: pre-create the file with 0o600 via os.open() before
# FileHandler can create it under the default umask (typically 0o644).
# A follow-up chmod tightens perms if the file already existed with
# looser bits.
_LOG_PATH = os.path.join(os.path.dirname(__file__), "drivesend.log")
try:
    _fd = os.open(_LOG_PATH, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    os.close(_fd)
except OSError:
    pass
_root_logger = logging.getLogger()
if not any(
    isinstance(h, logging.FileHandler)
    and getattr(h, "baseFilename", "") == _LOG_PATH
    for h in _root_logger.handlers
):
    try:
        _fh = logging.FileHandler(_LOG_PATH)
        _fh.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )
        _root_logger.addHandler(_fh)
        if _root_logger.level == logging.NOTSET or _root_logger.level > logging.INFO:
            _root_logger.setLevel(logging.INFO)
    except OSError:
        pass
try:
    os.chmod(_LOG_PATH, 0o600)
except OSError:
    pass

# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------
# Load .env from the plugin directory at import time so GOOGLE_CLIENT_ID,
# GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN, GOOGLE_DRIVE_FOLDER_ID,
# COMFYUI_ENCRYPTION_KEY, and the uploader's persisted settings are
# visible in os.environ before any node runs. override=False is
# intentional. Host-injected env vars (RunPod secrets, Docker env,
# systemd EnvironmentFile) take precedence over the plugin's local .env.
_PLUGIN_ENV = Path(__file__).parent / ".env"
if _PLUGIN_ENV.exists():
    load_dotenv(_PLUGIN_ENV, override=False)

from .drivesend_setup_node import NODE_CLASS_MAPPINGS as SETUP_MAPPINGS
from .drivesend_setup_node import NODE_DISPLAY_NAME_MAPPINGS as SETUP_DISPLAY_MAPPINGS
from .drivesend_uploader_node import NODE_CLASS_MAPPINGS as UPLOADER_MAPPINGS
from .drivesend_uploader_node import NODE_DISPLAY_NAME_MAPPINGS as UPLOADER_DISPLAY_MAPPINGS

NODE_CLASS_MAPPINGS = {**SETUP_MAPPINGS, **UPLOADER_MAPPINGS}
NODE_DISPLAY_NAME_MAPPINGS = {**SETUP_DISPLAY_MAPPINGS, **UPLOADER_DISPLAY_MAPPINGS}

# Define web directory for JavaScript extensions
WEB_DIRECTORY = "./web"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
