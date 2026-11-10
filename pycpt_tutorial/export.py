"""Export xarray results or readable CPTv10 text to verified NetCDF files."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

import numpy as np
import xarray as xr


def save_netcdf(
    data: xr.Dataset | xr.DataArray,
    destination: str | Path,
    *,
    metadata: Mapping[str, Any] | None = None,
    compression: int = 4,
    overwrite: bool = False,
) -> Path:
    """Save a losslessly compressed NetCDF4 file and verify its decoded contents.

    Values, names, units, coordinates, and attributes are retained. ``metadata``
    adds or replaces global attributes; supply public experiment information only.
    It must contain NetCDF-compatible attribute values, such as strings or numbers.
    No scientific validation method or CF compliance is inferred or asserted.

    A temporary file is written and reopened before publishing the result. Existing
    files are protected unless ``overwrite=True``. Non-overwrite publishing uses a
    same-directory hard link, requiring a filesystem that supports hard links.
    Verification reads the full result: this helper is intended for tutorial-scale
    outputs rather than very large archives. Run in the installed PyCPT environment.
    """
    if isinstance(data, xr.DataArray):
        if not isinstance(data.name, str) or not data.name:
            raise ValueError("Give the DataArray a variable name before exporting.")
        dataset = data.to_dataset()
    elif isinstance(data, xr.Dataset):
        dataset = data
    else:
        raise TypeError("data must be an xarray Dataset or named DataArray.")
    if not dataset.data_vars:
        raise ValueError("The dataset has no data variables to export.")
    if type(compression) is not int or not 0 <= compression <= 9:
        raise ValueError("compression must be an integer from 0 to 9.")
    target = Path(destination).expanduser().absolute()
    if target.suffix.lower() not in {".nc", ".nc4"}:
        raise ValueError("Use a .nc or .nc4 destination filename.")
    if not overwrite and os.path.lexists(target):
        raise FileExistsError(f"Output already exists: {target}")

    exported = dataset.copy(deep=False)
    exported.attrs = dict(dataset.attrs)
    if metadata:
        exported.attrs.update(metadata)
    encoding = {
        name: {"zlib": bool(compression), "complevel": compression, "shuffle": bool(compression)}
        for name, variable in exported.data_vars.items()
        if variable.ndim and np.issubdtype(variable.dtype, np.number)
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".nc", dir=target.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        exported.to_netcdf(temporary, engine="netcdf4", format="NETCDF4", encoding=encoding)
        with xr.open_dataset(temporary, engine="netcdf4") as reopened:
            xr.testing.assert_identical(exported, reopened.load())
        if overwrite:
            os.replace(temporary, target)
        else:
            # Fails atomically if another process created the destination meanwhile.
            os.link(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Existing NetCDF or readable CPTv10 text file")
    parser.add_argument("destination", type=Path, help="Output .nc filename")
    parser.add_argument("--input-format", choices=("auto", "netcdf", "cpt"), default="auto")
    parser.add_argument("--metadata", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--compression", type=int, default=4, choices=range(10))
    parser.add_argument("--overwrite", action="store_true", help="Explicitly allow replacement")
    args = parser.parse_args()
    metadata = {}
    for entry in args.metadata:
        name, separator, value = entry.partition("=")
        if not separator or not name.strip():
            parser.error("Each --metadata argument must be NAME=VALUE.")
        metadata[name.strip()] = value
    input_format = args.input_format
    if input_format == "auto":
        input_format = "netcdf" if args.source.suffix.lower() in {".nc", ".nc4"} else "cpt"
    if input_format == "netcdf":
        with xr.open_dataset(args.source, engine="netcdf4") as opened:
            dataset = opened.load()
    else:
        from cptio import open_cptdataset

        dataset = open_cptdataset(str(args.source))
    output = save_netcdf(
        dataset, args.destination, metadata=metadata,
        compression=args.compression, overwrite=args.overwrite,
    )
    print(f"Saved and verified: {output}")


if __name__ == "__main__":
    main()
