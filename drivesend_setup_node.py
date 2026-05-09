"""
DriveSend Setup Node
Handles Google Drive API authentication setup for both OAuth and Service Account methods.

Architecture: this node has NO credential-bearing inputs. client_id,
client_secret, and auth_code are entered only via a browser-only modal
launched from the JS extension's "Set credentials..." button. The modal
POSTs values directly to the same-origin route /drivesend/setup/stash
and clears its inputs. setup() consumes the per-session stash entry on
the next Queue. This keeps every credential out of PromptServer.history
(served on the unauthenticated /history endpoint), workflow JSON, PNG
metadata, ComfyUI's localStorage auto-save, and copy-pasted nodes.
"""

import os
import re
import time
import json
import base64
import threading
import logging
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import dotenv_values, load_dotenv


logger = logging.getLogger(__name__)
NODE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Out-of-band secret transport
# ---------------------------------------------------------------------------
# ComfyUI persists every queued prompt's input JSON in
# PromptServer.history, served on the unauthenticated /history endpoint.
# If the Setup Node accepted client_id/client_secret/auth_code as
# workflow inputs, those values would be visible there for the lifetime
# of the history entry. To close that path: the JS extension shows a
# browser-only modal, POSTs the secret values to /drivesend/setup/stash
# (this module's route), clears the inputs, then lets the queue go
# through. The prompt JSON ComfyUI stores in history therefore has no
# credential fields. setup() pulls the real values from the stash
# (one-shot, keyed by originating client_id).
#
# Entries auto-expire after _SETUP_STASH_TTL_SEC so a stash POST that's
# never consumed (user closed the tab between Save and Queue, etc.)
# does not sit in memory.
# ---------------------------------------------------------------------------

_setup_secret_stash = {}
_setup_secret_lock = threading.Lock()
_SETUP_STASH_TTL_SEC = 60
_SETUP_STASH_MAX_ENTRIES = 32
_CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# Per-IP rate limit on the stash route, defense in depth against
# stash-spam attempts to evict a legitimate user's entry.
_STASH_RL_WINDOW_SEC = 10
_STASH_RL_MAX_PER_WINDOW = 30
_stash_rl_state = {}
_stash_rl_lock = threading.Lock()


def _stash_rl_check(remote_ip):
    if not remote_ip:
        return True
    now = time.time()
    cutoff = now - _STASH_RL_WINDOW_SEC
    with _stash_rl_lock:
        if len(_stash_rl_state) > 256:
            stale = [ip for ip, hits in _stash_rl_state.items() if not hits or hits[-1] < cutoff]
            for ip in stale:
                _stash_rl_state.pop(ip, None)
        hits = _stash_rl_state.setdefault(remote_ip, [])
        i = 0
        while i < len(hits) and hits[i] < cutoff:
            i += 1
        if i:
            del hits[:i]
        if len(hits) >= _STASH_RL_MAX_PER_WINDOW:
            return False
        hits.append(now)
        return True


def _stash_prune_expired_locked():
    now = time.time()
    expired = [k for k, (ts, _v) in _setup_secret_stash.items() if now - ts > _SETUP_STASH_TTL_SEC]
    for k in expired:
        _setup_secret_stash.pop(k, None)


def _stash_set(client_id, payload):
    with _setup_secret_lock:
        _stash_prune_expired_locked()
        if len(_setup_secret_stash) >= _SETUP_STASH_MAX_ENTRIES and client_id not in _setup_secret_stash:
            oldest_key = min(_setup_secret_stash, key=lambda k: _setup_secret_stash[k][0])
            _setup_secret_stash.pop(oldest_key, None)
        _setup_secret_stash[client_id] = (time.time(), payload)


def _stash_consume(client_id):
    with _setup_secret_lock:
        _stash_prune_expired_locked()
        entry = _setup_secret_stash.pop(client_id, None)
    if entry is None:
        return None
    _ts, payload = entry
    return payload


