"""
Security regression tests.

These tests pin behavior that, if it regresses silently, would
re-introduce a previously-fixed vulnerability. They run without a real
ComfyUI process by stubbing the `server.PromptServer` module.

Run from the repo root:
    python -m pytest tests/

Or directly:
    python -m unittest tests.test_security
"""

import importlib
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
PARENT_OF_REPO = REPO_ROOT.parent


# Install ghost modules for the google-auth / googleapiclient packages
# BEFORE the package under test imports them. This lets the test run
# without those packages installed in the environment.
def _install_lib_ghosts():
    """Install fake modules for runtime deps so the package can import
    without google-auth / googleapiclient / watchdog installed."""
    for name in [
        "google", "google.oauth2", "google.auth", "google.auth.transport",
        "googleapiclient", "google_auth_oauthlib",
        "watchdog", "watchdog.observers", "watchdog.events",
    ]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules["google.oauth2.credentials"] = types.ModuleType("google.oauth2.credentials")
    sys.modules["google.oauth2.credentials"].Credentials = mock.MagicMock()
    sys.modules["google.oauth2.service_account"] = types.ModuleType("google.oauth2.service_account")
    sys.modules["google.oauth2.service_account"].Credentials = mock.MagicMock()
    sys.modules["google.auth.transport.requests"] = types.ModuleType("google.auth.transport.requests")
    sys.modules["google.auth.transport.requests"].Request = mock.MagicMock()
    sys.modules["googleapiclient.discovery"] = types.ModuleType("googleapiclient.discovery")
    sys.modules["googleapiclient.discovery"].build = mock.MagicMock()
    sys.modules["googleapiclient.http"] = types.ModuleType("googleapiclient.http")
    sys.modules["googleapiclient.http"].MediaFileUpload = mock.MagicMock()
    sys.modules["googleapiclient.errors"] = types.ModuleType("googleapiclient.errors")
    sys.modules["googleapiclient.errors"].HttpError = type("HttpError", (Exception,), {})
    sys.modules["google_auth_oauthlib.flow"] = types.ModuleType("google_auth_oauthlib.flow")
    sys.modules["google_auth_oauthlib.flow"].Flow = mock.MagicMock()
    sys.modules["google_auth_oauthlib.flow"].InstalledAppFlow = mock.MagicMock()
    sys.modules["watchdog.observers"].Observer = mock.MagicMock()
    sys.modules["watchdog.events"].FileSystemEventHandler = type("FileSystemEventHandler", (object,), {})


_install_lib_ghosts()


def _install_fake_promptserver(client_id, sockets=None):
    """Install a stubbed `server` module so the Setup Node can import it.

    Returns a `Mock` for `PromptServer.instance.send_sync` so tests can
    assert on calls.
    """
    fake_module = types.ModuleType("server")
    fake_instance = mock.MagicMock()
    fake_instance.client_id = client_id
    fake_instance.sockets = sockets if sockets is not None else {}
    fake_instance.send_sync = mock.MagicMock()
    fake_module.PromptServer = mock.MagicMock()
    fake_module.PromptServer.instance = fake_instance
    sys.modules["server"] = fake_module
    return fake_instance.send_sync


def _install_fake_gdrive_auth_manager(oauth_response=None):
    """Install a fake gdrive_auth_manager module so tests do not require
    the google-auth packages to be installed.
    """
    fake = types.ModuleType("gdrive_auth_manager")
    fake.get_oauth_credentials_for_setup = mock.MagicMock(
        return_value=oauth_response or {"credentials": {
            "client_id": "stub.apps.googleusercontent.com",
            "client_secret": "GOCSPX-stub",
            "refresh_token": "1//stub",
            "token": "ya29.stub",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": ["https://www.googleapis.com/auth/drive.file"],
        }}
    )
    fake.get_drive_service = mock.MagicMock()
    fake.get_folder_id = mock.MagicMock(return_value=None)
    fake.get_oauth_credentials = mock.MagicMock(return_value=None)
    fake.get_service_account_credentials = mock.MagicMock(return_value=None)
    fake.refresh_access_token = mock.MagicMock()
    sys.modules["gdrive_auth_manager"] = fake
    sys.modules["ComfyUI_DriveSendNode.gdrive_auth_manager"] = fake
    return fake


