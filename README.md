# sts-module-test

Tools for indexing and collecting STS module-test results and for analyzing pulse-scan data.
The repository contains two import packages:

- `module_test`: result parsing, remote file indexing, and calibration/mask generation.
- `pscan`: S-curve fitting, quality rules, and plotting used by `run_p_scan.py`.

The shared `sts_utils` implementation remains a separate repository and is installed as a
dependency rather than copied here.

## Installation

Python 3.10 or newer is required. From this repository root, when it is checked out
beside `sts_utils`, install both editable repositories into the same environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ../sts_utils -e '.[test]'
```

If this repository and `sts_utils` are checked out elsewhere, replace `../sts_utils`
with that checkout's path.

## Module-test file index

Build an SQLite index of test files available through SSH:

```sh
sts-module-test-index --host HOST --path REMOTE_ROOT --db file_index.db
```

Refresh an existing index with `--sync`. The indexed layout must be:

```text
REMOTE_ROOT/
  LADDER_NAME/
    MODULE_NAME/
      pscan_files/
        module_test_MODULE_NAME.txt
```

## Collect results

Run the collector with the Python interpreter from the installation environment above.
Running from the source checkout alone does not make the sibling `sts_utils` package
importable. If you see `ModuleNotFoundError: No module named 'sts_utils'`, install both
packages as shown above, then verify with `python -m module_test.collect_results --help`.

In a POSIX shell, keep the trailing `\` on every continued line except the last:

```sh
python -m module_test.collect_results \
  --host HOST \
  --path REMOTE_ROOT \
  --db file_index.db
```

The collector uses `test_result/` as its local mount point and writes
`channelMask.par`, `chargeCalibration.par`, and an address dump in the current working
directory. These runtime products are ignored by Git.

## Pulse-scan analysis

Place pulse-scan input files in `sources/`, then run from the repository root:

```sh
sts-p-scan
# Equivalent:
python run_p_scan.py
```

The analysis writes logs and generated plots/summaries beneath the current working
directory. Those directories are ignored by Git.

## Tests

```sh
python -m pytest -q
```

## Broken-channel reporting

Add `--broken-channel-report` to the collector command to generate both channel-position and broken-channels-per-module histograms, independently for P and N sides and each reason. Use `--histogram-type channel|module|both`, `--report-dir PATH`, and `--report-format png|pdf|svg` to customize output. Defaults: both, summary/broken_channels, png.

CSV exports include all successfully parsed modules, individual classifications, per-module counts and statistics. Empty reason in summary/count tables denotes all reasons. Missing source reasons are UNKNOWN; new reason labels are accepted. Channel indices use source numbering (0–1023); out-of-range entries are warned and excluded from reports only. Duplicate module addresses use the first result for reporting; repeated channel/reason pairs are counted once. A channel with conflicting classifications contributes once to the all-reasons total and once to each matching reason. Zero-count modules are included in module distributions. Existing masks, calibration, parser signatures and dataclass fields are unchanged.
