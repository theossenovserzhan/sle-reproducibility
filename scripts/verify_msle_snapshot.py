#!/usr/bin/env python3
"""Verify the public M-SLE snapshot without biometric data or secure benchmarks."""
from pathlib import Path
from urllib.parse import unquote
import hashlib, json, os, re, subprocess, sys
import numpy as np
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def check_outcomes(path, schema):
    with np.load(path, allow_pickle=False) as arrays:
        assert set(arrays.files) == set(schema), path
        assert set(arrays.files) <= {'rank1', 'rank5', 'unknown_accept', 'correct_accepted'}, path
        for name, expected in schema.items():
            value = arrays[name]
            assert str(value.dtype) == expected['dtype'] == 'uint8', path
            assert list(value.shape) == expected['shape'] and value.ndim in (4, 5), path
            assert np.all((value == 0) | (value == 1)), path


def main():
    manifest = json.loads((ROOT / 'publication/manifest.json').read_text(encoding='utf-8'))
    for relative, record in manifest['included'].items():
        path = ROOT / relative
        assert path.resolve().is_relative_to(ROOT) and path.is_file(), relative
        data = path.read_bytes()
        assert len(data) == record['bytes'], relative
        assert hashlib.sha256(data).hexdigest() == record['sha256'], relative
    for relative, schema in manifest['classification_outcome_arrays'].items():
        check_outcomes(ROOT / relative, schema)
    for name, pages in (('manuscript.pdf', 9), ('supplement.pdf', 13)):
        reader = PdfReader(ROOT / 'paper' / name)
        assert len(reader.pages) == pages, name
        assert not re.search(r'\?\?|\[\?\]', '\n'.join(p.extract_text() or '' for p in reader.pages)), name
    for relative in ('README.md', 'docs/REPRODUCE_MSLE.md'):
        path = ROOT / relative
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if target.startswith(('http:', 'https:', '#', 'mailto:')):
                continue
            destination = (path.parent / unquote(target.split('#')[0])).resolve()
            assert destination.is_relative_to(ROOT) and destination.exists(), (relative, target)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    for relative in ('experiments/revision_v2/test_reference.py', 'experiments/revision_v3/calibration_numeric.py'):
        result = subprocess.run([sys.executable, '-B', str(ROOT / relative)], cwd=ROOT,
                                env=environment, text=True, capture_output=True, timeout=90)
        assert result.returncode == 0, (relative, result.stdout, result.stderr)
        print(relative + ': passed')
    print(f"Public M-SLE snapshot verified: {len(manifest['included'])} source/paper hashes, "
          f"{len(manifest['classification_outcome_arrays'])} outcome schemas, 2 PDFs, relative links and reference/threshold tests")


if __name__ == '__main__':
    main()
