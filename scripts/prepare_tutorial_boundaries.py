"""Derive compact display-only overlays from the supplied administrative files."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

import shapefile
from shapely.geometry import box, mapping, shape
from shapely.validation import explain_validity, make_valid

ROOT = Path(__file__).resolve().parents[1]
EXTENT = [94, -12, 142, 7]
TOLERANCE = 0.01  # degrees: cartographic simplification, never an analysis mask


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("/mnt/f/temp/hybrid-bias-correction/data/subset/bnd"))
    args = parser.parse_args()
    dest = ROOT / "docs/data/boundaries"
    dest.mkdir(parents=True, exist_ok=True)
    bounds = box(*EXTENT)
    outputs, sources, repairs = {}, {}, []
    for source, layer in [("idn_bnd_adm0", "indonesia"), ("idn_bnd_adm1", "provinces"), ("wld_bnd_adm0", "neighbours")]:
        base = args.source_dir / source
        prj = base.with_suffix(".prj").read_text()
        assert 'GCS_WGS_1984' in prj, (source, prj)
        reader = shapefile.Reader(str(base), encoding="utf-8")
        features = []
        for record in reader.iterShapeRecords(bbox=EXTENT):
            attrs = record.record.as_dict()
            if layer == "neighbours" and attrs["iso_3"] == "IDN":
                continue
            geom = shape(record.shape.__geo_interface__)
            if not geom.is_valid:
                repairs.append({"source": source, "record": record.record.oid, "stage": "source", "reason": explain_validity(geom)})
                geom = make_valid(geom)
            geom = geom.simplify(TOLERANCE, preserve_topology=True).intersection(bounds)
            if geom.is_empty:
                continue
            if not geom.is_valid:
                repairs.append({"source": source, "record": record.record.oid, "stage": "display derivative", "reason": explain_validity(geom)})
                geom = make_valid(geom)
            assert geom.is_valid, source
            properties = ({"name": attrs["a1name"]} if layer == "provinces" else
                          {"name": attrs["adm0_name"], "iso3": attrs["iso_3"]} if layer == "neighbours" else
                          {"name": "Indonesia"})
            features.append({"type": "Feature", "properties": properties, "geometry": mapping(geom)})
        reader.close()
        target = dest / f"{layer}.geojson"
        target.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")) + "\n")
        outputs[target.name] = {"sha256": sha(target), "features": len(features), "bytes": target.stat().st_size}
        credits = []
        xml = base.with_suffix(".shp.xml")
        if xml.exists():
            credits = [(e.text or "").strip() for e in ET.parse(xml).iter() if e.tag == "idCredit" and (e.text or "").strip()]
        paths = [base.with_suffix(ext) for ext in (".shp", ".shx", ".dbf", ".prj")]
        if xml.exists(): paths.append(xml)
        sources[source] = {"directory": str(args.source_dir), "credits_from_metadata": credits,
                           "files": {p.name: sha(p) for p in paths}}
        print(f"{layer}: {len(features)} features, {target.stat().st_size:,} bytes", flush=True)
    assert outputs["indonesia.geojson"]["features"] == 1
    assert outputs["provinces.geojson"]["features"] == 38
    record = {"sources": sources, "outputs": outputs, "geometry_repairs": repairs, "coordinate_system": "WGS84 longitude/latitude (EPSG:4326)",
              "extent": EXTENT, "simplification_tolerance_degrees": TOLERANCE,
              "purpose": "Display-only overlays. Not used for masks, area weights, forecasts or verification.",
              "world_filter": "Exclude iso_3=IDN before clipping. Indonesia is outlined, never filled by the boundary layer."}
    (dest / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
