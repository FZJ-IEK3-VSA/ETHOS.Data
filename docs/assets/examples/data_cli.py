"""A data command for the collections.yaml beside this file.

Every package built on ETHOS.Data ships the same command under its own name,
``<your-tool>-data``; this wrapper gives the documentation's example file one
too, so that ``python data_cli.py show`` and ``python data_cli.py fetch ...``
can be run as written.
"""

from pathlib import Path

from ethos_data import tool_main

if __name__ == "__main__":
    raise SystemExit(
        tool_main(Path(__file__).with_name("collections.yaml"), prog="python data_cli.py")
    )
