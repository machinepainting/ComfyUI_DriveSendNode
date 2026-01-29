# ComfyUI DriveSend Node (GoogleDrive Version)

**Untested/Dev/ Google Drive Version based on the working DropBox - DropSend Node - (https://github.com/machinepainting/ComfyUI_DropSendNode).**

A ComfyUI custom node for seamless Google Drive uploads with **optional** encryption capabilities. Automatically upload your ComfyUI output files (images and videos) to Google Drive cloud storage — with or without encryption.

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

**Encryption is completely optional.** If you don't need it, simply leave `enable_encryption` off and your files upload directly to Google Drive as-is. Enable encryption only if you want an extra layer of security for your files in cloud storage.

## 📤📦 Features

- **📤📦 DriveSend AutoUploader Node**
  Automatically uploads newly created files to Google Drive with optional file encryption capabilities.

  - Monitors a specified folder (e.g., ComfyUI's `output/`) in real time, with optional recursive subfolder monitoring.
  - Supports common ComfyUI file types: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.mp4`, `.avi`, `.mov`.
  - Optional encryption of files before upload, creating `.enc` files using a secure Fernet key (AES-128).
  - Configurable toggles for:
    - `enable_encryption`: Encrypt files before upload (default: off).
    - `Post_Delete_Enc`: Delete encrypted `.enc` files after upload verification (default: off).
    - `Subfolder_Monitor`: Monitor subfolders in the watch directory (default: on).
    - `run_process`: Start or stop the monitoring and uploading process (default: on).
  - Uses a queue system to ensure reliable processing of files, even under high load, preventing skipped files.
  - Verifies upload integrity using SHA256 checksums to ensure files are not corrupted during transfer.

- **🛠️📦 DriveSend Setup Node**
  Streamlines Google Drive API access setup and encryption key management.

  - Supports two authentication methods:
    - **Service Account** (Recommended for cloud/RunPod): No browser interaction needed after initial setup.
    - **OAuth 2.0**: For local setups where you want to use your personal Google account.
  - Provides API credentials and optional encryption key for easy integration into Environment Variables and RunPod Secrets.
  - Supports two storage methods:
    - `env_file`: Saves credentials to a `.env` file (recommended for local user setups).
    - `display_only`: Displays credentials in the console for manual copying (recommended for cloud setups like RunPod).
  - Supports three encryption key methods:
    - `off`: No encryption key is generated (use if encryption is not needed).
    - `Display Only`: Displays the encryption key in the console with other credentials.
    - `save to .env`: Saves the encryption key to the `.env` file.

- **🔐📁 Standalone Decryption Scripts (Local Use Only)**
  Decrypt `.enc` files on your local machine using the included scripts in the `/scripts/` folder.

  - **Local use only** — Run these on your computer after downloading/syncing encrypted files from Google Drive.
  - Cross-platform support for macOS, Windows, and Linux.
  - Restores encrypted files back to their original format (PNG, JPG, MP4, etc.).
  - Supports recursive folder processing.
  - Option to organize `.enc` files after decryption.
  - Includes optional encryption scripts for manual local encryption (not needed for normal DriveSend operation).

---

## 💾📦 Installation

Clone this repository into the `ComfyUI/custom_nodes/` directory:

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/machinepainting/ComfyUI_DriveSendNode.git
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 🔧📦 Google Drive Setup Instructions

### Option A: Service Account (Recommended for Cloud/RunPod)

Service accounts allow server-to-server authentication without browser interaction — ideal for cloud deployments.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the Google Drive API:
   - Navigate to **APIs & Services > Library**
   - Search for "Google Drive API"
   - Click **Enable**

4. Create a Service Account:
   - Navigate to **IAM & Admin > Service Accounts**
   - Click **Create Service Account**
   - Enter a name (e.g., `comfyui-drivesend`)
   - Click **Create and Continue**
   - Skip the optional steps, click **Done**

5. Create and Download the Key:
   - Click on your newly created service account
   - Go to the **Keys** tab
   - Click **Add Key > Create new key**
   - Select **JSON** and click **Create**
   - Save the downloaded file as `service_account.json`

6. Share Your Google Drive Folder:
   - Open Google Drive and create a folder for uploads (e.g., `ComfyUI_Output`)
   - Right-click the folder > **Share**
   - Add the service account email (found in `service_account.json` as `client_email`)
   - Give it **Editor** access
   - Copy the **Folder ID** from the URL (the long string after `/folders/`)

### Option B: OAuth 2.0 (For Local/Personal Use)

OAuth allows you to upload to your personal Google Drive account.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the Google Drive API (same as above)

4. Configure OAuth Consent Screen:
   - Navigate to **APIs & Services > OAuth consent screen**
   - Select **External** (unless you have Google Workspace)
   - Fill in the required fields (App name, support email)
   - Add your email as a test user
   - Save

5. Create OAuth Credentials:
   - Navigate to **APIs & Services > Credentials**
   - Click **Create Credentials > OAuth client ID**
   - Select **Desktop app**
   - Download the JSON file as `credentials.json`

---

## 🏃‍♂️‍➡️🫛📦 DriveSend Setup Node Instructions (RunPod & Cloud Users)

Using Service Account authentication (recommended for cloud):

1. Upload your `service_account.json` to a secure location on your pod, or encode it as base64 and store as an environment variable.

2. Open the 'DriveSend Setup Node' in your ComfyUI and configure:

   - `auth_method`              [ service_account ]
   - `service_account_json`     [ path to service_account.json OR leave blank if using env var ]
   - `folder_id`                [ paste your Google Drive folder ID ]
   - `storage_method`           [ display_only ]
   - `encryption_key_method`    [ Display Only ] (or off if not needed)

3. Click 'Run' on the node. Note the returned credentials in the terminal:

```bash
GOOGLE_DRIVE_FOLDER_ID=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GOOGLE_SERVICE_ACCOUNT_JSON=<base64 encoded or path>
comfyui_encryption_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX (if encryption enabled)
```

4. For RunPod users, create secrets:

   | Secret Name | Secret Value |
   |-------------|--------------|
   | `GOOGLE_DRIVE_FOLDER_ID` | Your folder ID |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | Base64-encoded service account JSON |
   | `comfyui_encryption_key` | Your encryption key (if using encryption) |

5. Add Environment Variables to your RunPod Pod:
   - `GOOGLE_DRIVE_FOLDER_ID` → `{{ RUNPOD_SECRET_GOOGLE_DRIVE_FOLDER_ID }}`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` → `{{ RUNPOD_SECRET_GOOGLE_SERVICE_ACCOUNT_JSON }}`
   - `comfyui_encryption_key` → `{{ RUNPOD_SECRET_comfyui_encryption_key }}`

6. Add the DriveSend AutoUploader Node to your workflow and run!

---

## 🛠️💻📦 DriveSend Setup Node Instructions (Local Computer Users)

Using OAuth 2.0 authentication:

1. Place your `credentials.json` in the `ComfyUI_DriveSendNode` folder

2. Open the 'DriveSend Setup Node' in your ComfyUI and configure:

   - `auth_method`              [ oauth ]
   - `folder_id`                [ paste your Google Drive folder ID ] (optional - uploads to root if blank)
   - `storage_method`           [ env_file ]
   - `encryption_key_method`    [ save to .env ] (or off if not needed)

3. Click 'Run' on the node. A browser window will open for Google authentication.

4. After authenticating, a `token.json` file will be created automatically.

5. Restart ComfyUI and add the DriveSend AutoUploader Node to your workflow.

---

## 🔑📦 Encryption Key Management

If you enable encryption in the DriveSend AutoUploader Node, an encryption key is generated during setup (unless `encryption_key_method` is `off`). This key is **required** to decrypt `.enc` files downloaded from Google Drive.

### Saving the Encryption Key

**Display Only (Recommended for Cloud):**

If `encryption_key_method` is `Display Only`, the key is shown in the console:

```
comfyui_encryption_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

Copy the key and store it securely using one of the methods below.

**Save to .env (Recommended for Local):**

If `encryption_key_method` is `save to .env`, the key is saved in `ComfyUI/custom_nodes/ComfyUI_DriveSendNode/.env` as:

```
comfyui_encryption_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

Ensure the `.env` file is excluded from version control (add to `.gitignore`).

---

## 🔐📁 Standalone Decryption Scripts (Local Use Only)

The `/scripts/` folder contains standalone scripts to decrypt files on your **local machine**.

> ⚠️ **These scripts are for LOCAL USE ONLY.** Run them on your personal computer after downloading or syncing encrypted files from Google Drive. Do not run on cloud instances.

### What Are These Scripts For?

**Decryption Scripts** — The primary scripts. Use these on your local machine to decrypt `.enc` files you've downloaded/synced from Google Drive. When encryption is enabled in the DriveSend node, your files are uploaded as encrypted `.enc` files. These scripts restore them to their original format so you can view and use them.

**Encryption Scripts** — Optional utility scripts. You do NOT need these for normal DriveSend operation—the node handles encryption automatically during upload. These are provided for users who want to manually encrypt local files for backup or other purposes using the same key.

### Supported File Types

The scripts support all formats the DriveSend node handles:

- Images: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`
- Videos: `.mp4`, `.avi`, `.mov`

When decrypting, the original file extension is preserved (e.g., `video.mp4.enc` → `video.mp4`).

### Prerequisites (All Platforms)

**Python 3.8+** and the **cryptography** library are required:

```bash
pip install cryptography
```

---

## 🍎 macOS Setup & Usage

### Storing Your Encryption Key in Keychain

1. Open **Keychain Access** (search in Spotlight)
2. Click **File > New Password Item**
3. Fill in the fields:
   - **Keychain Item Name:** `DriveSend_Encryption_Key`
   - **Account Name:** `DriveSend`
   - **Password:** Paste your encryption key
4. Click **Add**

### Running the Scripts

```bash
cd ComfyUI/custom_nodes/ComfyUI_DriveSendNode/scripts
chmod +x decrypt_folder_mac.sh
./decrypt_folder_mac.sh
```

---

## 🪟 Windows Setup & Usage

### Storing Your Encryption Key

1. Press `Win + R`, type `sysdm.cpl`, press Enter
2. Go to **Advanced** tab → **Environment Variables**
3. Under **User variables**, click **New**
4. Set:
   - **Variable name:** `DRIVESEND_ENCRYPTION_KEY`
   - **Variable value:** Your encryption key
5. Click **OK** and restart any open terminals

### Running the Scripts

```cmd
cd ComfyUI\custom_nodes\ComfyUI_DriveSendNode\scripts
python decrypt_folder_win.py
```

---

## 🐧 Linux Setup & Usage

### Storing Your Encryption Key

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
export DRIVESEND_ENCRYPTION_KEY="your_encryption_key_here"
```

Then reload: `source ~/.bashrc`

### Running the Scripts

```bash
cd ComfyUI/custom_nodes/ComfyUI_DriveSendNode/scripts
chmod +x decrypt_folder_linux.sh
./decrypt_folder_linux.sh
```

---

## 🔄 Cross-Platform Python Script (Alternative)

For maximum compatibility, use the Python script directly on any platform:

```bash
cd ComfyUI/custom_nodes/ComfyUI_DriveSendNode/scripts
python decrypt_folder.py
```

---

## ⚠️ Security Best Practices

1. **Never commit your `.env` file** - Ensure `.env` is in your `.gitignore`
2. **Never commit `service_account.json` or `credentials.json`** - These contain sensitive credentials
3. **Never commit `token.json`** - This contains your OAuth tokens
4. **Use secure key storage** - Prefer OS-native credential storage over plain text files
5. **Backup your encryption key** - Without it, encrypted files cannot be recovered
6. **Restrict service account permissions** - Only share specific folders, not your entire Drive

---

## 🧪 Tested On

**NOT Tested:**
I have not tested, this is a work in progress based on my working Dropbox DropSend Node version.


**Community Testing Needed:**
- Windows 10/11 — *Please test and report any issues or suggestions!*
- Linux (Ubuntu, Fedora, Arch) — *Please test and report any issues or suggestions!*

If you encounter any problems on Windows or Linux, please open an issue on GitHub with:
- Your OS version
- Python version
- Error messages (if any)
- Steps to reproduce

Contributions and pull requests are welcome!

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
    ├── decrypt_folder.py          # Cross-platform Python script (recommended)
    ├── decrypt_folder_mac.sh      # macOS decryption script
    ├── encrypt_folder_mac.sh      # macOS encryption script (local use only)
    ├── decrypt_folder_win.py      # Windows decryption script
    ├── encrypt_folder_win.py      # Windows encryption script (local use only)
    ├── decrypt_folder_linux.sh    # Linux decryption script
    └── encrypt_folder_linux.sh    # Linux encryption script (local use only)
```

---

## License

MIT
