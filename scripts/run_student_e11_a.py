"""Record only the student's E11-A cloud integration and contract checks."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = (root / args.out).resolve()
    if not out.is_relative_to(root / 'work') or out == root / 'work' or out.exists():
        parser.error('Use a new personal directory below work/')
    out.mkdir(parents=True)
    summary = {'student_id': '241880444', 'status': 'RUNNING', 'mode': 'E11-A_ONLY',
               'time_utc': datetime.now(timezone.utc).isoformat(), 'commands': [], 'provenance': 'EXECUTION',
               'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
               'working_tree': subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip()}
    if summary['working_tree']:
        raise ValueError('Formal source must be committed and clean')

    def logged(name, command, timeout=1200):
        folder = out / 'commands' / name
        folder.mkdir(parents=True)
        entry = {'argv': command, 'cwd': str(root), 'time_utc': datetime.now(timezone.utc).isoformat()}
        start = time.monotonic()
        with (folder / 'stdout.log').open('w') as stdout, (folder / 'stderr.log').open('w') as stderr:
            code = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, timeout=timeout).returncode
        entry.update(exit_code=code, elapsed_s=time.monotonic()-start, passed=code == 0)
        (folder / 'command.json').write_text(json.dumps(entry, indent=2)+'\n')
        summary['commands'].append(entry)
        print(name, 'exit', code, flush=True)
        for name in ('stdout.log', 'stderr.log'):
            print('\n'.join((folder / name).read_text(errors='replace').splitlines()[-10:]), flush=True)
        if code:
            raise ValueError('Command failed; inspect original logs')
        return folder

    try:
        logged('doctor', [sys.executable, 'scripts/doctor.py', '--out', str(out / 'env.json')])
        logged('build-a-only', [sys.executable, 'run_e11e12.py', 'build', '--a-only'])
        image = 'course-e11a:241880444'
        info = logged('image', ['docker', 'image', 'inspect', image])
        image_id = json.loads((info / 'stdout.log').read_text())[0]['Id']
        summary['image_id'] = image_id
        logged('toolchain', ['docker', 'run', '--rm', '--network', 'none', image, 'cat', '/opt/toolchain.lock'])
        unit = logged('a-contracts', [sys.executable, 'run_e11e12.py', 'test', '--a-only'])
        text = (unit / 'stderr.log').read_text()
        summary['unit_tests'] = int(re.search(r'Ran (\d+) tests', text).group(1))
        command = ['docker', 'run', '--rm', '--network', 'none', '--cpus', '2', '--memory', '1g',
                   '--pids-limit', '256', '--security-opt', 'no-new-privileges:true', '--cap-add', 'SYS_PTRACE',
                   '--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/tmp',
                   '-e', 'PYTHONPATH=/course/labs/e11e12:/course/labs/e8e10:/app',
                   '-v', str(root)+':/course', '-w', '/course', image, 'python3',
                   'labs/e11e12/student_241880444_a.py', '--out',
                   '/course/'+(out / 'experiment').relative_to(root).as_posix(), '--image-id', image_id]
        logged('integration-a-only', command)
        result = json.loads((out / 'experiment/summary.json').read_text())
        assert result['status'] == 'PASSED' and len(result['cases']) == 3
        assert result['source_sha'] == summary['source_sha']
        logged('scan', [sys.executable, 'scripts/secret_scan.py', '.', '--history', '--image', image])
        summary.update(status='PASSED', real_integration_cases=3, stale_report_rejected=True,
                       e11_b_executed=False, e12_executed=False, api_started=False)
    except Exception as exc:
        summary.update(status='FAILED', error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
        print('EVIDENCE_DIR='+str(out), flush=True)


if __name__ == '__main__':
    main()
