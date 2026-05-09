// drivesend_oauth.js - ComfyUI extension for the DriveSend Setup Node.
//
// Architecture summary
// --------------------
// The Setup Node deliberately has NO secret-bearing inputs in its
// Python INPUT_TYPES. google_client_id, google_client_secret, auth_code,
// and the service-account JSON body are entered only via a browser-only
// modal launched from the "Set credentials..." button this extension
// installs on the node. The modal POSTs the values directly to
// /drivesend/setup/stash (a same-origin route registered by
// drivesend_setup_node.py) and closes. setup() consumes the stash entry
// on the next Queue.
//
// What this guarantees
//   - Secrets never enter any LiteGraph widget value, so they cannot be
//     serialized to workflow JSON, ComfyUI's localStorage auto-save,
//     PNG metadata, copy-pasted nodes, or PromptServer.history /
//     /history.
//   - Browser-native masking (input type=password) covers shoulder-
//     surfing during typing.
//   - Modal closes after Save with no in-process JS cache. User pastes
//     fresh values each time the modal opens.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const SETUP_NODE_TYPE = "DriveSendSetup";

let oauthPopup = null;

function findSetupNodes() {
    try {
        return app.graph.nodes.filter(n => n.type === SETUP_NODE_TYPE);
    } catch (e) {
        console.warn("[DriveSendNode] Could not enumerate graph nodes:", e);
        return [];
    }
}

// ---------------------------------------------------------------------------
// "Set credentials..." button widget on the Setup Node
// ---------------------------------------------------------------------------

function ensureCredentialButton(node) {
    if (!node || node.type !== SETUP_NODE_TYPE) return;
    if (node.__drivesendButtonAdded) return;
    if (typeof node.addWidget !== "function") {
        console.warn("[DriveSendNode] node.addWidget unavailable");
        return;
    }
    node.addWidget("button", "Set credentials...", null, () => {
        openCredentialEntryModal({ reason: "user-clicked", node });
    });
    node.__drivesendButtonAdded = true;
    try {
        if (typeof node.computeSize === "function" && typeof node.setSize === "function") {
            node.setSize(node.computeSize());
        }
    } catch (e) {
        console.warn("[DriveSendNode] could not recompute node size:", e);
    }
    try { app.graph.setDirtyCanvas(true, true); } catch (_) {}
    console.log(`[DriveSendNode] Installed Set-credentials button on ${SETUP_NODE_TYPE}`);
}

// Read the auth_method widget value from the given node so the modal
// can show only the relevant fields (OAuth vs service account).
function getAuthMethod(node) {
    try {
        if (!node || !node.widgets) return "oauth";
        const w = node.widgets.find(x => x.name === "auth_method");
        return (w && w.value) || "oauth";
    } catch (e) {
        return "oauth";
    }
}

// ---------------------------------------------------------------------------
// Credential ENTRY modal
// ---------------------------------------------------------------------------
//
// This is the modal the user types secrets INTO. Distinct from
// showCredentialModal below, which displays the credentials delivered
// at the end of a successful Setup run.

