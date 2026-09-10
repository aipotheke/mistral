# hidrive_copy

A minimal, dependency-free Python library to copy files from an **IONOS HiDrive**
folder to the local filesystem, using the HiDrive REST API
(`https://api.hidrive.strato.com/2.1`).

The auth token is read from a `.env` file.

## Setup

Copy `.env.example` to `.env` and fill in your token:

```
HIDRIVE_ACCESS_TOKEN=your_oauth2_access_token
```

The token is an OAuth2 access token issued by the HiDrive OAuth2 server
(`https://my.hidrive.com/oauth2/token`). See the HiDrive
[Get Started](https://developer.hidrive.com/get-started/) guide for how to obtain one.

Optional, for automatic refresh of short-lived access tokens:

```
HIDRIVE_CLIENT_ID=...
HIDRIVE_CLIENT_SECRET=...
HIDRIVE_REFRESH_TOKEN=...
```

## Usage

As a CLI:

```bash
python -m hidrive_copy /users/me/photos ./local-photos
```

As a library:

```python
from hidrive_copy import HiDriveClient

client = HiDriveClient()                       # reads ./.env by default
client.copy_folder("/users/me/photos", "./local-photos")

# or download a single file
client.download_file("/users/me/photos/cat.jpg", "./cat.jpg")

# or just list a directory
for entry in client.list_dir("/users/me/photos"):
    print(entry["type"], entry["name"], entry.get("size"))
```

## How it works

- `GET /dir?path=...&members=all&fields=members.name,members.type,members.size`
  lists directory contents (handles pagination and URL-encoded names).
- `GET /file?path=...` streams the file's bytes to disk.
- Subdirectories are mirrored recursively; symlinks are skipped (HiDrive stores
  them but offers no safe way to materialize a symlink target).

Only the Python standard library is used.
