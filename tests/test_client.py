import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hidrive_copy.client import HiDriveClient, HiDriveError, _read_dotenv


# --- monkeypatch urllib.request.urlopen for offline tests -----------------

class FakeResp:
    def __init__(self, body=b"", status=200):
        if isinstance(body, str):
            body = body.encode()
        self._buf = io.BytesIO(body)
        self.status = status

    def read(self, n=-1):
        return self._buf.read(n)

    def close(self):
        self._buf.close()


def make_client(monkeypatch, responses, requests):
    """responses: list of (status, body). requests: list to record calls."""
    calls = {"count": 0}
    state = {"refreshed": False}

    def fake_urlopen(req, *a, **kw):
        requests.append((req.full_url, dict(req.header_items())))
        calls["count"] += 1
        idx = calls["count"] - 1
        status, body = responses[min(idx, len(responses) - 1)]
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(body.encode() if isinstance(body, str) else body))
        return FakeResp(body, status)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client = HiDriveClient(access_token="tok")
    return client, state


def test_read_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# comment\nHIDRIVE_ACCESS_TOKEN="abc def"\nKEY=123\n\n\n')
    parsed = _read_dotenv(env)
    assert parsed == {"HIDRIVE_ACCESS_TOKEN": "abc def", "KEY": "123"}


def test_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("HIDRIVE_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError):
        HiDriveClient(access_token=None, env_file=tmp_path / "nope.env")


def test_list_dir_pagination_and_decode(monkeypatch):
    requests = []
    page1 = {"members": [
        {"name": "a%20b.txt", "type": "file", "size": 1},
        {"name": "sub", "type": "dir", "size": 0},
    ]}
    page2 = {"members": [
        {"name": "c.txt", "type": "file", "size": 2},
    ]}
    client, _ = make_client(
        monkeypatch,
        [(200, json.dumps(page1)), (200, json.dumps(page2))],
        requests,
    )
    client.page_size = 2  # force small page so pagination triggers
    members = client.list_dir("/x")
    assert [m["name"] for m in members] == ["a b.txt", "sub", "c.txt"]
    assert members[0]["type"] == "file"
    # two requests to /dir
    assert sum(1 for u, _ in requests if "/dir" in u) == 2


def test_list_dir_uses_offset_param(monkeypatch):
    requests = []
    page1 = {"members": [{"name": "f%2E", "type": "file"} for _ in range(3)]}
    page2 = {"members": []}
    client, _ = make_client(monkeypatch, [(200, json.dumps(page1)), (200, json.dumps(page2))], requests)
    client.page_size = 2
    client.list_dir("/x")
    dir_reqs = [u for u, _ in requests if "/dir" in u]
    assert "limit=0%2C2" in dir_reqs[0]
    assert "limit=2%2C2" in dir_reqs[1]


def test_download_file_writes_bytes(monkeypatch, tmp_path):
    requests = []
    client, _ = make_client(monkeypatch, [(200, b"hello-bytes")], requests)
    out = tmp_path / "out" / "f.txt"
    res = client.download_file("/remote/f.txt", out)
    assert res == out
    assert out.read_bytes() == b"hello-bytes"
    assert any("/file" in u for u, _ in requests)


def test_copy_folder_recursive(monkeypatch, tmp_path):
    """Drive copy_folder through a fake tree with nested dirs."""
    requests = []
    client, _ = make_client(monkeypatch, [], requests)

    tree = {
        "/r": [
            {"name": "a.txt", "type": "file", "size": 3},
            {"name": "sub", "type": "dir", "size": 0},
            {"name": "link", "type": "symlink", "size": 0},
        ],
        "/r/sub": [
            {"name": "b.txt", "type": "file", "size": 2},
            {"name": "empty", "type": "dir", "size": 0},
        ],
        "/r/sub/empty": [],
    }
    file_contents = {
        "/r/a.txt": b"AAA",
        "/r/sub/b.txt": b"BB",
    }

    calls = {"n": 0}

    def fake_urlopen(req, *a, **kw):
        url = req.full_url
        requests.append(url)
        if "/dir" in url:
            path = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)).get("path")
            return FakeResp(json.dumps({"members": tree.get(path, [])}).encode())
        if "/file" in url:
            path = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)).get("path")
            return FakeResp(file_contents[path])
        raise AssertionError(url)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    local = tmp_path / "dest"
    written = client.copy_folder("/r", local)
    assert (local / "a.txt").read_bytes() == b"AAA"
    assert (local / "sub" / "b.txt").read_bytes() == b"BB"
    assert (local / "sub" / "empty").is_dir()
    assert not (local / "link").exists()  # symlink skipped
    assert sorted(p.relative_to(local).as_posix() for p in written) == ["a.txt", "sub/b.txt"]


def test_401_triggers_refresh_then_retry(monkeypatch):
    requests = []
    client, _ = make_client(
        monkeypatch,
        [
            (401, '{"code":"invalid_token"}'),  # first attempt
            (200, json.dumps({"members": [{"name": "ok.txt", "type": "file"}]})),  # retry after refresh
        ],
        requests,
    )
    client.access_token = "tok"
    client.refresh_token = "rtok"
    client.client_id = "cid"
    client.client_secret = "csec"

    refresh_done = {"v": False}

    def fake_refresh():
        refresh_done["v"] = True
        client.access_token = "newtok"

    monkeypatch.setattr(client, "_refresh", fake_refresh)

    members = client.list_dir("/x")
    assert refresh_done["v"] is True
    assert members[0]["name"] == "ok.txt"
    # the second request should carry the refreshed token
    retry_header = [h for u, h in requests if "/dir" in u][1]
    assert dict(retry_header).get("Authorization") == "Bearer newtok"


def test_error_raised(monkeypatch):
    requests = []
    client, _ = make_client(monkeypatch, [(404, '{"code":"not_found"}')], requests)
    client.refresh_token = None  # no refresh -> immediate raise
    with pytest.raises(HiDriveError) as ei:
        client.list_dir("/missing")
    assert ei.value.status == 404