function openCredentialEntryModal({ reason, node }) {
    const existing = document.getElementById("drivesend-credentials-entry-modal");
    if (existing) {
        const firstInput = existing.querySelector("input, textarea");
        if (firstInput) firstInput.focus();
        return;
    }

    // If no node was passed (auto-trigger from server event), pick the
    // first Setup Node in the graph so we can read its auth_method.
    if (!node) {
        const nodes = findSetupNodes();
        node = nodes && nodes.length ? nodes[0] : null;
    }
    const authMethod = getAuthMethod(node);

    const overlay = document.createElement("div");
    overlay.id = "drivesend-credentials-entry-modal";
    overlay.style.cssText = [
        "position:fixed", "inset:0",
        "background:rgba(0,0,0,0.7)",
        "z-index:10001",
        "display:flex", "align-items:center", "justify-content:center",
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif'
    ].join(";");

    const dialog = document.createElement("div");
    dialog.style.cssText = [
        "background:#1e1e1e", "color:#eaeaea",
        "border-radius:12px", "padding:24px",
        "max-width:560px", "width:90%",
        "max-height:85vh", "overflow-y:auto",
        "box-shadow:0 20px 60px rgba(0,0,0,0.5)",
        "box-sizing:border-box"
    ].join(";");

    const header = document.createElement("div");
    header.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px";
    const title = document.createElement("h2");
    title.textContent = "Set DriveSend Credentials";
    title.style.cssText = "margin:0;font-size:1.2rem;color:#fff";
    const closeX = document.createElement("button");
    closeX.textContent = "x";
    closeX.setAttribute("aria-label", "Close");
    closeX.style.cssText = "background:none;border:none;color:#999;font-size:1.5rem;cursor:pointer;padding:0 8px;line-height:1";
    closeX.onclick = () => overlay.remove();
    header.appendChild(title);
    header.appendChild(closeX);
    dialog.appendChild(header);

    const intro = document.createElement("p");
    intro.style.cssText = "color:#bbb;font-size:0.85rem;line-height:1.5;margin:0 0 16px 0";
    if (authMethod === "service_account") {
        intro.textContent =
            "Paste the entire JSON body of your service account key file " +
            "below. Values are sent to the server (browser only, never " +
            "written to disk in display_only mode) and are NOT saved by " +
            "ComfyUI in any workflow JSON, PNG metadata, or browser cache.";
    } else {
        intro.textContent =
            reason === "auto-after-oauth-url"
                ? "Authorization URL printed in the ComfyUI terminal. Authorize at Google, copy the auth code, then paste Client ID + Client Secret + Auth Code below and click Save."
                : "Paste your Google OAuth Client ID and Client Secret. Leave the Auth Code blank for now; you'll paste it later after authorizing at Google. Values are sent to the server (browser only, never written to disk in display_only mode) and are NOT saved by ComfyUI in any workflow JSON, PNG metadata, or browser cache.";
    }
    dialog.appendChild(intro);

    const inputs = {};

    if (authMethod === "service_account") {
        // One large textarea for the JSON body.
        const row = document.createElement("div");
        row.style.cssText = "margin-bottom:12px";
        const lbl = document.createElement("label");
        lbl.textContent = "Service Account JSON";
        lbl.style.cssText = "display:block;font-size:0.8rem;color:#aaa;margin-bottom:4px;letter-spacing:0.02em";
        row.appendChild(lbl);

        const ta = document.createElement("textarea");
        ta.autocomplete = "off";
        ta.spellcheck = false;
        ta.value = "";
        ta.rows = 12;
        ta.style.cssText = "width:100%;box-sizing:border-box;padding:8px;font-family:Menlo,Monaco,monospace;font-size:0.8rem;background:#2a2a2a;color:#eaeaea;border:1px solid #444;border-radius:4px;resize:vertical";
        ta.placeholder = '{ "type": "service_account", "project_id": "...", ... }';
        row.appendChild(ta);
        dialog.appendChild(row);
        inputs.service_account_json = ta;
    } else {
        const fields = [
            { name: "google_client_id",     label: "Google OAuth Client ID" },
            { name: "google_client_secret", label: "Google OAuth Client Secret" },
            { name: "auth_code",            label: "Auth Code (paste after authorizing at Google)" },
        ];
        fields.forEach(({ name, label }) => {
            const row = document.createElement("div");
            row.style.cssText = "margin-bottom:12px";

            const lbl = document.createElement("label");
            lbl.textContent = label;
            lbl.style.cssText = "display:block;font-size:0.8rem;color:#aaa;margin-bottom:4px;letter-spacing:0.02em";
            row.appendChild(lbl);

            const input = document.createElement("input");
            input.type = "password";
            input.autocomplete = "off";
            input.spellcheck = false;
            input.value = "";
            input.style.cssText = "width:100%;box-sizing:border-box;padding:8px;font-family:Menlo,Monaco,monospace;font-size:0.9rem;background:#2a2a2a;color:#eaeaea;border:1px solid #444;border-radius:4px";
            row.appendChild(input);
            dialog.appendChild(row);
            inputs[name] = input;
        });
    }

    const status = document.createElement("p");
    status.style.cssText = "color:#f87171;font-size:0.8rem;margin:6px 0 0 0;min-height:1em";
    status.textContent = "";
    dialog.appendChild(status);

    const footer = document.createElement("div");
    footer.style.cssText = "display:flex;gap:10px;margin-top:16px;padding-top:12px;border-top:1px solid #333";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = "flex:1;padding:9px;background:#444;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9rem";
    cancelBtn.onclick = () => overlay.remove();

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "Save";
    saveBtn.style.cssText = "flex:1;padding:9px;background:#3b82f6;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9rem";
    saveBtn.onclick = async () => {
        const payload = {
            google_client_id: (inputs.google_client_id && inputs.google_client_id.value) || "",
            google_client_secret: (inputs.google_client_secret && inputs.google_client_secret.value) || "",
            auth_code: (inputs.auth_code && inputs.auth_code.value) || "",
            service_account_json: (inputs.service_account_json && inputs.service_account_json.value) || "",
        };
        const anyValue = Object.values(payload).some(v => v && v.trim());
        if (!anyValue) {
            status.textContent = "Nothing to save. Paste values into at least one field.";
            return;
        }
        const clientId = api && api.clientId ? api.clientId : null;
        if (!clientId) {
            status.textContent = "Browser not yet connected to ComfyUI. Wait a moment and try again.";
            return;
        }
        saveBtn.disabled = true;
        cancelBtn.disabled = true;
        try {
            const resp = await fetch("/drivesend/setup/stash", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ client_id: clientId, ...payload }),
            });
            if (!resp.ok) throw new Error("server returned " + resp.status);
        } catch (e) {
            console.error("[DriveSendNode] Stash POST failed:", e);
            status.textContent = "Could not save: " + e.message;
            saveBtn.disabled = false;
            cancelBtn.disabled = false;
            return;
        }
        Object.values(inputs).forEach(i => { if (i) i.value = ""; });
        overlay.remove();
        console.log("[DriveSendNode] Stashed credentials via entry modal; click Queue to run setup");
    };

    footer.appendChild(cancelBtn);
    footer.appendChild(saveBtn);
    dialog.appendChild(footer);

    Object.values(inputs).forEach(input => {
        if (!input) return;
        input.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" && input.tagName !== "TEXTAREA") {
                ev.preventDefault();
                saveBtn.click();
            }
            if (ev.key === "Escape") {
                ev.preventDefault();
                cancelBtn.click();
            }
        });
    });

    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    setTimeout(() => {
        const list = Object.values(inputs).filter(Boolean);
        const firstEmpty = list.find(i => !i.value);
        if (firstEmpty) firstEmpty.focus();
    }, 0);
}

