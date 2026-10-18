"""Historical measurements must retain their original source, not masquerade as HEAD."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('evidence_provenance', Path(__file__).resolve().parents[2]/'scripts/evidence_provenance.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_archive_accepts_changed_head_but_rejects_wrong_recorded_source(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, stderr=subprocess.PIPE).decode().strip()
    git('init')
    (tmp_path/'model.py').write_text('measured implementation\n')
    git('add', 'model.py')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'measured')
    revision = git('rev-parse', 'HEAD')
    report = {'source_sha256': {'model.py': hashlib.sha256((tmp_path/'model.py').read_bytes()).hexdigest()}}
    (tmp_path/'model.py').write_text('later instrumentation\n')
    module.verify_sources(tmp_path, report, revision)
    with pytest.raises(ValueError, match='hash mismatch'):
        module.verify_sources(tmp_path, {'source_sha256':{'model.py':'0'*64}}, revision)
    with pytest.raises(ValueError, match='unavailable'):
        module.verify_sources(tmp_path, report, '0'*40)
    with pytest.raises(ValueError, match='full Git SHA'):
        module.verify_sources(tmp_path, report, 'HEAD')