def _register_stash_route_once():
    """Register the /drivesend/setup/stash POST handler on PromptServer.

    Idempotent. If PromptServer is not ready yet, registration is silently
    skipped and the Setup Node will surface a clear error when the user
    tries to save credentials.
    """
    if getattr(_register_stash_route_once, "_registered", False):
        return
    try:
        from server import PromptServer
        from aiohttp import web
    except Exception:
        return
    instance = getattr(PromptServer, "instance", None)
    if instance is None or not hasattr(instance, "routes"):
        return

    @instance.routes.post("/drivesend/setup/stash")
    async def _stash_handler(request):
        # Same-origin enforcement. Without this, a malicious page in
        # another tab could attempt a CSRF POST against
        # http://127.0.0.1:8188.
        origin = request.headers.get("Origin", "")
        if origin:
            try:
                from urllib.parse import urlparse
                origin_host = urlparse(origin).netloc
            except Exception:
                origin_host = ""
            if not origin_host or origin_host != request.host:
                return web.json_response({"error": "cross-origin denied"}, status=403)

        if request.content_type and request.content_type != "application/json":
            return web.json_response(
                {"error": "Content-Type must be application/json"},
                status=415,
            )

        remote_ip = request.headers.get("X-Forwarded-For", request.remote or "").split(",")[0].strip()
        if not _stash_rl_check(remote_ip):
            return web.json_response({"error": "rate limit"}, status=429)

        if request.content_length is not None and request.content_length > 32 * 1024:
            return web.json_response({"error": "payload too large"}, status=413)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        client_id_field = data.get("client_id") if isinstance(data, dict) else None
        if not client_id_field or not isinstance(client_id_field, str) or not _CLIENT_ID_PATTERN.match(client_id_field):
            return web.json_response({"error": "client_id required"}, status=400)

        # Authenticate by liveness: only accept stash writes for a
        # client_id that currently has an active WebSocket connection
        # to this PromptServer instance.
        try:
            sockets = getattr(instance, "sockets", None)
            if not sockets or client_id_field not in sockets:
                return web.json_response({"error": "client_id has no active WebSocket"}, status=403)
        except Exception:
            return web.json_response({"error": "internal"}, status=500)

        payload = {
            "google_client_id": str(data.get("google_client_id") or ""),
            "google_client_secret": str(data.get("google_client_secret") or ""),
            "auth_code": str(data.get("auth_code") or ""),
            "service_account_json": str(data.get("service_account_json") or ""),
        }
        if not any(payload.values()):
            return web.json_response({"ok": True, "stashed": False})
        _stash_set(client_id_field, payload)
        return web.json_response({"ok": True, "stashed": True})

    _register_stash_route_once._registered = True
    print("[DriveSend Setup] Registered /drivesend/setup/stash route (out-of-band secret transport)")


_register_stash_route_once()


# ---------------------------------------------------------------------------
# Opt-in gate
# ---------------------------------------------------------------------------
# Workflow inputs to the Setup Node can come from any caller that can
# submit a workflow to ComfyUI. On a network-reachable host that means a
# remote attacker can wipe credentials or overwrite the stored Google
# Drive app to redirect uploads to their own account. We require the
# operator to opt in by setting this env var on the host before the
# Setup Node performs any state-changing action.
_SETUP_OPT_IN_VAR = "COMFYUI_DRIVESEND_ALLOW_SETUP"
_SETUP_OPT_IN_HELP = (
    f"Setup is disabled. To allow this node to write or clear credentials, "
    f"set {_SETUP_OPT_IN_VAR}=1 in the host environment before starting "
    f"ComfyUI, or provision GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / "
    f"GOOGLE_REFRESH_TOKEN directly via environment variables (e.g. RunPod "
    f"secrets). This guard prevents remote workflow submitters from "
    f"hijacking or wiping your Google Drive connection."
)


