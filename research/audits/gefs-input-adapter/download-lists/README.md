# CHIRPS3 Final daily download lists

**Regional alternative:** the user now prefers
[Earth Engine Indonesia subsets](../../../scripts/gee/README.md). That script
prepares a small source-comparison pilot first; live GEE exports and comparison
are pending. These global URL lists are retained as a fallback.

Generated 2026-11-02 for the proposed GEFSv12 Wednesday initialization cohorts:
hindcasts2000-2018 and archived forecasts2023-2025; lead weeks2/3/4. rnl is the
primary reference; sat supplies sensitivity. No fits or TIFF downloads ran.

| List | TIFF URLs | Observation dates, inclusive |
| --- | ---: | --- |
| [chirps3-rnl.txt](chirps3-rnl.txt) | 8,064 | 2000-01-12–2019-01-22 and 2023-01-11–2026-01-27 |
| [chirps3-sat.txt](chirps3-sat.txt) | 8,064 | Same dates |

The lists contain only absolute URLs, one per line, ASCII with LF endings,
sorted by date and deduplicated. Shared dates across starts/leads occur once.
Each initialization contributes UTC date offsets7..27 inclusive, corresponding
to half-open weekly targets [7,14), [14,21), [21,28). January2019/2026 is required
by late-year issues. These are global0.05degree GeoTIFFs; Indonesia is subset later.

## PowerShell (installed GNU wget.exe)

```powershell
Set-Location 'C:\Users\benny\OneDrive\Documents\Github\pycpt-tutorial\research\audits\gefs-input-adapter\download-lists'
$ca = 'C:\Users\benny\miniforge3\Lib\site-packages\certifi\cacert.pem'
wget.exe -c -i chirps3-rnl.txt -P 'H:\temp\chirps\daily\rnl' --ca-certificate="$ca" --timeout=60 --tries=5 --wait=1
wget.exe -c -i chirps3-sat.txt -P 'H:\temp\chirps\daily\sat' --ca-certificate="$ca" --timeout=60 --tries=5 --wait=1
```

Keep each command on one line. Change the destination paths as needed. Each
variant folder contains original filenames directly, without year subfolders.
Run rnl first, then sat. Ctrl+C interrupts; rerun the same command to resume with
`-c`. Leave the URL lists unchanged while a download is running.

### Windows certificate verification fix

The initial command failed with "Unable to locally verify the issuer's authority".
The installed `C:\apps\gnuwin64\wget.exe` was then tested using `--spider` with
the existing Miniforge Python certifi CA bundle above: the first rnl URL returned
HTTP200, with certificate verification enabled and no TIFF body downloaded.
No system trust settings or global wget configuration were changed. Evidence:
[wget-tls-check.json](wget-tls-check.json).

`--ca-certificate` supplies the PEM trust bundle used to verify the server;
see the [GNU Wget HTTPS options](https://www.gnu.org/software/wget/manual/html_node/HTTPS-_0028SSL_002fTLS_0029-Options.html).
This bundle path was verified on this computer. On another installation, locate
the equivalent bundle with `python -c "import certifi; print(certifi.where())"`.
If a download is still printing certificate failures, stop it with Ctrl+C and
restart with the corrected command. The lists themselves are unchanged.

## Debian / WSL alternative

Using the usual Windows-drive mounts:

```bash
cd /mnt/c/Users/benny/OneDrive/Documents/Github/pycpt-tutorial/research/audits/gefs-input-adapter/download-lists
wget -c -i chirps3-rnl.txt -P /mnt/h/temp/chirps/daily/rnl --timeout=60 --tries=5 --wait=1
wget -c -i chirps3-sat.txt -P /mnt/h/temp/chirps/daily/sat --timeout=60 --tries=5 --wait=1
```

Both variants total16,128 files, approximately276.5GB based on the input-check
sample. This is an estimate, not a quota or exact expected size. The lists check
filename availability, not completed download integrity or country-pixel coverage.
After downloading, validate the TIFFs, dates, georeferencing, missingness and
country support before building training inputs. wget continuation alone is not
scientific validation.

## Provenance and regeneration

[download-manifest.json](download-manifest.json) records source/list hashes,
cohort/date counts and successful live HEAD probes of eight span endpoints.
All16,128 filenames were checked against the saved official annual directory
census; intermediate URLs were not individually probed live. HEAD fetched no
TIFF bodies. Original source is the [CHC CHIRPS3 daily archive](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/).

From the repository root, Python standard library only:

```bash
python research/scripts/make_chirps3_download_lists.py
# Optional: also check the eight span endpoints with HEAD requests.
python research/scripts/make_chirps3_download_lists.py --check-links
```

An offline regeneration leaves `head_checks` empty in the new manifest; it does
not imply a new live availability check. Generating/download preparation does
not select a fitting protocol or change the proposed-period status.
