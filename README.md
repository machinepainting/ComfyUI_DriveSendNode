# ComfyUI DriveSend Node

A ComfyUI custom node for seamless Google Drive uploads with **optional** encryption capabilities. Automatically upload your ComfyUI output files (images and videos) to Google Drive cloud storage.

## ⚠️ Authentication Methods - READ FIRST

| Method | Lifespan | Best For | Effort |
|--------|----------|----------|--------|
| **Service Account** | ✅ **Permanent** (never expires) | Cloud/RunPod | Medium setup |
| **OAuth 2.0** | ❌ **7 days** (must re-auth weekly) | Not recommended | Easy setup |

**We strongly recommend Service Account** for any persistent use. OAuth tokens expire every 7 days in Google's "testing mode" and there is no workaround without paying for Google Workspace or going through Google's app verification process.

---

## 🔄 How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLOUD (RunPod, etc.)                             │
│                                                                             │
│    ComfyUI generates files ──→ DriveSend Node ──→ Uploads to Google Drive   │
│        (png, mp4, etc.)         │                                           │
│                                 │                                           │
│                                 ▼                                           │
│                      ┌──────────────────────┐                               │
│                      │ Encryption OPTIONAL  │                               │
│                      │ ☐ OFF: file.png      │                               │
│                      │ ☑ ON:  file.png.enc  │                               │
│                      └──────────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                             📁 GOOGLE DRIVE
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           YOUR LOCAL MACHINE                                │
│                                                                             │
│   Google Drive syncs/downloads ──→ If encrypted: Run decrypt script (local) │
│                                                 ──→ file.png (viewable!)    │
│                                                                             │
│                                   If not encrypted: Ready to use!           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 💾 Installation

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/machinepainting/ComfyUI_DriveSendNode.git
cd ComfyUI_DriveSendNode
pip install -r requirements.txt
```

---

## 🔧 Google Cloud Setup (Service Account - Recommended)

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with a **personal Gmail account** (not work/school - they often have restrictions)
3. Click **Select a project** → **New Project**
4. Name it (e.g., `ComfyUI-DriveSend`) → **Create**

### Step 2: Enable Google Drive API

1. Go to **APIs & Services** → **Library**
2. Search for **Google Drive API**
3. Click **Enable**

### Step 3: Create Service Account

1. Go to **IAM & Admin** → **Service Accounts**
2. Click **+ Create Service Account**
3. Name it (e.g., `comfyui-uploader`)
4. Click **Create and Continue**
5. Skip optional steps → **Done**

### Step 4: Fix Organization Policy (IMPORTANT - New Google Accounts)

Google now blocks service account key creation by default. You MUST disable this policy first.

#### 4a. Grant Yourself Policy Admin Role

1. Go to **IAM & Admin** → **IAM**
2. Click the dropdown at top-left and select your **organization** (your email domain), not the project
3. Click **+ Grant Access**
4. Principal: **your email**
5. Role: search for **Organization Policy Administrator**
6. Click **Save**

#### 4b. Enable the Organization Policy API

Open **Cloud Shell** (terminal icon at top-right) and run:

```bash
gcloud services enable orgpolicy.googleapis.com --project=YOUR_PROJECT_ID
```

Replace `YOUR_PROJECT_ID` with your actual project ID.

#### 4c. Disable the Key Creation Restrictions

Run these commands in Cloud Shell:

```bash
gcloud org-policies reset iam.disableServiceAccountKeyCreation --project=YOUR_PROJECT_ID

