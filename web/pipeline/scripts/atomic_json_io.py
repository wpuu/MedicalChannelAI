from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


def _same_path(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    try:
        return first.exists() and second.exists() and first.samefile(second)
    except OSError:
        return False


def validate_json_output_paths(
    *,
    report_output: Path,
    data_outputs: dict[str, Path],
    input_paths: dict[str, list[Path]],
) -> None:
    """Prevent reports or data outputs from replacing unrelated pipeline state.

    A data output may intentionally be one of that same data type's inputs, as is
    common for read/merge/replace refreshes. Cross-type aliases are rejected.
    """
    all_inputs = [path for paths in input_paths.values() for path in paths]
    for name, output in data_outputs.items():
        if _same_path(report_output, output):
            raise ValueError(f'{name} output must not alias report output')
        for input_name, inputs in input_paths.items():
            if input_name == name:
                continue
            if any(_same_path(output, input_path) for input_path in inputs):
                raise ValueError(f'{name} output must not alias {input_name} input')
    output_items = list(data_outputs.items())
    for index, (name, output) in enumerate(output_items):
        for other_name, other_output in output_items[index + 1:]:
            if _same_path(output, other_output):
                raise ValueError(f'{name} and {other_name} outputs must be distinct')
    if any(_same_path(report_output, input_path) for input_path in all_inputs):
        raise ValueError('report output must not alias an input')


def _stage_bytes(path: Path, payload: bytes, mode: int | None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            staged.chmod(mode)
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _restore_bytes(path: Path, payload: bytes, mode: int | None) -> None:
    staged = _stage_bytes(path, payload, mode)
    os.replace(staged, path)


def write_json_bundle_atomic(outputs: dict[Path, Any]) -> None:
    """Stage JSON files before replacing any destination; roll back failed commits."""
    serialized = [
        (path.resolve(), (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        for path, payload in outputs.items()
    ]
    for index, (path, _payload) in enumerate(serialized):
        if any(_same_path(path, other) for other, _ in serialized[index + 1:]):
            raise ValueError(f'JSON bundle destinations must be distinct: {path}')

    staged: dict[Path, Path] = {}
    originals: dict[Path, tuple[bytes | None, int | None]] = {}
    replaced: list[Path] = []
    try:
        for path, payload in serialized:
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
            originals[path] = (path.read_bytes() if path.exists() else None, mode)
            staged[path] = _stage_bytes(path, payload, mode)
        for path, _payload in serialized:
            os.replace(staged[path], path)
            replaced.append(path)
    except BaseException:
        rollback_errors: list[Exception] = []
        for path in reversed(replaced):
            previous, mode = originals[path]
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    _restore_bytes(path, previous, mode)
            except Exception as exc:  # retain the original write error, but report failed rollback
                rollback_errors.append(exc)
        if rollback_errors:
            raise RuntimeError(f'JSON_BUNDLE_ROLLBACK_FAILED:{rollback_errors[0]}')
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: Any) -> None:
    write_json_bundle_atomic({path: payload})
