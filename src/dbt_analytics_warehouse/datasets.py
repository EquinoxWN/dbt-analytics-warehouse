"""Pinned public input files: manifest validation, bounded download and checksum verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlsplit

ALLOWED_HOSTS = frozenset({"d37ci6vzurychx.cloudfront.net"})
MAX_FILE_BYTES = 64 * 1024 * 1024
CHUNK = 1024 * 1024
TIMEOUT_S = 60
_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}\.(parquet|csv)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

Opener = Callable[[str, float], IO[bytes]]


class DatasetError(Exception):
    """A manifest entry or a downloaded file failed validation."""


@dataclass(frozen=True)
class PinnedFile:
    """One file with its pinned URL, byte size and SHA-256."""

    name: str
    url: str
    size: int
    sha256: str


def parse_entry(raw: Any) -> PinnedFile:
    """Validate one manifest entry strictly."""
    if not isinstance(raw, dict) or set(raw) != {"name", "url", "size", "sha256"}:
        raise DatasetError(f"entry must have exactly name, url, size, sha256: {raw!r}")
    name, url, size, sha = raw["name"], raw["url"], raw["size"], raw["sha256"]
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise DatasetError(f"unsafe or invalid file name: {name!r}")
    if not isinstance(url, str):
        raise DatasetError("url must be a string")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise DatasetError(f"url must be https on an allowed host: {url!r}")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise DatasetError(f"url must not carry credentials, query or fragment: {url!r}")
    if not parts.path.endswith("/" + name):
        raise DatasetError(f"url path must end with the file name {name!r}")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_FILE_BYTES:
        raise DatasetError(f"size must be an integer in 1..{MAX_FILE_BYTES}: {size!r}")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        raise DatasetError(f"sha256 must be 64 lowercase hex characters: {sha!r}")
    return PinnedFile(name, url, size, sha)


def load_manifest(path: Path) -> list[PinnedFile]:
    """Read and validate the manifest; names must be unique."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), list) or not data["files"]:
        raise DatasetError("manifest must be an object with a non-empty 'files' list")
    files = [parse_entry(e) for e in data["files"]]
    if len({f.name for f in files}) != len(files):
        raise DatasetError("file names in the manifest must be unique")
    return files


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def is_verified(path: Path, pin: PinnedFile) -> bool:
    """True when the file exists with the pinned size and checksum."""
    return path.is_file() and path.stat().st_size == pin.size and sha256_of(path) == pin.sha256


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so a download can never leave the pinned host."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Fail on any 3xx response."""
        raise DatasetError("redirects are not followed; update the pinned URL instead")


def _default_opener(url: str, timeout: float) -> IO[bytes]:
    """Open a pinned HTTPS URL without following redirects."""
    opener = urllib.request.build_opener(_NoRedirect())
    response: IO[bytes] = opener.open(url, timeout=timeout)
    return response


def download(pin: PinnedFile, dest_dir: Path, opener: Opener = _default_opener) -> Path:
    """Download one pinned file atomically; keep it only if size and SHA-256 match."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / pin.name
    if is_verified(target, pin):
        return target
    partial = dest_dir / (pin.name + ".part")
    h = hashlib.sha256()
    written = 0
    try:
        with opener(pin.url, TIMEOUT_S) as src, partial.open("wb") as out:
            while chunk := src.read(CHUNK):
                written += len(chunk)
                if written > pin.size:
                    raise DatasetError(f"{pin.name}: more than the pinned {pin.size} bytes")
                h.update(chunk)
                out.write(chunk)
        if written != pin.size:
            raise DatasetError(f"{pin.name}: got {written} bytes, pinned {pin.size}")
        if h.hexdigest() != pin.sha256:
            raise DatasetError(f"{pin.name}: SHA-256 {h.hexdigest()} differs from the pin")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def fetch_all(manifest: Path, dest_dir: Path, opener: Opener = _default_opener) -> list[Path]:
    """Download every pinned file in the manifest into dest_dir."""
    return [download(pin, dest_dir, opener) for pin in load_manifest(manifest)]
