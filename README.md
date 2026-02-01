# ComfyUI DriveSend Node

A ComfyUI custom node for uploading output files to Google Drive with optional encryption. Automatically monitors your output folder and uploads images/videos to your Google Drive.

> **Prefer DropBox?** Check out [DropSend Node](https://github.com/machinepainting/ComfyUI_DropSendNode)
---

## ⚠️ Important: Choose Your Authentication Method

| Method | Account Type | Cost | Best For |
|--------|-------------|------|----------|
| **OAuth 2.0** | Personal Gmail | Free | Most users |
| **Service Account** | Google Workspace | ~$7+/month | Business accounts |

**Most users should use OAuth 2.0** - it works with free personal Gmail accounts and tokens auto-refresh on each pod startup.

Service Accounts **do NOT work** with personal Gmail accounts (they have 0 GB storage quota). They only work with paid Google Workspace accounts.

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

# 🔐 Option A: OAuth 2.0 Setup (Personal Gmail - FREE)

**Recommended for most users.** Works with free personal Gmail accounts.

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your **personal Gmail account**
3. Click **Select a project** (top, next to "Google Cloud" logo) → **New Project**
4. Name it (e.g., `ComfyUI-DriveSend`) → Click **Create**
5. Make sure your new project is selected (check dropdown at top)

## Step 2: Enable Google Drive API

1. Go to **APIs & Services** → **Library** (left sidebar)
2. Search for **Google Drive API**
3. Click on it → Click **Enable**

## Step 3: Configure Google Auth Platform

1. Go to **APIs & Services** → **OAuth consent screen** (left sidebar)
2. You'll see "Google Auth Platform is not configured yet" → Click **Get Started**
3. Fill in:
   - **App name:** `DriveSend`
   - **User support email:** Select your email
4. Click **Next**
5. Select **External** (for personal Gmail)
6. Click **Next**
7. Enter your **email** for contact information
8. Click **Next**
9. Check the agreement box → Click **Create**

## Step 4: Create OAuth Client

1. Click **Create OAuth Client**
2. **Application type:** Select **Desktop app**
3. **Name:** `DriveSend`
4. Click **Create**
5. You'll see your **Client ID** and **Client Secret**

⚠️ **IMPORTANT:** Copy and save these values NOW. You won't be able to see the Client Secret again after closing this dialog!

- **Client ID:** Copy and save (ends with `.apps.googleusercontent.com`)
- **Client Secret:** Copy and save (starts with `GOCSPX-`)
- **Download JSON:** Click download to save `client_secret.json` as backup

6. Click **Done** when you've saved everything

> **Note:** Your email is automatically added as a test user. You can verify this under **Google Auth Platform** → **Audience** → **Test users**.

## Step 5: Create a Google Drive Folder

1. Go to [Google Drive](https://drive.google.com/)
2. Create a new folder (e.g., `ComfyUI_Uploads`)
3. Open the folder
4. Look at the URL in your browser:
   ```
   https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXX
   ```
5. Copy the long string after `/folders/` — that's your **Folder ID**
6. Save it with your Client ID and Client Secret

## Step 6: Run DriveSend Setup in ComfyUI

1. Open ComfyUI
2. Add the **DriveSend Setup** node
3. Configure:
   - `auth_method`: **oauth**
   - `folder_id`: Paste your Folder ID
   - `client_id`: Paste your Client ID (ends with `.apps.googleusercontent.com`)
   - `client_secret`: Paste your Client Secret (starts with `GOCSPX-`)
   - `auth_code`: **Leave blank** (for now)
   - `storage_method`: **display_only**
   - `encryption_key_method`: **off** (or your preference)

4. Run the node (Queue Prompt)
5. Check the **terminal/console** - you'll see a URL
6. **Click the URL** to open Google authorization
7. Sign in to Google and **accept access** for DriveSend
8. A second popup appears saying "Make sure you trust DriveSend" → Click **Continue**
9. You'll see an **authorization code** - copy it
10. Back in ComfyUI, paste the code into the `auth_code` field
11. Run the node again

## Step 7: Copy Credentials from Console

After running setup with your auth code, the console displays:

```
============================================================
[DriveSend Setup] Configuration Complete!
============================================================

Copy these values to your Environment Variables:

GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
GOOGLE_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your_secret_here
GOOGLE_REFRESH_TOKEN=your_refresh_token_here

============================================================
Copy the values above to your RunPod Secrets
============================================================
```

**Copy only the value after the `=` sign** (not the variable name).

---

## RunPod Secrets Setup (For Cloud Users)

### Step 8: Create RunPod Secrets

1. Go to [RunPod.io](https://www.runpod.io) → Click **Secrets** in the sidebar
2. Create 4 secrets (click **Create Secret** for each):

| Secret Name | Secret Value (paste only the value after `=`) |
|-------------|-----------------------------------------------|
| `GOOGLE_DRIVE_FOLDER_ID` | Your folder ID |
| `GOOGLE_CLIENT_ID` | Your client ID (ends with `.apps.googleusercontent.com`) |
| `GOOGLE_CLIENT_SECRET` | Your client secret (starts with `GOCSPX-`) |
| `GOOGLE_REFRESH_TOKEN` | Your refresh token |

### Step 9: Add Environment Variables to Pod Template

1. Go to your Pod → Click **Edit Template** (or create new pod)
2. Click **Environment Variables** dropdown
3. Click **+ Add Environment Variable** for each:

| Key | Value (click 🗝️ and select secret) |
|-----|-------------------------------------|
| `GOOGLE_DRIVE_FOLDER_ID` | `{{ RUNPOD_SECRET_GOOGLE_DRIVE_FOLDER_ID }}` |
| `GOOGLE_CLIENT_ID` | `{{ RUNPOD_SECRET_GOOGLE_CLIENT_ID }}` |
| `GOOGLE_CLIENT_SECRET` | `{{ RUNPOD_SECRET_GOOGLE_CLIENT_SECRET }}` |
| `GOOGLE_REFRESH_TOKEN` | `{{ RUNPOD_SECRET_GOOGLE_REFRESH_TOKEN }}` |

4. Click **Set Overrides** → Deploy your pod

### Step 10: Test Upload

1. Open ComfyUI on your RunPod
2. Add the **DriveSend AutoUploader** node
3. Set:
   - `auth_method`: **oauth**
   - `run_process`: **True**
4. Run a workflow that generates an image
5. Check console for upload messages
6. Verify file appears in your Google Drive folder!

---

# 🏢 Option B: Service Account Setup (Google Workspace - PAID)

**For Google Workspace subscribers only.** Does NOT work with personal Gmail accounts.

## Why Service Accounts Don't Work with Personal Gmail

Service accounts have **0 GB storage quota**. When they try to upload a file, Google immediately rejects it with "storageQuotaExceeded" error. This is a Google limitation, not a DriveSend bug.

Google Workspace accounts (~$7+/month) have Shared Drives where service accounts CAN upload.

## Requirements

- Google Workspace account (~$7+/month minimum)
- Custom domain (e.g., yourbusiness.com)
- Admin access to Google Workspace

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your **Google Workspace account**
3. Click **Select a project** (top, next to "Google Cloud" logo) → **New Project**
4. Name it (e.g., `ComfyUI-DriveSend`) → Click **Create**
5. Make sure your new project is selected

## Step 2: Enable Google Drive API

1. Go to **APIs & Services** → **Library** (left sidebar)
2. Search for **Google Drive API**
3. Click on it → Click **Enable**

## Step 3: Create Service Account

1. Go to **IAM & Admin** → **Service Accounts** (left sidebar)
2. Click **+ Create Service Account** (top of page)
3. Name it (e.g., `comfyui-uploader`)
4. Click **Create and Continue**
5. Skip optional steps → Click **Done**

## Step 4: Fix Organization Policy (If Key Creation Blocked)

Google may block service account key creation by default. If you get an error when creating keys:

### 4a: Grant Yourself Policy Admin Role

1. Click the dropdown at the **top next to the Google Cloud logo**
2. Select **All** tab
3. Click on your **organization** (shows your domain, not project name)
4. Go to **IAM & Admin** → **IAM** (left sidebar)
5. Click **+ Grant Access**
6. Principal: enter **your email**
7. Role: search for **Organization Policy Administrator**
8. Click **Save**

### 4b: Go Back to Project Level

1. Click the dropdown at the **top next to the Google Cloud logo**
2. Select your **project** (not the organization)

### 4c: Disable Key Creation Restrictions

1. Click the **Cloud Shell** icon (terminal icon, top-right of the page)
2. Wait for the terminal to load
3. When prompted **"Authorize Cloud Shell"** - click **Authorize**
4. Find your Project ID (shown in the Cloud Shell prompt, or under Project Settings)
5. Run these commands (replace `YOUR_PROJECT_ID`):

```bash
gcloud services enable orgpolicy.googleapis.com --project=YOUR_PROJECT_ID
```

```bash
gcloud org-policies reset iam.disableServiceAccountKeyCreation --project=YOUR_PROJECT_ID
```

```bash
gcloud org-policies reset iam.managed.disableServiceAccountKeyCreation --project=YOUR_PROJECT_ID
```

## Step 5: Create Service Account Key

1. Go to **IAM & Admin** → **Service Accounts** (left sidebar)
2. Click on your service account
3. Go to the **Keys** tab
4. Click **Add Key** → **Create new key**
5. Select **JSON** → Click **Create**
6. **Rename** the downloaded file to exactly: `service_account.json`
7. Place it in: `ComfyUI/custom_nodes/ComfyUI_DriveSendNode/service_account.json`

## Step 6: Create a Shared Drive

1. In Google Drive, click **Shared drives** (left sidebar)
2. Click **+ New** to create a Shared Drive
3. Name it (e.g., `ComfyUI Uploads`)
4. Click on the Shared Drive → Click the gear icon → **Manage members**
5. Add the service account email (from your `service_account.json`, field `client_email`) as **Content Manager**
6. Get the Shared Drive ID from the URL

## Step 7: Run DriveSend Setup

1. Add the **DriveSend Setup** node
2. Configure:
   - `auth_method`: **service_account**
   - `folder_id`: Your Shared Drive ID
   - `storage_method`: **display_only**
3. Run the node
4. Copy credentials from console to RunPod Secrets

## RunPod Secrets for Service Account

| Secret Name | Secret Value |
|-------------|--------------|
| `GOOGLE_DRIVE_FOLDER_ID` | Your Shared Drive ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Base64-encoded contents of service_account.json |

Add environment variables to your pod template same as OAuth method.

---

## 🔒 Encryption (Optional)

DriveSend supports AES-128 encryption for files before upload.

### Enable Encryption

1. In **DriveSend Setup** node, set `encryption_key_method` to **display_only**
2. Run the setup node to generate a key
3. Save the key securely - add it to RunPod Secrets as `COMFYUI_ENCRYPTION_KEY`
4. In **DriveSend AutoUploader**, set `enable_encryption` to **True**

### RunPod Secret for Encryption

| Secret Name | Secret Value |
|-------------|--------------|
| `COMFYUI_ENCRYPTION_KEY` | Your encryption key |

Add environment variable:
| Key | Value |
|-----|-------|
| `COMFYUI_ENCRYPTION_KEY` | `{{ RUNPOD_SECRET_COMFYUI_ENCRYPTION_KEY }}` |

### Decrypt Files Locally

Use the scripts in `/scripts/` folder after downloading encrypted files from Google Drive.

---

## 🛠️ Troubleshooting

### "storageQuotaExceeded" Error
- **Cause:** Using service account with personal Gmail
- **Fix:** Use OAuth instead (Option A). Service accounts only work with Google Workspace.

### "invalid_grant" Error
- **Cause:** Auth code expired or already used
- **Fix:** 
  1. Clear the `auth_code` field (delete the code)
  2. Run the setup node again to get a new URL
  3. Click the URL and authorize again
  4. Paste the new auth code

### OAuth Credentials Not Found
- **Cause:** Environment variables not set
- **Fix:** Make sure you created RunPod Secrets AND added them as Environment Variables to your pod template

### "Access blocked: App not verified"
- **Cause:** OAuth consent screen not configured
- **Fix:** Ensure you completed Step 3 (Configure Google Auth Platform)

### Organization Policy Blocks Key Creation
- **Cause:** Google's default security policy
- **Fix:** Follow Step 4 in Service Account setup (Fix Organization Policy)

### Files Not Uploading
- **Check:** Console output for error messages
- **Check:** Folder ID is correct
- **Check:** Run process is set to True

---

## 🧪 Tested On

- Python 3.10 / 3.11
- ComfyUI (Feb 2026)
- RunPod GPU instances
- Google Drive API v3

---

## License

MIT
