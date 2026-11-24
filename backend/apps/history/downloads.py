"""
Checksum-pinned downloads for the offline model commands. A file is kept only
when its SHA-256 matches the pinned value, so a training run always reads the
exact bytes its report credits; a changed upstream file stops the run instead
of quietly changing the model.
"""
import hashlib
from pathlib import Path

import requests

USER_AGENT = 'GeoAlert-Talisay/1.0 (offline model build)'
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def fetch_verified(url: str, sha256: str, dest: Path, session=None) -> Path:
    """
    `dest`, downloaded from `url` when it is missing. Raises RuntimeError when
    the bytes don't match `sha256`: a fresh download's part file is deleted,
    and a cached file with the wrong checksum is left for the user to check.
    """
    dest = Path(dest)
    if dest.exists():
        if sha256_of(dest) != sha256:
            raise RuntimeError(f'{dest} does not match its pinned checksum; delete it to download it again.')
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix('.part')
    session = session or requests.Session()
    if hasattr(session, 'headers'):
        session.headers.setdefault('User-Agent', USER_AGENT)
    response = session.get(url, stream=True, timeout=300)
    response.raise_for_status()
    digest = hashlib.sha256()
    try:
        with open(part, 'wb') as f:
            for block in response.iter_content(chunk_size=CHUNK):
                if block:
                    f.write(block)
                    digest.update(block)
        if digest.hexdigest() != sha256:
            raise RuntimeError(f'{url} did not match its pinned checksum ({digest.hexdigest()}); nothing was kept.')
        part.replace(dest)
    finally:
        if part.exists():
            part.unlink()
    return dest
