"""Execute one "Learn PyCPT" notebook in place and record what ran.

Run inside the pinned Debian environment (kernel "pycpt-tutorial"):

    python scripts/execute_learn_chapter.py docs/learn/01-first-case.ipynb

After execution, the user's home directory is replaced by "~" in text outputs so
published pages do not expose a personal path. Images are left untouched. The
record lists every cell that was changed this way.
"""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import time

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "research/audits/learn-pycpt"


def redact_home(nb):
    home = str(Path.home())
    changed = []
    for index, cell in enumerate(nb.cells):
        for output in cell.get("outputs", []):
            if output.get("output_type") == "stream" and home in output.get("text", ""):
                output["text"] = output["text"].replace(home, "~")
                changed.append(index)
            data = output.get("data", {})
            for mime in ("text/plain", "text/html"):
                if home in data.get(mime, ""):
                    data[mime] = data[mime].replace(home, "~")
                    changed.append(index)
    return sorted(set(changed))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--timeout", type=int, default=1800, help="per-cell timeout in seconds")
    args = parser.parse_args()

    path = args.notebook.resolve()
    nb = nbformat.read(path, as_version=4)
    start = time.monotonic()
    client = NotebookClient(nb, timeout=args.timeout, kernel_name="pycpt-tutorial",
                            resources={"metadata": {"path": str(path.parent)}})
    try:
        client.execute()
    except Exception:
        failed = ROOT / "temp" / f"{path.stem}-failed.ipynb"
        failed.parent.mkdir(exist_ok=True)
        nbformat.write(nb, failed)
        print(f"Execution failed; partial notebook saved to {failed}")
        raise

    errors = [i for i, c in enumerate(nb.cells)
              if any(o.get("output_type") == "error" for o in c.get("outputs", []))]
    if errors:
        raise RuntimeError(f"Cells with errors: {errors}")

    redacted = redact_home(nb)
    nbformat.write(nb, path)

    record = {
        "notebook": str(path.relative_to(ROOT)),
        "executed": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(time.monotonic() - start, 1),
        "kernel": "pycpt-tutorial",
        "code_cells": sum(c.cell_type == "code" for c in nb.cells),
        "errors": 0,
        "home_path_redacted_in_cells": redacted,
        "notebook_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out = AUDIT_DIR / f"{path.stem}-execution.json"
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