def _import_setup_node_fresh():
    """Re-import the setup node module as part of the ComfyUI_DriveSendNode
    package so relative imports (e.g. `from .gdrive_auth_manager import ...`)
    resolve correctly.
    """
    pkg_name = "ComfyUI_DriveSendNode"
    mod_name = f"{pkg_name}.drivesend_setup_node"
    # Strip cached entries so import-time route registration sees the
    # current `server` mock.
    for cached in list(sys.modules):
        if cached == mod_name or cached.startswith(mod_name + "."):
            sys.modules.pop(cached, None)
    sys.modules.pop(mod_name, None)
    if str(PARENT_OF_REPO) not in sys.path:
        sys.path.insert(0, str(PARENT_OF_REPO))
    return importlib.import_module(mod_name)


class TestWebSocketBroadcastGuard(unittest.TestCase):
    """Setup must NEVER call send_sync(..., sid=None) for credential events.

    ComfyUI's send_sync with sid=None broadcasts to every connected
    WebSocket client. When PromptServer.instance.client_id is None
    (typical for curl/SDK submissions that omit client_id), credentials
    delivered via display_only would otherwise leak to any concurrent
    listener on /ws.
    """

    def test_no_send_sync_when_client_id_is_none(self):
        send_sync = _install_fake_promptserver(client_id=None)
        setup_mod = _import_setup_node_fresh()

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(setup_mod, "NODE_DIR", Path(tmp)):
                with mock.patch.dict(os.environ, {"COMFYUI_DRIVESEND_ALLOW_SETUP": "1"}, clear=False):
                    node = setup_mod.DriveSendSetupNode()
                    # Force a state-changing path: stash an OAuth attempt
                    # with a usable client_id+secret+auth_code, then call
                    # setup() with no real client_id present.
                    setup_mod._stash_set("any-client", {
                        "google_client_id": "stub.apps.googleusercontent.com",
                        "google_client_secret": "GOCSPX-stub",
                        "auth_code": "code-stub",
                        "service_account_json": "",
                    })
                    # The fake PromptServer reports client_id=None, so
                    # _stash_consume(None) returns nothing. The OAuth
                    # branch will still proceed but find no inputs and
                    # return a "click Set credentials..." message
                    # without touching send_sync.
                    with mock.patch(
                        "ComfyUI_DriveSendNode.gdrive_auth_manager.get_oauth_credentials_for_setup",
                        return_value={"credentials": {
                            "client_id": "stub.apps.googleusercontent.com",
                            "client_secret": "GOCSPX-stub",
                            "refresh_token": "1//stub",
                            "token": "ya29.stub",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "scopes": ["https://www.googleapis.com/auth/drive.file"],
                        }},
                    ):
                        node.setup(
                            auth_method="oauth",
                            folder_id="stub_folder_id",
                            storage_method="display_only",
                            encryption_key_method="off",
                            reconnect=False,
                        )

        # Assert: every send_sync call was scoped to a non-None sid.
        for call in send_sync.call_args_list:
            args, kwargs = call
            sid = args[2] if len(args) >= 3 else kwargs.get("sid")
            self.assertIsNotNone(
                sid,
                f"send_sync was called with sid=None: {call}. "
                "This would broadcast to every connected WebSocket client.",
            )

    def test_send_sync_called_with_real_sid(self):
        """Sanity check: when a real client_id is present, send_sync IS called
        and is scoped to that sid."""
        send_sync = _install_fake_promptserver(
            client_id="real-sid", sockets={"real-sid": object()}
        )
        setup_mod = _import_setup_node_fresh()

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(setup_mod, "NODE_DIR", Path(tmp)):
                with mock.patch.dict(os.environ, {"COMFYUI_DRIVESEND_ALLOW_SETUP": "1"}, clear=False):
                    setup_mod._stash_set("real-sid", {
                        "google_client_id": "stub.apps.googleusercontent.com",
                        "google_client_secret": "GOCSPX-stub",
                        "auth_code": "code-stub",
                        "service_account_json": "",
                    })
                    with mock.patch(
                        "ComfyUI_DriveSendNode.gdrive_auth_manager.get_oauth_credentials_for_setup",
                        return_value={"credentials": {
                            "client_id": "stub.apps.googleusercontent.com",
                            "client_secret": "GOCSPX-stub",
                            "refresh_token": "1//stub",
                            "token": "ya29.stub",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "scopes": ["https://www.googleapis.com/auth/drive.file"],
                        }},
                    ):
                        node = setup_mod.DriveSendSetupNode()
                        node.setup(
                            auth_method="oauth",
                            folder_id="stub_folder_id",
                            storage_method="display_only",
                            encryption_key_method="off",
                            reconnect=False,
                        )

        # Expect at least one send_sync delivering the credentials_ready
        # event scoped to real-sid.
        creds_calls = [
            c for c in send_sync.call_args_list
            if c.args and c.args[0] == "drivesend_credentials_ready"
        ]
        self.assertTrue(creds_calls, "Expected drivesend_credentials_ready to be sent")
        for call in creds_calls:
            self.assertEqual(call.args[2], "real-sid")
            payload = call.args[1]
            self.assertEqual(payload.get("client_id"), "real-sid",
                "Payload must echo the sid for JS-side defense in depth")