// ---------------------------------------------------------------------------
// OAuth popup window (delegate to Google)
// ---------------------------------------------------------------------------

window.openDriveSendOAuth = function (url) {
    console.log("[DriveSendNode] Opening OAuth popup:", url);
    if (oauthPopup && !oauthPopup.closed) oauthPopup.close();
    const popup = window.open(
        url,
        "google_oauth",
        "width=520,height=720,scrollbars=yes,resizable=yes,status=no,location=no,toolbar=no,menubar=no"
    );
    if (popup) {
        oauthPopup = popup;
        popup.focus();
        const checkClosed = setInterval(() => {
            if (popup.closed) {
                console.log("[DriveSendNode] OAuth popup closed");
                clearInterval(checkClosed);
                oauthPopup = null;
            }
        }, 500);
        return popup;
    }
    console.error("[DriveSendNode] OAuth popup blocked by browser?");
    return null;
};

// ---------------------------------------------------------------------------
// Credential OUTPUT modal (display_only delivery surface)
// ---------------------------------------------------------------------------

function showCredentialModal(creds) {
    const existing = document.getElementById("drivesend-credentials-modal");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "drivesend-credentials-modal";
    overlay.style.cssText = [
        "position:fixed", "inset:0",
        "background:rgba(0,0,0,0.7)",
        "z-index:10000",
        "display:flex", "align-items:center", "justify-content:center",
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif'
    ].join(";");

    const dialog = document.createElement("div");
    dialog.style.cssText = [
        "background:#1e1e1e", "color:#eaeaea",
        "border-radius:12px", "padding:24px",
        "max-width:640px", "width:90%", "max-height:85vh",
        "overflow-y:auto",
        "box-shadow:0 20px 60px rgba(0,0,0,0.5)",
        "box-sizing:border-box"
    ].join(";");

    const header = document.createElement("div");
    header.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:12px";
    const title = document.createElement("h2");
    title.textContent = "DriveSend Credentials";
    title.style.cssText = "margin:0;font-size:1.25rem;color:#fff";
    const closeX = document.createElement("button");
    closeX.textContent = "x";
    closeX.setAttribute("aria-label", "Close");
    closeX.style.cssText = "background:none;border:none;color:#999;font-size:1.5rem;cursor:pointer;padding:0 8px;line-height:1";
    closeX.onclick = () => overlay.remove();
    header.appendChild(title);
    header.appendChild(closeX);
    dialog.appendChild(header);

    const intro = document.createElement("p");
    intro.style.cssText = "color:#bbb;font-size:0.9rem;line-height:1.5;margin:0 0 18px 0";
    intro.textContent =
        "These values are shown only in this browser and will be discarded when you close " +
        "this dialog. They are NOT written to disk in this mode. Save each value somewhere " +
        "safe now (password manager, secure note). Then configure them as your platform's " +
        "secrets (RunPod Secrets, Docker env, systemd EnvironmentFile). Most cloud platforms " +
        "require a pod or container restart for new secrets to take effect.";
    dialog.appendChild(intro);

    const flashCopied = (btn) => {
        const original = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = original; }, 1200);
    };

    Object.entries(creds).forEach(([name, value]) => {
        const row = document.createElement("div");
        row.style.cssText = "margin-bottom:14px";

        const labelRow = document.createElement("div");
        labelRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:4px";
        const label = document.createElement("label");
        label.textContent = name;
        label.style.cssText = "font-weight:600;font-size:0.85rem;color:#aaa;letter-spacing:0.02em";

        const copyBtn = document.createElement("button");
        copyBtn.textContent = "Copy";
        copyBtn.style.cssText = "padding:4px 12px;font-size:0.8rem;background:#3b82f6;color:#fff;border:none;border-radius:4px;cursor:pointer";
        copyBtn.onclick = async () => {
            try {
                await navigator.clipboard.writeText(value);
                flashCopied(copyBtn);
            } catch (e) {
                input.select();
                document.execCommand("copy");
                flashCopied(copyBtn);
            }
        };
        labelRow.appendChild(label);
        labelRow.appendChild(copyBtn);

        // Service-account JSON is long; render it as a textarea.
        const isLong = (value && value.length > 120) || /JSON|SERVICE_ACCOUNT/i.test(name);
        const input = document.createElement(isLong ? "textarea" : "input");
        if (!isLong) input.type = "text";
        input.value = value;
        input.readOnly = true;
        if (isLong) input.rows = 5;
        input.style.cssText = "width:100%;box-sizing:border-box;padding:8px;font-family:Menlo,Monaco,monospace;font-size:0.8rem;background:#2a2a2a;color:#eaeaea;border:1px solid #444;border-radius:4px;resize:vertical";
        input.onclick = () => input.select();
        input.onfocus = () => input.select();

        row.appendChild(labelRow);
        row.appendChild(input);
        dialog.appendChild(row);
    });

    const footer = document.createElement("div");
    footer.style.cssText = "display:flex;gap:10px;margin-top:18px;padding-top:14px;border-top:1px solid #333";

    const copyAllBtn = document.createElement("button");
    copyAllBtn.textContent = "Copy all as NAME=value";
    copyAllBtn.style.cssText = "flex:1;padding:10px;background:#3b82f6;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9rem";
    copyAllBtn.onclick = async () => {
        const text = Object.entries(creds).map(([k, v]) => `${k}=${v}`).join("\n");
        try {
            await navigator.clipboard.writeText(text);
            flashCopied(copyAllBtn);
        } catch (e) {
            console.error("[DriveSendNode] Clipboard write failed:", e);
            alert("Clipboard write failed; select and copy values manually.");
        }
    };

    const doneBtn = document.createElement("button");
    doneBtn.textContent = "I have copied them";
    doneBtn.style.cssText = "flex:1;padding:10px;background:#444;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9rem";
    doneBtn.onclick = () => overlay.remove();

    footer.appendChild(copyAllBtn);
    footer.appendChild(doneBtn);
    dialog.appendChild(footer);

    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
}

