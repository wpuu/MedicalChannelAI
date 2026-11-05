"""Read-only checks for the public app and its China entrypoint."""
from __future__ import annotations

import json
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SmokeFailure(RuntimeError):
    pass


def origin(url: str) -> tuple[str, str | None, int | None]:
    parsed = urlsplit(url)
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        if origin(request.full_url) != origin(new_url):
            raise SmokeFailure('CROSS_ORIGIN_REDIRECT')
        return super().redirect_request(request, response, code, message, headers, new_url)


def validate_status(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get('service') != 'MedicalChannelAI':
        raise SmokeFailure('STATUS_SERVICE_INVALID')
    snapshot = payload.get('snapshot')
    if payload.get('ready') is not True or not isinstance(snapshot, dict) or snapshot.get('available') is not True:
        raise SmokeFailure('STATUS_NOT_READY')
    if snapshot.get('freshness') != 'FRESH' or payload.get('degraded') is not False:
        raise SmokeFailure('STATUS_NOT_FRESH')
    source_health = snapshot.get('source_health')
    if not isinstance(source_health, dict) or source_health.get('status') != 'HEALTHY':
        raise SmokeFailure('SOURCE_HEALTH_NOT_HEALTHY')


def check_endpoint(url: str, *, status_endpoint: bool = False) -> None:
    request = Request(url, headers={'Accept': 'application/json' if status_endpoint else 'text/html'})
    with build_opener(SameOriginRedirect()).open(request, timeout=30) as response:
        code = response.status
        final_url = response.geturl()
        if not 200 <= code < 300 or origin(final_url) != origin(url):
            raise SmokeFailure('ENDPOINT_ORIGIN_OR_STATUS_INVALID')
        if status_endpoint:
            validate_status(json.loads(response.read(256 * 1024).decode('utf-8')))
        print(f'{url} -> HTTP {code} -> {final_url}')


def main() -> None:
    for base in ('https://medicalchannelai.vercel.app/', 'https://medicalai.qd.je/'):
        for path in ('', 'today', 'api/status'):
            check_endpoint(urljoin(base, path), status_endpoint=path == 'api/status')


if __name__ == '__main__':
    main()
