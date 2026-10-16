"""Live Daytona check: create a sandbox, run a command, delete it. `make check-daytona`."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_env(path='.env'):
    try:
        for line in Path(path).read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and not key.strip().startswith('#') and value.strip():
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))
    except OSError:
        pass


def step(name, ok, detail=''):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f'  {detail}' if detail else ''))
    return ok


def main():
    load_env()
    if not step('DAYTONA_API_KEY set', bool(os.environ.get('DAYTONA_API_KEY'))):
        return 1
    sandbox = daytona = None
    ok = True
    try:
        from daytona import Daytona
        step('import daytona SDK', True)
        daytona = Daytona()
        sandbox = daytona.create(timeout=90)
        step('create sandbox', True, f'id={sandbox.id}')
        response = sandbox.process.code_run("print('relay-helper-ok')", timeout=30)
        ok = step('run code', response.exit_code == 0 and 'relay-helper-ok' in (response.result or ''),
                  f'exit_code={response.exit_code}')
    except Exception as exc:  # noqa: BLE001 - report type only, never request details
        ok = step('daytona call', False, type(exc).__name__)
    finally:
        if sandbox is not None:
            try:
                daytona.delete(sandbox)
                step('delete sandbox', True)
            except Exception as exc:  # noqa: BLE001
                ok = step('delete sandbox', False, type(exc).__name__)
    print('RESULT: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
