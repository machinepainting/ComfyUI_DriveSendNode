"""
ComfyUI DriveSend Node
Automatic Google Drive uploads with optional encryption
"""

from .drivesend_setup_node import NODE_CLASS_MAPPINGS as SETUP_MAPPINGS
from .drivesend_setup_node import NODE_DISPLAY_NAME_MAPPINGS as SETUP_DISPLAY_MAPPINGS
from .drivesend_uploader_node import NODE_CLASS_MAPPINGS as UPLOADER_MAPPINGS
from .drivesend_uploader_node import NODE_DISPLAY_NAME_MAPPINGS as UPLOADER_DISPLAY_MAPPINGS

# Merge mappings
NODE_CLASS_MAPPINGS = {**SETUP_MAPPINGS, **UPLOADER_MAPPINGS}
NODE_DISPLAY_NAME_MAPPINGS = {**SETUP_DISPLAY_MAPPINGS, **UPLOADER_DISPLAY_MAPPINGS}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

# Load environment variables from .env file if present
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"[DriveSend] Loaded environment from {env_path}")
