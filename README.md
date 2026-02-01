# ComfyUI DriveSend Node

A ComfyUI custom node for uploading output files to Google Drive with optional encryption. Automatically monitors your output folder and uploads images/videos to your Google Drive.

> **Prefer DropBox?** Check out [DropSend Node](https://github.com/machinepainting/ComfyUI_DropSendNode)
---

## ⚠️ Important: Authentication Requirements

DriveSend supports two authentication methods, each with different requirements:

| Method | Account Type | Cost | Token Expiry | Recommended For |
|--------|-------------|------|--------------|-----------------|
| **Service Account** | Google Workspace only | Paid Tier | Never expires | Business/paid users |
| **OAuth 2.0** | Personal Gmail | Free | Auto-refreshes* | Personal/free users |

**\* OAuth tokens auto-refresh on each pod startup, effectively working like permanent credentials.**

### Why These Limitations?

- **Service Accounts** have 0 GB storage quota on personal Gmail accounts. Google blocks uploads entirely.
- **Google Workspace** ($7+/month) provides Shared Drives where service accounts can upload.
- **OAuth 2.0** works with personal Gmail but requires initial browser authorization.

---

## 📤📦 Features

- **DriveSend AutoUploader Node** - Automatically uploads new files to Google Drive
  - Monitors output folder in real-time
  - Supports: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.mp4`, `.avi`, `.mov`
  - Optional AES-128 encryption before upload
  - SHA256 checksum verification
  - Queue system for reliable uploads

- **DriveSend Setup Node** - Configures authentication and credentials
  - Generates OAuth refresh tokens
  - Outputs credentials for RunPod environment variables
  - Optional encryption key generation

---

## 💾 Installation

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/machinepainting/ComfyUI_DriveSendNode.git
pip install -r ComfyUI_DriveSendNode/requirements.txt
```

Restart ComfyUI after installation.

---

## 🔧 Google Cloud Setup (Required for Both Methods)

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account
3. Click **Select a project** (top, next to "Google Cloud" logo) → **New Project**
4. Name it (e.g., `ComfyUI-DriveSend`) → Click **Create**
5. Make sure your new project is selected (check dropdown at top)

### Step 2: Enable Google Drive API

1. Go to **APIs & Services** → **Library** (left sidebar)
2. Search for **Google Drive API**
3. Click on it → Click **Enable**

### Step 3: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials** (left sidebar)
2. Click **+ Create Credentials** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: **External** → Click **Create**
   - App name: `DriveSend`
   - User support email: Your email
   - Developer contact: Your email
   - Click **Save and Continue** through all steps
4. Back in Credentials, click **+ Create Credentials** → **OAuth client ID**
5. Application type: **Desktop app**
6. Name: `DriveSend`
7. Click **Create**
8. **Download JSON** and save as `client_secret.json` in the DriveSend node folder:
   ```
   ComfyUI/custom_nodes/ComfyUI_DriveSendNode/client_secret.json
   ```

### Step 4: Add Yourself as Test User

1. Go to **APIs & Services** → **OAuth consent screen**
2. Under **Test users**, click **+ Add Users**
3. Add your Gmail address
4. Click **Save**

---

## 🔐 Option A: OAuth 2.0 Setup (Personal Gmail - FREE)

**Best for:** Personal Gmail accounts, RunPod users who want free Google Drive uploads.

### How It Works

OAuth uses a refresh token that auto-refreshes on every pod startup. You authorize once, and it works indefinitely (as long as you don't revoke access).

### Local Setup

1. Add the **DriveSend Setup** node to your workflow
2. Configure:
   - `auth_method`: **oauth**
   - `storage_method`: **display_only** (for cloud) or **env_file** (for local)
   - `encryption_key_method`: Your preference
3. Run the node
4. A browser window opens - sign in and authorize the app
5. Copy the credentials from the console output

### RunPod Setup

1. Complete local setup first to get your refresh token
2. In RunPod, create these **Secrets**:
   
   | Secret Name | Value |
   |-------------|-------|
   | `GOOGLE_CLIENT_ID` | Your OAuth client ID |
   | `GOOGLE_CLIENT_SECRET` | Your OAuth client secret |
   | `GOOGLE_REFRESH_TOKEN` | The refresh token from setup |
   | `GOOGLE_DRIVE_FOLDER_ID` | Your Drive folder ID |
   | `comfyui_encryption_key` | (Optional) Your encryption key |

3. Add **Environment Variables** to your pod template:
   - `GOOGLE_CLIENT_ID` → `{{ RUNPOD_SECRET_GOOGLE_CLIENT_ID }}`
   - `GOOGLE_CLIENT_SECRET` → `{{ RUNPOD_SECRET_GOOGLE_CLIENT_SECRET }}`
   - `GOOGLE_REFRESH_TOKEN` → `{{ RUNPOD_SECRET_GOOGLE_REFRESH_TOKEN }}`
   - `GOOGLE_DRIVE_FOLDER_ID` → `{{ RUNPOD_SECRET_GOOGLE_DRIVE_FOLDER_ID }}`
   - `comfyui_encryption_key` → `{{ RUNPOD_SECRET_comfyui_encryption_key }}`

4. Deploy your pod and add the **DriveSend AutoUploader** node with:
   - `auth_method`: **oauth**
   - `run_process`: **True**

---

## 🏢 Option B: Service Account Setup (Google Workspace - PAID)

**Best for:** Google Workspace subscribers who want simpler, permanent authentication.

**Requirements:**
- Google Workspace account (~$7+/month)
- Custom domain (e.g., yourbusiness.com)

### Why Service Account Requires Google Workspace

Service accounts have 0 GB storage quota. On personal Gmail, uploads fail immediately with "storageQuotaExceeded". Google Workspace provides Shared Drives where service accounts CAN upload.

### Setup Steps

1. Go to **IAM & Admin** → **Service Accounts**
2. Click **+ Create Service Account**
3. Name it (e.g., `comfyui-uploader`) → Click **Create and Continue** → **Done**
4. Click on the service account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
5. Rename downloaded file to `service_account.json`
6. Place in: `ComfyUI/custom_nodes/ComfyUI_DriveSendNode/service_account.json`

### Create a Shared Drive

1. In Google Drive, click **Shared drives** (left sidebar)
2. Click **+ New** to create a Shared Drive
3. Add the service account email as a **Content Manager**
4. Get the Shared Drive ID from the URL

### RunPod Configuration

Create secrets and environment variables similar to OAuth setup, but use:
- `GOOGLE_SERVICE_ACCOUNT_JSON` (base64-encoded JSON)
- `GOOGLE_DRIVE_FOLDER_ID` (Shared Drive ID)

---

## 📁 Getting Your Folder ID

1. Open Google Drive
2. Navigate to your target folder (or Shared Drive)
3. Look at the URL:
   ```
   https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXX
   ```
4. Copy the long string after `/folders/` - that's your **Folder ID**

---

## 🔒 Encryption (Optional)

DriveSend supports AES-128 encryption for files before upload.

### Enable Encryption

1. In **DriveSend Setup** node, set `encryption_key_method` to **Display Only** or **save to .env**
2. Run the setup node to generate a key
3. Save the key securely (you'll need it to decrypt files)
4. In **DriveSend AutoUploader**, set `enable_encryption` to **True**

### Decrypt Files Locally

Use the scripts in the `/scripts/` folder:

**macOS:**
```bash
./scripts/decrypt_folder_mac.sh
```

**Windows:**
```bash
python scripts/decrypt_folder_win.py
```

**Linux:**
```bash
./scripts/decrypt_folder_linux.sh
```

---

## 🛠️ Troubleshooting

### "storageQuotaExceeded" Error
- **Cause:** Using service account with personal Gmail
- **Fix:** Use OAuth instead, or upgrade to Google Workspace

### "invalid_grant" Error
- **Cause:** Refresh token expired or revoked
- **Fix:** Run setup node again to get new refresh token

### "Access blocked: App not verified"
- **Cause:** OAuth consent screen in testing mode
- **Fix:** Add your email as a test user (Step 4 in Google Cloud Setup)

### Files not uploading
- **Check:** Console output for error messages
- **Check:** Folder ID is correct
- **Check:** Auth credentials are set in environment variables

### Browser doesn't open for OAuth
- **Cause:** Running on headless server (RunPod)
- **Fix:** Complete OAuth setup locally first, then copy credentials to RunPod

---

## 📊 Comparison: DriveSend vs DropSend

| Feature | DriveSend (Google Drive) | DropSend (Dropbox) |
|---------|-------------------------|-------------------|
| Free with personal account | ✅ OAuth only | ✅ Yes |
| Service account support | ⚠️ Workspace only | N/A |
| Storage (free tier) | 15 GB | 2 GB |
| Token management | Auto-refresh | Auto-refresh |
| Setup complexity | Medium | Easy |

---

## 🧪 Tested On

- Python 3.10 / 3.11
- ComfyUI (Feb 2026)
- RunPod GPU instances
- Google Drive API v3

---

## License

MIT
