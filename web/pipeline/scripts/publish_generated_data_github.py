#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://api.github.com'


def request_json(url: str, *, token: str, method: str = 'GET', payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'MedicalChannelAI-GeneratedDataPublisher/0.2',
            **({'Content-Type': 'application/json'} if body is not None else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


def resolve_safe_base_head(
    *,
    owner: str,
    repo: str,
    branch: str,
    expected_sha: str,
    generated_paths: set[str],
    token: str,
) -> str:
    ref = request_json(f'{API}/repos/{owner}/{repo}/git/ref/heads/{branch}', token=token)
    head_sha = str(ref['object']['sha'])
    if head_sha == expected_sha:
        return head_sha

    base = urllib.parse.quote(expected_sha, safe='')
    head = urllib.parse.quote(head_sha, safe='')
    comparison = request_json(
        f'{API}/repos/{owner}/{repo}/compare/{base}...{head}',
        token=token,
    )
    if comparison.get('status') != 'ahead':
        raise RuntimeError(f'GITHUB_HEAD_NOT_DESCENDANT:{head_sha}:{expected_sha}')

    changed_paths = {
        str(item.get('filename') or '').strip()
        for item in comparison.get('files') or []
        if str(item.get('filename') or '').strip()
    }
    conflicts = sorted(generated_paths & changed_paths)
    if conflicts:
        raise RuntimeError(f'GENERATED_DATA_CHANGED_SINCE_RUN:{",".join(conflicts)}')

    print(
        f'main advanced safely from {expected_sha[:7]} to {head_sha[:7]}; '
        'no generated target files changed, rebasing generated data commit onto latest head.'
    )
    return head_sha


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Commit generated verified data with GitHub Git Data API; no local git required.'
    )
    parser.add_argument('--branch', default='main')
    parser.add_argument('--message', required=True)
    parser.add_argument('paths', nargs='+', type=Path)
    args = parser.parse_args()

    repository = os.environ.get('GITHUB_REPOSITORY', '').strip()
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    expected_sha = os.environ.get('GITHUB_SHA', '').strip()
    if not repository or not token or not expected_sha:
        raise RuntimeError('GITHUB_PUBLISH_CONTEXT_REQUIRED')

    owner, repo = repository.split('/', 1)
    generated_paths = {path.as_posix() for path in args.paths}
    head_sha = resolve_safe_base_head(
        owner=owner,
        repo=repo,
        branch=args.branch,
        expected_sha=expected_sha,
        generated_paths=generated_paths,
        token=token,
    )

    head_commit = request_json(f'{API}/repos/{owner}/{repo}/git/commits/{head_sha}', token=token)
    base_tree_sha = str(head_commit['tree']['sha'])
    tree_entries: list[dict] = []
    for path in args.paths:
        if not path.exists() or not path.is_file():
            raise RuntimeError(f'GENERATED_FILE_MISSING:{path}')
        raw = path.read_bytes()
        blob = request_json(
            f'{API}/repos/{owner}/{repo}/git/blobs',
            token=token,
            method='POST',
            payload={'content': base64.b64encode(raw).decode('ascii'), 'encoding': 'base64'},
        )
        tree_entries.append({
            'path': path.as_posix(),
            'mode': '100644',
            'type': 'blob',
            'sha': blob['sha'],
        })

    tree = request_json(
        f'{API}/repos/{owner}/{repo}/git/trees',
        token=token,
        method='POST',
        payload={'base_tree': base_tree_sha, 'tree': tree_entries},
    )
    if str(tree['sha']) == base_tree_sha:
        print('No verified regional state change to commit.')
        return 0

    # Fail closed if another writer moved main after our conflict check and tree creation.
    latest_ref = request_json(f'{API}/repos/{owner}/{repo}/git/ref/heads/{args.branch}', token=token)
    latest_sha = str(latest_ref['object']['sha'])
    if latest_sha != head_sha:
        raise RuntimeError(f'GITHUB_HEAD_MOVED_DURING_PUBLISH:{latest_sha}:{head_sha}')

    commit = request_json(
        f'{API}/repos/{owner}/{repo}/git/commits',
        token=token,
        method='POST',
        payload={'message': args.message, 'tree': tree['sha'], 'parents': [head_sha]},
    )
    request_json(
        f'{API}/repos/{owner}/{repo}/git/refs/heads/{args.branch}',
        token=token,
        method='PATCH',
        payload={'sha': commit['sha'], 'force': False},
    )
    print(f'published generated data commit={commit["sha"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