def _setup_opt_in_enabled():
    return os.getenv(_SETUP_OPT_IN_VAR, "").strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Redaction helpers for the post-setup banner
# ---------------------------------------------------------------------------
_SECRET_FIELDS = {
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "COMFYUI_ENCRYPTION_KEY",
}


def _redact(value, visible_tail=4):
    if not value:
        return ""
    if len(value) <= visible_tail:
        return "*" * len(value)
    return "*" * (len(value) - visible_tail) + value[-visible_tail:]


def _redact_kv_line(line):
    name, sep, value = line.partition("=")
    if sep and name in _SECRET_FIELDS:
        return f"{name}={_redact(value)}"
    return line


# ---------------------------------------------------------------------------
# The Setup Node
# ---------------------------------------------------------------------------

class DriveSendSetupNode:
    """Setup node for configuring Google Drive authentication."""

    CATEGORY = "DriveSend"
    FUNCTION = "setup"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        # Architecture: NO credential-bearing inputs. google_client_id,
        # google_client_secret, auth_code, and the service-account JSON
        # body all live exclusively in the per-session stash populated
        # by the browser modal.
        return {
            "required": {
                "auth_method": (["oauth", "service_account"], {"default": "oauth"}),
                "folder_id": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Google Drive folder ID from URL (the part after /folders/)"
                }),
                "storage_method": (["display_only", "env_file"], {
                    "label": "Credential Storage Method",
                    "default": "display_only"
                }),
                "encryption_key_method": (["off", "display_only", "save_to_env"], {
                    "label": "Encryption Key Method",
                    "default": "off"
                }),
            },
            "optional": {
                "reconnect": ("BOOLEAN", {
                    "label": "Reset stored credentials",
                    "default": False
                }),
            }
        }

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # Force re-execution on every Queue. setup() is intentionally
        # side-effecting, and the input dict here does not reflect the
        # actual work (the real driver is the out-of-band stash entry).
        return float("NaN")

    def setup(self, auth_method, folder_id, storage_method, encryption_key_method, reconnect=False):
        try:
            print(f"[DriveSend Setup] Called: auth_method={auth_method}, "
                  f"reconnect={reconnect}, storage_method={storage_method}, "
                  f"encryption_key_method={encryption_key_method}")

            # Pull stash for this client (browser-only entry).
            google_client_id = None
            google_client_secret = None
            auth_code = None
            service_account_json = None
            sid = None
            try:
                from server import PromptServer
                sid = getattr(PromptServer.instance, "client_id", None)
                if sid:
                    stashed = _stash_consume(sid)
                    if stashed:
                        google_client_id = stashed.get("google_client_id") or None
                        google_client_secret = stashed.get("google_client_secret") or None
                        auth_code = stashed.get("auth_code") or None
                        service_account_json = stashed.get("service_account_json") or None
                        print("[DriveSend Setup] Loaded secrets from out-of-band stash")
            except Exception as e:
                print(f"[DriveSend Setup] Warning: could not consume secret stash: {e}")

            # ----- Reconnect (clear all stored credentials) -----
            if reconnect:
                if not _setup_opt_in_enabled():
                    message = "Reconnect refused: " + _SETUP_OPT_IN_HELP
                    print(f"[DriveSend Setup] {message}")
                    return {"ui": {"text": [message]}, "result": (message,)}

                print("[DriveSend Setup] Reconnect requested - clearing all credentials")

                env_path = NODE_DIR / ".env"
                token_path = NODE_DIR / "token.json"

                if env_path.exists():
                    print(f"[DriveSend Setup] Removing .env file: {env_path}")
                    try:
                        os.remove(env_path)
                    except OSError as e:
                        print(f"[DriveSend Setup] Warning: could not remove .env: {e}")

                if token_path.exists():
                    print(f"[DriveSend Setup] Removing token.json: {token_path}")
                    try:
                        os.remove(token_path)
                    except OSError as e:
                        print(f"[DriveSend Setup] Warning: could not remove token.json: {e}")

                # Clear in-process os.environ so subsequent runs do not
                # short-circuit on the previously-loaded values.
                for key in (
                    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
                    "GOOGLE_SERVICE_ACCOUNT_JSON",
                ):
                    if key in os.environ:
                        os.environ.pop(key, None)
                        print(f"[DriveSend Setup] Cleared {key} from process environment")

                # WebSocket notification, sid-targeted only (refuse to
                # broadcast on sid=None).
                try:
                    from server import PromptServer
                    notify_sid = getattr(PromptServer.instance, "client_id", None)
                    if not notify_sid:
                        print(
                            "[DriveSend Setup] Skipping reconnect-complete "
                            "broadcast: prompt has no client_id (CLI "
                            "submission?). Submit from the ComfyUI web UI "
                            "to receive the refresh notification."
                        )
                    else:
                        PromptServer.instance.send_sync(
                            "drivesend_reconnect_complete",
                            {
                                "type": "drivesend_reconnect_complete",
                                "success": True,
                                "client_id": notify_sid,
                                "message": "Credentials cleared. ComfyUI will refresh to show auth fields",
                            },
                            notify_sid,
                        )
                        print("[DriveSend Setup] Sent WebSocket notification for reconnect completion")
                except Exception as e:
                    print(f"[DriveSend Setup] Warning: Could not send WebSocket notification: {e}")

                message = "Google Drive credentials cleared."
                return {"ui": {"text": [message]}, "result": (message,)}

            # ----- folder_id is required -----
            if not folder_id or not str(folder_id).strip():
                message = "Error: folder_id is required. Get it from your Google Drive folder URL (the part after /folders/)."
                print(f"[DriveSend Setup] {message}")
                return {"ui": {"text": [message]}, "result": (message,)}

            from .safe_paths import validate_drive_folder_id
            try:
                folder_id = validate_drive_folder_id(folder_id)
            except ValueError as e:
                message = f"Error: {e}"
                print(f"[DriveSend Setup] {message}")
                return {"ui": {"text": [message]}, "result": (message,)}

            # ----- env_vars short-circuit (already configured) -----
            #
            # If credentials are already provisioned in the host environment
            # (RunPod secrets, Docker env, etc.), there's nothing to do.
            if auth_method == "oauth":
                env_vars_set = all([
                    os.getenv("GOOGLE_CLIENT_ID"),
                    os.getenv("GOOGLE_CLIENT_SECRET"),
                    os.getenv("GOOGLE_REFRESH_TOKEN"),
                ])
                if env_vars_set and not auth_code and not google_client_id:
                    # Persist the folder_id only (non-sensitive). Use the
                    # secure write helper.
                    _persist_env_writes([("GOOGLE_DRIVE_FOLDER_ID", folder_id)])
                    message = (
                        "Google Drive credentials already configured via host environment. "
                        "Folder ID saved. Ready to upload."
                    )
                    print(f"[DriveSend Setup] {message}")
                    return {"ui": {"text": [message]}, "result": (message,)}

            elif auth_method == "service_account":
                if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") and not service_account_json:
                    _persist_env_writes([("GOOGLE_DRIVE_FOLDER_ID", folder_id)])
                    message = (
                        "Service account already configured via host environment. "
                        "Folder ID saved. Ready to upload."
                    )
                    print(f"[DriveSend Setup] {message}")
                    return {"ui": {"text": [message]}, "result": (message,)}

            # ----- Anything below this line writes credential state -----
            if not _setup_opt_in_enabled():
                message = _SETUP_OPT_IN_HELP
                print(f"[DriveSend Setup] {message}")
                return {"ui": {"text": [message]}, "result": (message,)}

            # ----- Generate or reuse encryption key -----
            encryption_key = None
            if encryption_key_method != "off":
                existing_key = (
                    os.environ.get("COMFYUI_ENCRYPTION_KEY")
                    or os.environ.get("comfyui_encryption_key")
                    or os.environ.get("DROPSEND_ENCRYPTION_KEY")
                    or os.environ.get("DRIVESEND_ENCRYPTION_KEY")
                    or os.environ.get("RUNPOD_SECRET_COMFYUI_ENCRYPTION_KEY")
                )
                if existing_key:
                    encryption_key = existing_key
                    print("[DriveSend Setup] Using existing encryption key from environment")
                else:
                    encryption_key = Fernet.generate_key().decode("utf-8")
                    print("[DriveSend Setup] Generated new encryption key")

            # ----- Service Account flow -----
            if auth_method == "service_account":
                return self._handle_service_account(
                    folder_id, storage_method, encryption_key_method,
                    encryption_key, service_account_json,
                )

            # ----- OAuth flow -----
            return self._handle_oauth(
                folder_id, storage_method, encryption_key_method,
                encryption_key, google_client_id, google_client_secret,
                auth_code, sid,
            )

        except Exception as e:
            logger.exception("[DriveSend Setup] Unexpected error")
            message = f"Setup failed with an unexpected error: {e}"
            return {"ui": {"text": [message]}, "result": (message,)}

    # -----------------------------------------------------------------
    # OAuth path
    # -----------------------------------------------------------------

    def _handle_oauth(self, folder_id, storage_method, encryption_key_method,
                      encryption_key, google_client_id, google_client_secret,
                      auth_code, sid):
        if not google_client_id or not google_client_secret:
            # No client_id / client_secret in stash. Tell the user to
            # click "Set credentials..." on the node.
            message = (
                "OAuth requires google_client_id and google_client_secret.\n\n"
                "Click 'Set credentials...' on this node, paste your OAuth "
                "Client ID and Client Secret from Google Cloud Console, leave "
                "the auth code blank, click Save, then click Queue.\n\n"
                "Get a Client ID and Client Secret here:\n"
                "  Google Cloud Console -> APIs & Services -> Credentials\n"
                "  Create OAuth 2.0 Client ID (Desktop app)"
            )
            print(f"[DriveSend Setup] {message}")
            return {"ui": {"text": [message]}, "result": (message,)}

        from .gdrive_auth_manager import get_oauth_credentials_for_setup

        if not auth_code:
            # First run: generate the auth URL and ask the browser to
            # auto-open the entry modal so the user can paste the auth
            # code on the next round.
            result = get_oauth_credentials_for_setup(google_client_id, google_client_secret)
            if "auth_url" not in result:
                err = result.get("error", "Unknown error")
                message = f"Error generating auth URL: {err}"
                print(f"[DriveSend Setup] {message}")
                return {"ui": {"text": [message]}, "result": (message,)}

            auth_url = result["auth_url"]

            # The auth URL contains your OAuth client_id, which Google
            # treats as a public identifier (it's in every OAuth URL
            # ever issued by your app). Safe to print.
            print()
            print("=" * 80)
            print("DRIVESEND - GOOGLE DRIVE AUTHORIZATION REQUIRED")
            print("=" * 80)
            print("Open this URL in your browser to authorize:")
            print()
            print(f"  {auth_url}")
            print()
            print("After authorizing, Google will display an authorization code.")
            print("Paste it into the credentials modal that auto-opens in your")
            print("browser, then click Save and re-queue this workflow.")
            print("=" * 80)
            print()

            # Auto-trigger the entry modal in the originating browser.
            try:
                from server import PromptServer
                if sid:
                    PromptServer.instance.send_sync(
                        "drivesend_credentials_needed",
                        {"client_id": sid, "stage": "auth_code"},
                        sid,
                    )
                    print("[DriveSend Setup] Sent credentials-needed event to browser")
            except Exception as e:
                print(f"[DriveSend Setup] Warning: could not send credentials-needed event: {e}")

            message = (
                "Google OAuth Ready!\n\n"
                "Click the link below (also printed in the ComfyUI terminal):\n\n"
                f"{auth_url}\n\n"
                "Authorize, copy the code Google shows you, then paste your "
                "Client ID, Client Secret, and Auth Code in the modal that "
                "auto-opens. Click Save, then click Queue."
            )
            return {"ui": {"text": [message]}, "result": (message,)}

        # Second run: exchange the auth code.
        result = get_oauth_credentials_for_setup(
            google_client_id, google_client_secret, auth_code
        )
        if "error" in result:
            message = (
                f"OAuth exchange failed: {result['error']}\n\n"
                "The auth code may have expired or already been used.\n"
                "Click 'Set credentials...' again to enter a fresh one, "
                "or rerun the node with no auth code to regenerate the URL."
            )
            print(f"[DriveSend Setup] {message}")
            return {"ui": {"text": [message]}, "result": (message,)}

        creds = result.get("credentials", {})
        refresh_token = creds.get("refresh_token")
        if not refresh_token:
            message = (
                "OAuth exchange returned no refresh token. This usually means "
                "the user did not see the consent screen (already authorized). "
                "Revoke access at https://myaccount.google.com/permissions and "
                "rerun setup."
            )
            print(f"[DriveSend Setup] {message}")
            return {"ui": {"text": [message]}, "result": (message,)}

        return self._deliver_credentials(
            auth_method="oauth",
            folder_id=folder_id,
            storage_method=storage_method,
            encryption_key_method=encryption_key_method,
            encryption_key=encryption_key,
            sid=sid,
            credentials_payload=[
                ("GOOGLE_CLIENT_ID", google_client_id),
                ("GOOGLE_CLIENT_SECRET", google_client_secret),
                ("GOOGLE_REFRESH_TOKEN", refresh_token),
            ],
        )

    # -----------------------------------------------------------------
    # Service Account path
    # -----------------------------------------------------------------

    def _handle_service_account(self, folder_id, storage_method, encryption_key_method,
                                encryption_key, service_account_json):
        # Three sources of service account JSON, checked in order:
        #   1. Stashed by the browser modal (paste into the dedicated field)
        #   2. service_account.json in the plugin directory (legacy)
        #   3. nothing -> tell the user how to provide it
        sa_data = None
        sa_source = None

        if service_account_json:
            try:
                sa_data = json.loads(service_account_json)
                sa_source = "modal"
            except json.JSONDecodeError as e:
                message = f"Service account JSON could not be parsed: {e}"
                print(f"[DriveSend Setup] {message}")
                return {"ui": {"text": [message]}, "result": (message,)}

        if sa_data is None:
            sa_file = NODE_DIR / "service_account.json"
            if sa_file.exists():
                try:
                    with open(sa_file, "r") as f:
                        sa_data = json.load(f)
                    sa_source = "file"
                except (OSError, json.JSONDecodeError) as e:
                    message = f"Could not read service_account.json: {e}"
                    print(f"[DriveSend Setup] {message}")
                    return {"ui": {"text": [message]}, "result": (message,)}

        if sa_data is None:
            message = (
                "No service account configured. Two options:\n\n"
                "(a) Click 'Set credentials...' on this node and paste the "
                "JSON contents of your service-account key file into the "
                "Service Account JSON field.\n\n"
                "(b) Place the file at "
                "ComfyUI/custom_nodes/ComfyUI_DriveSendNode/service_account.json\n\n"
                "Note: service accounts only work with Google Workspace (paid). "
                "For personal Gmail accounts, use OAuth instead."
            )
            print(f"[DriveSend Setup] {message}")
            return {"ui": {"text": [message]}, "result": (message,)}

        sa_email = sa_data.get("client_email", "unknown")
        sa_json_b64 = base64.b64encode(json.dumps(sa_data).encode()).decode()
        print(f"[DriveSend Setup] Service account loaded ({sa_source}): {sa_email}")

        return self._deliver_credentials(
            auth_method="service_account",
            folder_id=folder_id,
            storage_method=storage_method,
            encryption_key_method=encryption_key_method,
            encryption_key=encryption_key,
            sid=None,
            credentials_payload=[("GOOGLE_SERVICE_ACCOUNT_JSON", sa_json_b64)],
            extra_message=(
                f"Service account email: {sa_email}\n"
                f"Make sure your Drive folder is shared with that email "
                f"(otherwise uploads will fail with a 'file not found' error)."
            ),
        )

    # -----------------------------------------------------------------
    # Credential delivery (env_file or display_only)
    # -----------------------------------------------------------------

    def _deliver_credentials(self, auth_method, folder_id, storage_method,
                             encryption_key_method, encryption_key, sid,
                             credentials_payload, extra_message=None):
        # folder_id is non-sensitive and always persisted to .env so
        # the AutoUploader can find it.
        env_writes = [("GOOGLE_DRIVE_FOLDER_ID", folder_id)]
        ws_payload = {}

        if storage_method == "env_file":
            env_writes.extend(credentials_payload)
        else:
            for name, value in credentials_payload:
                ws_payload[name] = value

        if encryption_key_method == "save_to_env" and encryption_key:
            env_writes.append(("COMFYUI_ENCRYPTION_KEY", encryption_key))
        elif encryption_key_method == "display_only" and encryption_key:
            ws_payload["COMFYUI_ENCRYPTION_KEY"] = encryption_key

        # Persist .env. Race-free 0o600 open. Merges with existing
        # values so re-running setup does not wipe non-setup keys
        # (uploader settings, etc.).
        env_path = _persist_env_writes(env_writes, scrub_setup_keys=True)

        # OAuth: also write token.json for local CLI use, with secure
        # permissions. Only if storage_method is env_file (otherwise
        # display_only's whole point is "no secrets on disk").
        if auth_method == "oauth" and storage_method == "env_file":
            creds_dict = {name: value for name, value in credentials_payload}
            if all(k in creds_dict for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")):
                _write_token_json(
                    client_id=creds_dict["GOOGLE_CLIENT_ID"],
                    client_secret=creds_dict["GOOGLE_CLIENT_SECRET"],
                    refresh_token=creds_dict["GOOGLE_REFRESH_TOKEN"],
                )

        # WebSocket delivery for display_only (sid-targeted, never broadcast).
        ws_delivered = False
        ws_delivery_error = None
        if ws_payload:
            try:
                from server import PromptServer
                deliver_sid = sid or getattr(PromptServer.instance, "client_id", None)
                if not deliver_sid:
                    ws_delivery_error = (
                        "prompt has no client_id (typical for CLI/curl/SDK "
                        "submissions). display_only delivery requires "
                        "submitting from the ComfyUI web browser so a "
                        "client_id is attached to the prompt."
                    )
                    print(
                        "[DriveSend Setup] Refusing to deliver credentials: "
                        "prompt has no client_id. Sending to sid=None would "
                        "broadcast to every connected browser. Submit from "
                        "the ComfyUI web UI instead."
                    )
                else:
                    PromptServer.instance.send_sync(
                        "drivesend_credentials_ready",
                        {"credentials": dict(ws_payload), "client_id": deliver_sid},
                        deliver_sid,
                    )
                    ws_delivered = True
            except Exception as e:
                ws_delivery_error = str(e)
                print(f"[DriveSend Setup] WebSocket delivery failed: {e}")

        # Build status message. Contains NO credential values.
        message_parts = ["Google Drive connected."]
        if extra_message:
            message_parts.append(extra_message)

        if ws_payload and ws_delivered:
            message_parts.append(
                "Next steps:\n"
                "  1. Copy each value from the DriveSend Credentials panel "
                "to a safe place (password manager, secure note).\n"
                "  2. Add them to your platform's secrets configuration "
                "(RunPod Secrets, Docker env, systemd EnvironmentFile).\n"
                "  3. Restart your pod / container so the new secrets are "
                "visible to the ComfyUI process.\n"
                "  4. On the restarted pod, remove this Setup node from "
                "your workflow and run the 'DriveSend - AutoUploader' node."
            )
        elif ws_payload and not ws_delivered:
            message_parts.append(
                f"Browser delivery refused: {ws_delivery_error}\n\n"
                f"What to do:\n"
                f"  - Cloud / RunPod / hosted ComfyUI:  Submit this workflow "
                f"from your web browser (not via curl / API / SDK). The "
                f"browser's WebSocket connection attaches a client_id "
                f"automatically. display_only never writes credentials to "
                f"the pod's filesystem.\n"
                f"  - Local install only:  switch storage_method to "
                f"'env_file' and rerun if you don't mind credentials in a "
                f"0600 .env file on disk."
            )
        elif env_writes:
            message_parts.append(
                "You can remove this Setup node from your workflow and run "
                "the 'DriveSend - AutoUploader' node."
            )

        message = "\n\n".join(message_parts)

        # Console banner. Confirmation only, values redacted.
        print("\n" + "=" * 80)
        print("DRIVESEND SETUP COMPLETE (values redacted in console)")
        if env_writes:
            print(f"Wrote to file: {env_path}")
            for name, value in env_writes:
                print("  " + _redact_kv_line(f"{name}={value}"))
        if ws_payload:
            label = "Sent to browser (display_only):"
            print(label)
            for name in ws_payload:
                # Field names only for display_only. The values rode the
                # WS payload, never stdout.
                print(f"  {name}=<delivered to browser>")
        print("=" * 80 + "\n")

        return {"ui": {"text": [message]}, "result": (message,)}


# ---------------------------------------------------------------------------
# Persistence helpers (race-free, 0o600)
# ---------------------------------------------------------------------------

# Keys the Setup Node "owns". On a setup re-run that does NOT write a
# given key, it gets scrubbed from .env so old values don't linger when
# switching env_file -> display_only. GOOGLE_DRIVE_FOLDER_ID is owned by
# the AutoUploader, so it's not in this set.
_SETUP_KEYS = {
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "COMFYUI_ENCRYPTION_KEY",
}


def _persist_env_writes(env_writes, scrub_setup_keys=False):
    """Write (key, value) pairs to .env with 0o600 permissions.

    Merges with existing .env contents so non-setup keys (uploader
    settings, etc.) survive re-runs unchanged. If scrub_setup_keys is
    True, setup-owned keys NOT being rewritten by this run are dropped
    from disk (covers the env_file -> display_only switch).
    """
    env_path = NODE_DIR / ".env"

    existing = {}
    if env_path.exists():
        existing = dict(dotenv_values(env_path))

    if scrub_setup_keys:
        existing = {k: v for k, v in existing.items() if k not in _SETUP_KEYS}

    merged = dict(existing)
    for name, value in env_writes:
        merged[name] = value

    if merged:
        fd = os.open(str(env_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            for k, v in merged.items():
                f.write(f"{k}={v}\n")
        # Load freshly written values into os.environ so the
        # AutoUploader can use them in the same session.
        load_dotenv(env_path, override=True)
    elif env_path.exists():
        os.remove(env_path)

    return env_path


def _write_token_json(client_id, client_secret, refresh_token):
    """Write token.json with 0o600 permissions for local CLI use."""
    token_path = NODE_DIR / "token.json"
    token_data = {
        "token": None,
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": ["https://www.googleapis.com/auth/drive.file"],
    }
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token_data, f, indent=2)


# ---------------------------------------------------------------------------
# Node registration
# ---------------------------------------------------------------------------
NODE_CLASS_MAPPINGS = {
    "DriveSendSetup": DriveSendSetupNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DriveSendSetup": "🚙⚙️ DriveSend - Setup Node"
}
