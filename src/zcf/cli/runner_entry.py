"""
zcf-runner: Direct entrypoint for binfmt_misc and desktop file execution.
Invoked transparently when executing Windows or foreign architecture binaries.
"""

import sys
from zcf.execution.runner import ExecutionOrchestrator


def main():
    if len(sys.argv) < 2:
        print("Usage: zcf-runner <path-to-binary> [arguments...]", file=sys.stderr)
        sys.exit(1)

    target_bin = sys.argv[1]
    args = sys.argv[2:]

    orchestrator = ExecutionOrchestrator()
    try:
        code = orchestrator.run(target_bin, app_args=args)
        sys.exit(code)
    except Exception as e:
        print(f"[ZCF Runner Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