gcloud org-policies reset iam.managed.disableServiceAccountKeyCreation --project=YOUR_PROJECT_ID
```

### Step 5: Create and Download the Key

1. Switch back to your **project** (click dropdown top-left, select your project)
2. Go to **IAM & Admin** → **Service Accounts**
3. Click on your service account
4. Go to **Keys** tab
5. Click **Add Key** → **Create new key** → **JSON** → **Create**
6. **IMPORTANT:** Rename the downloaded file to exactly: `service_account.json`

### Step 6: Share Your Google Drive Folder

1. Go to [Google Drive](https://drive.google.com)
2. Create a new folder (e.g., `ComfyUI_Uploads`)
3. Right-click the folder → **Share**
4. Open your `service_account.json` file and find the `client_email` value (looks like `name@project-id.iam.gserviceaccount.com`)
5. Paste that email in the Share dialog
6. Set permission to **Editor**
7. Click **Share** (uncheck "Notify people" if prompted)

### Step 7: Get Your Folder ID

1. Open the folder in Google Drive
2. Look at the URL: `https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXX`
3. Copy the long string after `/folders/` — that's your **Folder ID**

---

## 🚀 Local Setup (Quick Test)

1. Place `service_account.json` in the `ComfyUI_DriveSendNode` folder
2. Add the **DriveSend Setup** node to ComfyUI
3. Configure:
   - `auth_method`: **service_account**
   - `folder_id`: your folder ID
   - `owner_email`: **your Gmail address** (required!)
   - `storage_method`: **env_file**
   - `encryption_key_method`: **off** (for testing)
4. Run the node
5. Add **DriveSend AutoUploader** node and run a workflow

---

## ☁️ RunPod / Cloud Setup (Persistent)

### Option A: Custom Template (Recommended - One-Time Setup)

1. Run the **DriveSend Setup** node locally with `storage_method`: **display_only**
2. Copy the output values from the console
3. In RunPod, go to **Secrets** and create:

| Secret Name | Value |
|-------------|-------|
| `GOOGLE_DRIVE_FOLDER_ID` | Your folder ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | The base64 string from setup |
| `GOOGLE_OWNER_EMAIL` | Your Gmail address |
| `comfyui_encryption_key` | (only if using encryption) |

4. Create or edit a **Pod Template**:
   - Click **Edit Template** → **Environment Variables**
   - Add each variable, linking to secrets:
     - Key: `GOOGLE_DRIVE_FOLDER_ID` → Value: `{{ RUNPOD_SECRET_GOOGLE_DRIVE_FOLDER_ID }}`
     - Key: `GOOGLE_SERVICE_ACCOUNT_JSON` → Value: `{{ RUNPOD_SECRET_GOOGLE_SERVICE_ACCOUNT_JSON }}`
     - Key: `GOOGLE_OWNER_EMAIL` → Value: `{{ RUNPOD_SECRET_GOOGLE_OWNER_EMAIL }}`
     - Key: `comfyui_encryption_key` → Value: `{{ RUNPOD_SECRET_comfyui_encryption_key }}`
   - Click **Set Overrides**

5. Deploy pods using this template — credentials persist automatically!

### Option B: Manual Environment Variables (Each Pod)

If you don't want to create a template, manually add the environment variables each time you create a pod. This is more tedious but works the same way.

---

## 📋 Node Settings Reference

### DriveSend Setup Node

| Field | Description |
|-------|-------------|
| `auth_method` | `service_account` (recommended) or `oauth` |
| `folder_id` | Google Drive folder ID from URL |
| `owner_email` | **Your Gmail** - required for service account! |
| `storage_method` | `display_only` (cloud) or `env_file` (local) |
| `encryption_key_method` | `off`, `Display Only`, or `save to .env` |
| `service_account_path` | Default: `service_account.json` |

### DriveSend AutoUploader Node

| Field | Description |
|-------|-------------|
| `watch_directory` | Folder to monitor (default: ComfyUI output) |
| `auth_method` | Must match setup node |
| `folder_id` | Override folder ID (or leave blank to use env var) |
| `owner_email` | Override owner email (or leave blank to use env var) |
| `enable_encryption` | Encrypt files before upload |
| `Post_Delete_Enc` | Delete .enc files after upload |
| `Subfolder_Monitor` | Watch subfolders too |
| `run_process` | Start/stop the monitor |

---

## ❓ Why is `owner_email` Required?

**Service accounts have 0 GB storage quota.** When a service account uploads a file, it owns that file — but it has no storage space!

The `owner_email` setting transfers ownership to your personal Gmail account after upload, so the file uses YOUR storage quota (15 GB free).

Without this, uploads will fail with: `403 storageQuotaExceeded`

---

## 🔐 Encryption (Optional)

Enable encryption to protect files in cloud storage:

1. In Setup node: set `encryption_key_method` to **Display Only** or **save to .env**
2. In AutoUploader: set `enable_encryption` to **True**
3. Save your encryption key securely — you need it to decrypt files!

See the `/scripts/` folder for decryption scripts (run on your local machine after downloading).

---

## 🛠️ Troubleshooting

### "service_account.json NOT FOUND"
- Rename your downloaded key file to exactly `service_account.json`
- Place it in the `ComfyUI_DriveSendNode` folder

### "403 storageQuotaExceeded"
- Set `owner_email` to your Gmail address
- Make sure the folder is shared with your service account email

### "Organization Policy blocks key creation"
- Follow Step 4 in the setup guide to disable the policy restrictions
- Run the gcloud commands in Cloud Shell

### "Permission denied" on upload
- Make sure you shared the Google Drive folder with the service account email
- The service account needs **Editor** access

---

## 📁 Repository Structure

```
ComfyUI_DriveSendNode/
├── __init__.py
├── drivesend_uploader_node.py
├── drivesend_setup_node.py
├── gdrive_upload.py
├── gdrive_auth_manager.py
├── encrypt_file.py
├── monitor_output.py
├── requirements.txt
├── README.md
├── .gitignore
└── scripts/
    ├── decrypt_folder.py
    ├── decrypt_folder_mac.sh
    ├── encrypt_folder_mac.sh
    ├── decrypt_folder_win.py
    ├── encrypt_folder_win.py
    ├── decrypt_folder_linux.sh
    └── encrypt_folder_linux.sh
```

---

## 🧪 Status

**Testing in Progress** — Based on the working [DropSend Node](https://github.com/machinepainting/ComfyUI_DropSendNode).

Please report issues on GitHub!

---

## License

MIT
