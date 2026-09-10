"""Copy files from an IONOS HiDrive folder to local disk. Token read from .env.

Usage:
    python hidrive_copy.py /users/me/photos ./local-photos
    python hidrive_copy.py /remote/file.txt ./file.txt --file
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://api.hidrive.strato.com/2.1"
PAGE = 1000


def load_token(env_file: str = ".env") -> str:
    p = Path(env_file)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == "HIDRIVE_TOKEN":
                return v.strip().strip("'").strip('"')
    return os.environ.get("HIDRIVE_TOKEN", "")


class HiDriveError(RuntimeError):
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(f"HiDrive API error {status}: {msg}")
        self.status = status


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as exc:
        raise HiDriveError(exc.code, exc.read().decode("utf-8", "replace")) from exc


def list_dir(path: str, token: str) -> list[dict]:
    members: list[dict] = []
    offset = 0
    while True:
        qs = urllib.parse.urlencode({
            "path": path,
            "members": "all",
            "fields": "members.name,members.type",
            "limit": f"{offset},{PAGE}",
        })
        resp = _get(f"{BASE_URL}/dir?{qs}", token)
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


def download_file(remote_path: str, local_path: str | os.PathLike, token: str) -> Path:
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    qs = urllib.parse.urlencode({"path": remote_path})
    resp = _get(f"{BASE_URL}/file?{qs}", token)
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


def copy_folder(remote_dir: str, local_dir: str | os.PathLike, token: str) -> list[Path]:
    remote_dir = remote_dir.rstrip("/") or "/"
    root = Path(local_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def _walk(rdir: str, ldir: Path) -> None:
        for entry in list_dir(rdir, token):
            name = entry["name"]
            rpath = (rdir.rstrip("/") + "/" + name) if rdir != "/" else "/" + name
            if entry.get("type") == "dir":
                sub = ldir / name
                sub.mkdir(parents=True, exist_ok=True)
                _walk(rpath, sub)
            elif entry.get("type") == "file":
                target = ldir / name
                print(f"  {rpath} -> {target}")
                download_file(rpath, target, token)
                written.append(target)

    _walk(remote_dir, root)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hidrive_copy",
        description="Copy files from an IONOS HiDrive folder to a local directory.",
    )
    parser.add_argument("remote", help="Remote HiDrive path (folder, or file with --file)")
    parser.add_argument("local", help="Local destination (dir for folder copy, path for --file)")
    parser.add_argument("--file", action="store_true", help="Treat remote as a single file")
    parser.add_argument("--env-file", default=".env", help="Path to .env (default: .env)")
    args = parser.parse_args(argv)

    token = load_token(args.env_file)
    if not token:
        print("error: HIDRIVE_TOKEN not found in .env", file=sys.stderr)
        return 1
    try:
        if args.file:
            download_file(args.remote, args.local, token)
            print(f"Done. {args.remote} -> {args.local}")
        else:
            written = copy_folder(args.remote, args.local, token)
            print(f"\nDone. {len(written)} file(s) copied to {args.local}.")
    except HiDriveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
