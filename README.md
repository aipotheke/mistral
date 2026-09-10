# hidrive_copy

Copy files from an **IONOS HiDrive** folder to the local filesystem, using the
HiDrive REST API (`https://api.hidrive.strato.com/2.1`). Stdlib-only, one file.

The auth token is loaded from `.env` (via `python-dotenv`) as `HIDRIVE_TOKEN`.

## Setup

```bash
pip install python-dotenv
```

Copy `.env.example` to `.env` and fill in your token:

```
HIDRIVE_TOKEN=your_oauth2_access_token
```

It's an OAuth2 access token from the HiDrive OAuth2 server. See the
[Get Started](https://developer.hidrive.com/get-started/) guide to obtain one.

## Usage

```python
from hidrive_copy import copy_folder, download_file, list_dir

copy_folder("/users/me/photos", "./local-photos")
download_file("/users/me/photos/cat.jpg", "./cat.jpg")

for entry in list_dir("/users/me/photos"):
    print(entry["type"], entry["name"])
```

## How it works

- `GET /dir?path=...&members=all&fields=members.name,members.type` lists a
  directory (paginated, URL-encoded names decoded).
- `GET /file?path=...` streams the file bytes to disk.
- Subdirectories are mirrored; symlinks are skipped.
