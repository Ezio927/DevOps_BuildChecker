"""命令行入口。

  python3 -m buildchecker version
  python3 -m buildchecker smoke [--fixture fixtures/md-rd]

保留 E4 的 version/smoke，E6 增加有证据输出的 full-check。
"""
import argparse
import json

from . import __version__
from .smoke import run_smoke
from .fullcheck import full_check


def build_parser():
    ap = argparse.ArgumentParser(prog="buildchecker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version", help="打印版本")
    sp = sub.add_parser("smoke", help="E4 冒烟测试：在容器里用 strace 跟踪 E3 md-rd 样例")
    sp.add_argument("--fixture", default="fixtures/md-rd")
    full = sub.add_parser("full-check", help="执行 clean build 并比较实际与声明依赖")
    full.add_argument("--fixture", default="fixtures/md-rd")
    full.add_argument("--out", required=True)
    full.add_argument("--clean-command", default="make clean")
    full.add_argument("--build-command", default="make app")
    full.add_argument("--timeout", type=int, default=120)
    full.add_argument("--fail-on-findings", action="store_true")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "version":
        print(f"buildchecker {__version__}")
        return 0
    if args.cmd == "full-check":
        try:
            if args.timeout <= 0:
                raise ValueError("Timeout must be positive")
            result = full_check(args.fixture, args.out, args.clean_command,
                                args.build_command, args.timeout)
        except (ValueError, OSError) as exc:
            print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "SUCCEEDED" and not (
            args.fail_on_findings and result["findings"]) else 1
    result = run_smoke(args.fixture)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1
