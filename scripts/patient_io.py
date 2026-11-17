"""Let an executing notebook wait out a short file lock instead of failing.

On a synced or shared drive another program (a sync client, a site render, a virus scanner) can hold a file for a
moment. Opening it for writing then fails with errno 22, and a notebook that has just spent an hour fitting stops on
its last export. `add` puts a temporary first cell into the notebook that makes `open` retry such a failure for up to
two minutes; `remove` takes the cell out again before the notebook is saved, so the published notebook is unchanged.
"""
import nbformat

CELL_ID = "patient-io-temporary"
SOURCE = """import builtins as _b, io as _io, time as _t
if not getattr(_b.open, "_patient", False):
    _open = _b.open
    def _patient_open(file, mode="r", *args, **kwargs):
        if any(c in str(mode) for c in "wax+"):
            for _ in range(30):
                try:
                    return _open(file, mode, *args, **kwargs)
                except OSError as error:
                    if error.errno != 22:
                        raise
                    _t.sleep(4)
        return _open(file, mode, *args, **kwargs)
    _patient_open._patient = True
    _b.open = _io.open = _patient_open
"""


def add(nb):
    cell = nbformat.v4.new_code_cell(SOURCE)
    cell["id"] = CELL_ID
    nb.cells.insert(0, cell)


def remove(nb):
    if nb.cells and nb.cells[0].get("id") == CELL_ID:
        del nb.cells[0]
        for cell in nb.cells:                       # give back the numbering the notebook would have had
            if cell.cell_type == "code" and cell.get("execution_count"):
                cell["execution_count"] -= 1
                for output in cell.get("outputs", []):
                    if output.get("execution_count"):
                        output["execution_count"] -= 1
