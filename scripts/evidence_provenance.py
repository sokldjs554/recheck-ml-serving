"""Verify archived measurements against an explicit, immutable Git revision."""
import hashlib
from pathlib import Path
import re
import subprocess


def verify_sources(root: Path, report: dict, revision: str):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Evidence source revision must be a full Git SHA')
    for path, expected in report['source_sha256'].items():
        try:
            source = subprocess.check_output(['git', 'show', f'{revision}:{path}'], cwd=root, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            raise ValueError(f'Evidence source unavailable: {revision}:{path}; fetch repository history') from exc
        if hashlib.sha256(source).hexdigest() != expected:
            raise ValueError(f'Archived source hash mismatch: {revision}:{path}')