// ---------------------------------------------------------------------------
// Extension registration
// ---------------------------------------------------------------------------

app.registerExtension({
    name: "DriveSendNode.OAuthHandler",

    async setup() {
        console.log("[DriveSendNode] OAuth extension loaded");

        try {
            findSetupNodes().forEach(n => ensureCredentialButton(n));
        } catch (e) {
            console.warn("[DriveSendNode] setup-time sweep failed:", e);
        }

        api.addEventListener("drivesend_reconnect_complete", (event) => {
            console.log("[DriveSendNode] drivesend_reconnect_complete:", event.detail);
            const data = event.detail;
            if (data && data.success) {
                this.handleReconnectSuccess();
            }
        });

        api.addEventListener("drivesend_credentials_needed", (event) => {
            console.log("[DriveSendNode] drivesend_credentials_needed:", event.detail);
            const data = event.detail || {};
            const expectedClientId = data.client_id;
            const ourClientId = api && typeof api.clientId !== "undefined" ? api.clientId : null;
            if (expectedClientId && ourClientId && expectedClientId !== ourClientId) {
                console.warn(
                    "[DriveSendNode] Ignoring credentials-needed event: client_id mismatch"
                );
                return;
            }
            openCredentialEntryModal({ reason: "auto-after-oauth-url" });
        });

        api.addEventListener("drivesend_credentials_ready", (event) => {
            console.log("[DriveSendNode] drivesend_credentials_ready");
            const data = event.detail;
            if (!data || !data.credentials || typeof data.credentials !== "object") {
                console.error("[DriveSendNode] credentials_ready payload missing/malformed", event);
                return;
            }
            const expectedClientId = data.client_id;
            const ourClientId = api && typeof api.clientId !== "undefined" ? api.clientId : null;
            if (ourClientId == null) {
                console.warn(
                    "[DriveSendNode] api.clientId not available, cannot defense-in-depth verify; " +
                    "trusting the server's sid-targeted delivery."
                );
            } else if (expectedClientId && expectedClientId !== ourClientId) {
                console.warn(
                    "[DriveSendNode] Ignoring credentials event: client_id mismatch"
                );
                return;
            }
            const entry = document.getElementById("drivesend-credentials-entry-modal");
            if (entry) entry.remove();
            showCredentialModal(data.credentials);
        });
    },

    resetReconnectFields() {
        try {
            findSetupNodes().forEach(node => {
                if (!node.widgets) return;
                const reconnectWidget = node.widgets.find(w => w.name === "reconnect");
                if (reconnectWidget && reconnectWidget.value === true) {
                    reconnectWidget.value = false;
                    if (node.onWidgetChanged) node.onWidgetChanged("reconnect", false);
                }
            });
        } catch (e) {
            console.log("[DriveSendNode] Could not reset reconnect fields:", e);
        }
    },

    handleReconnectSuccess() {
        console.log("[DriveSendNode] Reconnect success - refreshing UI to show auth fields");
        this.resetReconnectFields();
        const entry = document.getElementById("drivesend-credentials-entry-modal");
        if (entry) entry.remove();
        setTimeout(() => {
            console.log("[DriveSendNode] Reloading after reconnect");
            window.location.reload();
        }, 1000);
    },

    nodeCreated(node) {
        ensureCredentialButton(node);
    },

    loadedGraphNode(node, _app) {
        ensureCredentialButton(node);
    },

    async beforeRegisterNodeDef(nodeType, nodeData, _app) {
        if (nodeData.name !== SETUP_NODE_TYPE) return;
        console.log(`[DriveSendNode] Registered ${SETUP_NODE_TYPE} enhancement`);

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
            try {
                ensureCredentialButton(this);
            } catch (e) {
                console.warn("[DriveSendNode] ensureCredentialButton via prototype hook failed:", e);
            }
            return r;
        };

        const originalExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            try {
                if (message && message.text && message.text[0]) {
                    const text = message.text[0];
                    if (text.includes("Google OAuth Ready!")) {
                        const m = text.match(/(https:\/\/accounts\.google\.com\/o\/oauth2\/auth[^\s]+)/);
                        if (m) {
                            setTimeout(() => window.openDriveSendOAuth(m[1]), 500);
                        }
                    }
                }
            } catch (e) {
                console.warn("[DriveSendNode] onExecuted hook error:", e);
            }
            if (originalExecuted) return originalExecuted.apply(this, arguments);
        };
    },
});
