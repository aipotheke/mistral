"""Copy files from an IONOS HiDrive folder to local disk.

Token (HIDRIVE_TOKEN) is loaded from .env via python-dotenv.

Usage as a module:
    from hidrive_copy import copy_folder, download_file, list_dir
    copy_folder("/users/me/photos", "./local-photos")
"""
from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BASE_URL = "https://api.hidrive.strato.com/2.1"
PAGE = 1000

load_dotenv()
TOKEN = os.environ.get("HIDRIVE_TOKEN", "")


class HiDriveError(RuntimeError):
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(f"HiDrive API error {status}: {msg}")
        self.status = status


def _get(url: str) -> object:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as exc:
        raise HiDriveError(exc.code, exc.read().decode("utf-8", "replace")) from exc


def list_dir(path: str) -> list[dict]:
    import json
    members: list[dict] = []
    offset = 0
    while True:
        qs = urllib.parse.urlencode({
            "path": path,
            "members": "all",
            "fields": "members.name,members.type",
            "limit": f"{offset},{PAGE}",
        })
        resp = _get(f"{BASE_URL}/dir?{qs}")
        try:
            data = json.loads(resp.read().decode("utf-8"))
        finally:
            resp.close()
        entries = data.get("members") or []
        for e in entries:
            e = dict(e)
            e["name"] = urllib.parse.unquote(e.get("name", ""))
            members.append(e)
        if len(entries) < PAGE:
            break
        offset += PAGE
    return members


def download_file(remote_path: str, local_path: str | os.PathLike) -> Path:
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    qs = urllib.parse.urlencode({"path": remote_path})
    resp = _get(f"{BASE_URL}/file?{qs}")
    try:
        with local.open("wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
    finally:
        resp.close()
    return local


def copy_folder(remote_dir: str, local_dir: str | os.PathLike) -> list[Path]:
    remote_dir = remote_dir.rstrip("/") or "/"
    root = Path(local_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def _walk(rdir: str, ldir: Path) -> None:
        for entry in list_dir(rdir):
            name = entry["name"]
            rpath = (rdir.rstrip("/") + "/" + name) if rdir != "/" else "/" + name
            if entry.get("type") == "dir":
                sub = ldir / name
                sub.mkdir(parents=True, exist_ok=True)
                _walk(rpath, sub)
            elif entry.get("type") == "file":
                target = ldir / name
                print(f"  {rpath} -> {target}")
                download_file(rpath, target)
                written.append(target)

    _walk(remote_dir, root)
    return written
