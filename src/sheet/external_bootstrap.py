"""Bootstrap executed by an external interpreter to start a Sheet session worker.

The external interpreter does not import the application runtime; this stub puts
the packaged Sheet source directory on ``sys.path`` and hands the session
identity to the real worker module.
"""

import sys


def _main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("usage: external_bootstrap.py <code directory> <session id>\n")
        return 2
    sys.path.insert(0, sys.argv[1])
    from sheet.external_worker import main

    return main(sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(_main())
