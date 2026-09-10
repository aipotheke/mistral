"""Command line: python -m hidrive_copy REMOTE_DIR LOCAL_DIR [--env-file .env]"""
from __future__ import annotations

import argparse
import sys

from .client import DEFAULT_BASE_URL, HiDriveClient, HiDriveError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hidrive_copy",
        description="Copy files from an IONOS HiDrive folder to a local directory.",
    )
    parser.add_argument("remote_dir", help="Remote HiDrive folder path, e.g. /users/you/backup")
    parser.add_argument("local_dir", help="Local destination directory")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to a .env file holding HIDRIVE_ACCESS_TOKEN (default: .env)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    client = HiDriveClient(env_file=args.env_file, base_url=args.base_url)
    try:
        written = client.copy_folder(args.remote_dir, args.local_dir)
    except HiDriveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.status if 1 <= exc.status < 10 else 1
    print(f"\nDone. {len(written)} file(s) copied to {args.local_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
