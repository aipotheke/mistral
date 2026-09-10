"""Simple HiDrive client: copy files from a remote folder to local disk.

Auth token is read from a .env file (see .env.example).
Uses only the Python standard library.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.hidrive.strato.com/2.1"
TOKEN_URL = "https://my.hidrive.com/oauth2/token"


def _read_dotenv(path: str | os.PathLike = ".env") -> dict[str, str]:
    """Minimal .env parser (no external deps)."""
    env: dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return env
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            env[key] = value
    return env


def _first_env(*keys: str, env: dict[str, str] | None = None) -> str | None:
    sources = [env or {}, os.environ]
    for k in keys:
        for src in sources:
            if src.get(k):
                return src[k]
    return None


class HiDriveError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HiDrive API error {status}: {message}")
        self.status = status
        self.message = message


class HiDriveClient:
    """A thin wrapper around the HiDrive REST API."""

    def __init__(
        self,
        access_token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        env_file: str | os.PathLike = ".env",
    ) -> None:
        env = _read_dotenv(env_file)
        self.base_url = base_url.rstrip("/")
        self.page_size = 1000
        self.access_token = access_token or _first_env("HIDRIVE_ACCESS_TOKEN", env=env)
        self.client_id = client_id or _first_env("HIDRIVE_CLIENT_ID", env=env)
        self.client_secret = client_secret or _first_env("HIDRIVE_CLIENT_SECRET", env=env)
        self.refresh_token = refresh_token or _first_env("HIDRIVE_REFRESH_TOKEN", env=env)
        if not self.access_token and not self.refresh_token:
            raise ValueError(
                "No HiDrive credentials found. Set HIDRIVE_ACCESS_TOKEN in .env "
                "(or HIDRIVE_REFRESH_TOKEN + HIDRIVE_CLIENT_ID + HIDRIVE_CLIENT_SECRET)."
            )

    # -- internal HTTP ---------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _refresh(self) -> None:
        if not (self.refresh_token and self.client_id and self.client_secret):
            raise HiDriveError(401, "access token expired and no refresh credentials configured")
        data = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }
        ).encode()
        req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise HiDriveError(exc.code, exc.read().decode("utf-8", "replace")) from exc
        self.access_token = payload["access_token"]
        if payload.get("refresh_token"):
            self.refresh_token = payload["refresh_token"]

    def _get(self, endpoint: str, params: dict, *, stream: bool = False):
        qs = urllib.parse.urlencode(params)
        url = f"{self.base_url}/{endpoint.lstrip('/')}?{qs}"
        return self._get_url(url, stream=stream)

    def _get_url(self, url: str, *, stream: bool = False):
        for _ in range(2):
            req = urllib.request.Request(url, headers=self._headers())
            try:
                return urllib.request.urlopen(req)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                if exc.code == 401 and self.refresh_token and _ == 0:
                    self._refresh()
                    continue
                raise HiDriveError(exc.code, body) from exc

    # -- public API -------------------------------------------------------

    def list_dir(self, path: str) -> list[dict]:
        """Return members of a directory as dicts with decoded 'name' and 'type'."""
        members: list[dict] = []
        offset = 0
        page = self.page_size
        while True:
            params = {
                "path": path,
                "members": "all",
                "fields": "members.name,members.type,members.size",
                "limit": f"{offset},{page}",
           }
            resp = self._get("dir", params)
            try:
                data = json.loads(resp.read().decode("utf-8"))
            finally:
                resp.close()
            entries = data.get("members") or []
            for entry in entries:
                entry = dict(entry)
                entry["name"] = urllib.parse.unquote(entry.get("name", ""))
                members.append(entry)
            if len(entries) < page:
                break
            offset += page
        return members

    def download_file(self, remote_path: str, local_path: str | os.PathLike) -> Path:
        """Download a single file by its full remote path."""
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        params = {"path": remote_path}
        qs = urllib.parse.urlencode(params)
        url = f"{self.base_url}/file?{qs}"
        resp = self._get_url(url, stream=True)
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

    def copy_folder(self, remote_dir: str, local_dir: str | os.PathLike) -> list[Path]:
        """Recursively copy all files from a remote folder into a local folder.

        Directory structure is mirrored under local_dir. Symlinks are skipped.
        Returns the list of downloaded local file paths.
        """
        remote_dir = remote_dir.rstrip("/") or "/"
        local_root = Path(local_dir)
        local_root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []

        def _walk(rdir: str, ldir: Path) -> None:
            for entry in self.list_dir(rdir):
                name = entry["name"]
                rpath = (rdir.rstrip("/") + "/" + name) if rdir != "/" else "/" + name
                etype = entry.get("type")
                if etype == "dir":
                    sub = ldir / name
                    sub.mkdir(parents=True, exist_ok=True)
                    _walk(rpath, sub)
                elif etype == "file":
                    target = ldir / name
                    print(f"  {rpath} -> {target}")
                    self.download_file(rpath, target)
                    written.append(target)
                # symlinks are intentionally skipped

        _walk(remote_dir, local_root)
        return written