class TestEnvFilePermissions(unittest.TestCase):
    """The .env file must be created with mode 0o600. Default umask
    typically produces 0o644, which is world-readable on multi-tenant
    hosts. The Setup and AutoUploader nodes both use os.open with
    O_CREAT|0o600 to create the file race-free."""

    def test_persist_env_writes_creates_0600(self):
        _install_fake_promptserver(client_id=None)
        setup_mod = _import_setup_node_fresh()

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(setup_mod, "NODE_DIR", Path(tmp)):
                env_path = setup_mod._persist_env_writes(
                    [("GOOGLE_DRIVE_FOLDER_ID", "stub")],
                    scrub_setup_keys=False,
                )
                self.assertTrue(env_path.exists())
                mode = stat.S_IMODE(env_path.stat().st_mode)
                self.assertEqual(
                    mode, 0o600,
                    f".env file mode is {oct(mode)}, expected 0o600. "
                    "Default-umask creation would expose secrets to other local users.",
                )


class TestStashHardening(unittest.TestCase):
    """The /drivesend/setup/stash route must enforce: client_id pattern,
    payload size cap, JSON content type, live-WebSocket gating. These
    are the hardening primitives that prevent stash poisoning."""

    def test_client_id_pattern_rejects_bad_input(self):
        _install_fake_promptserver(client_id=None)
        setup_mod = _import_setup_node_fresh()

        good = ["abc", "abc-123", "client.id_42", "X" * 128]
        bad = ["", "abc 123", "abc/../etc", "X" * 129, "<script>"]

        for s in good:
            self.assertIsNotNone(setup_mod._CLIENT_ID_PATTERN.match(s),
                f"client_id {s!r} should match pattern but did not")
        for s in bad:
            self.assertIsNone(setup_mod._CLIENT_ID_PATTERN.match(s),
                f"client_id {s!r} should NOT match pattern but did")

    def test_stash_ttl_eviction(self):
        _install_fake_promptserver(client_id=None)
        setup_mod = _import_setup_node_fresh()

        # Set a stash entry, then jump time past TTL and confirm it's gone.
        setup_mod._stash_set("test-sid", {"google_client_id": "x"})
        with mock.patch("time.time", return_value=9_999_999_999):
            self.assertIsNone(setup_mod._stash_consume("test-sid"))


if __name__ == "__main__":
    unittest.main()
