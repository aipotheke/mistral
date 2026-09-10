# hidrive_copy

Copy files from an **IONOS HiDrive** folder to the local filesystem, using the
HiDrive REST API (`https://api.hidrive.strato.com/2.1`). Stdlib-only, one file.

The auth token is read from a `.env` file.

## Setup

Copy `.env.example` to `.env` and fill in your token:

```
HIDRIVE_TOKEN=your_oauth2_access_token
```

It's an OAuth2 access token from the HiDrive OAuth2 server. See the
[Get Started](https://developer.hidrive.com/get-started/) guide to obtain one.

## Usage

Copy a whole folder (mirrored recursively):

```bash
python hidrive_copy.py /users/me/photos ./local-photos
```

Download a single file:

```bash
python hidrive_copy.py /users/me/photos/cat.jpg ./cat.jpg --file
```

As a library:

```python
import hidrive_copy

token = hidrive_copy.load_token()
hidrive_copy.copy_folder("/users/me/photos", "./local-photos", token)
hidrive_copy.download_file("/users/me/photos/cat.jpg", "./cat.jpg", token)

for entry in hidrive_copy.list_dir("/users/me/photos", token):
    print(entry["type"], entry["name"])
```

## How it works

- `GET /dir?path=...&members=all&fields=members.name,members.type` lists a
  directory (paginated, URL-encoded names decoded).
- `GET /file?path=...` streams the file bytes to disk.
- Subdirectories are mirrored; symlinks are skipped.
