from pathlib import Path

path = Path('web/collector_runtime.py')
source = path.read_text(encoding='utf-8')
old = '''    except Exception as exc:
        raise CollectorStageBlocked(f"TEDA_INDEX_DISCOVERY_FAILED:{type(exc).__name__}") from exc
'''
new = '''    except Exception as exc:
        message = str(exc)[:180]
        raise CollectorStageBlocked(
            f"TEDA_INDEX_DISCOVERY_FAILED:{type(exc).__name__}:{message}"
        ) from exc
'''
count = source.count(old)
if count != 1:
    raise SystemExit(f'expected exactly one TEDA discovery error block, got {count}')
path.write_text(source.replace(old, new, 1), encoding='utf-8')
