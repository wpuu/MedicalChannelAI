#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

REPO = 'wpuu/MedicalChannelAI'
BRANCH = 'preview/multi-region-ui-acceptance'
TOKEN = os.environ['GITHUB_TOKEN']
ROOT = Path(__file__).resolve().parents[3]
API = f'https://api.github.com/repos/{REPO}/contents'


def request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f'{API}/{path}'
    if method == 'GET':
        url += f'?ref={BRANCH}'
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'MedicalChannelAI-preview-patch',
            'Content-Type': 'application/json',
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode('utf-8')
    return json.loads(raw) if raw else {}


def current_sha(path: str) -> str:
    return str(request('GET', path)['sha'])


def put_text(path: str, content: str, message: str) -> None:
    request(
        'PUT',
        path,
        {
            'message': message,
            'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
            'sha': current_sha(path),
            'branch': BRANCH,
        },
    )
    print(f'updated {path}')


def delete(path: str, message: str) -> None:
    request(
        'DELETE',
        path,
        {
            'message': message,
            'sha': current_sha(path),
            'branch': BRANCH,
        },
    )
    print(f'deleted {path}')


parser_path = 'web/pipeline/medical_channel_pipeline/ccgp_detail.py'
put_text(
    parser_path,
    (ROOT / parser_path).read_text(encoding='utf-8'),
    'fix: support verified Liaoning CCGP tender format',
)

for temporary_path in (
    'web/pipeline/scripts/patch_liaoning_ccgp_preview.py',
    'web/pipeline/scripts/publish_preview_patch_via_api.py',
    '.github/workflows/preview-patch-liaoning-ccgp.yml',
):
    delete(temporary_path, 'chore: remove temporary Liaoning patch tooling')
