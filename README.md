# TESS Light Curve Downloader

A Python command-line program to query the available TESS light-curve products for a list of TIC IDs, select the most suitable product for each target, generate download scripts, and download the resulting light curves from MAST.

The program is designed for large target lists and supports multiprocessing for the product-search and selection stage, as well as multiple simultaneous download scripts.

## Project Structure

```text
tess_lc_downloader/
├── src/
│   └── tess_lc_downloader/
│       ├── tess_lc_downloader.py
│       ├── scripts/
│       │   └── run_batches.sh
│       └── tests/
│           └── test_multi.csv
```

## Testing

An integration test is provided in:

```text
src/tess_lc_downloader/tests/test.sh
```

The test uses the sample input file:

```text
src/tess_lc_downloader/tests/test_multi.csv
```

and checks the main components of the program, including:

* Input handling.
* Multiprocessing execution.
* Worker logs.
* Consolidated metadata files.
* Generated download scripts.
* Download directory structure.
* `run_batches.sh` execution.

From the project directory, make the test executable if necessary:

```bash
chmod +x src/tess_lc_downloader/tests/test.sh
```

Then run:

```bash
./src/tess_lc_downloader/tests/test.sh
```

The test uses a small sample dataset and is intended as a smoke/integration test rather than a performance benchmark.


### Main components

* `tess_lc_downloader.py`: Main Python program.
* `scripts/run_batches.sh`: Bash utility used to execute several generated download scripts concurrently.
* `tests/test_multi.csv`: Example input file for testing the program.

The program also creates the following directories at runtime:

```text
LOGS/
CONSOLIDATED/
SCRIPTS/
FAILED/
LIGHTCURVES_c/
```

These directories are generated in the working directory when the program starts.

## Requirements

The program requires:

* Linux
* Python 3
* `pandas`
* `numpy`
* `lightkurve`
* `astropy`
* `psutil`

Multiprocessing additionally requires the `pyconfigs` package containing `ResourceAwarePool`.

The program uses Lightkurve to query TESS data products available through MAST.

## Input

The program accepts either:

1. A file containing TIC IDs.
2. A single TIC ID.

These two modes are mutually exclusive.

### Input file

The input file must contain the TIC IDs in its first column.

The first column is read as strings to avoid numerical precision loss:

```text
id_tess
262875675
279741694
197803556
262843455
...
```

Additional columns are allowed; only the first column is used.

### Single TIC ID

A single target can be provided directly:

```bash
python3 tess_lc_downloader.py -i 262875675
```

## Command-Line Arguments

### `-f`, `--file`

Path to the input file containing the TIC IDs.

```bash
-f FILE
```

### `-i`, `--id`

Single TIC ID.

```bash
-i TIC_ID
```

### `-m`, `--multiprocessing`

Enable multiprocessing.

The three arguments are:

```text
WORKERS CPU_MAX RAM_MAX
```

For example:

```bash
-m 16 0.7 0.7
```

where:

* `WORKERS`: Maximum number of parallel workers.
* `CPU_MAX`: Maximum allowed CPU usage fraction.
* `RAM_MAX`: Maximum allowed RAM usage fraction.

The program splits the input targets into batches and processes the batches using `ResourceAwarePool`.

### `-c`, `--cache_dir`

Root directory where the Lightkurve cache is stored.

Default:

```text
.
```

The program creates:

```text
.cache/lightkurve/mastDownload/
```

inside the specified directory.

For example:

```bash
-c /datos/scratch/user
```

results in a cache directory under:

```text
/datos/scratch/user/.cache/lightkurve/mastDownload/
```

### `-d`, `--downloaders`

Number of download scripts that may run simultaneously.

Default:

```text
3
```

For example:

```bash
-d 4
```

allows four generated `.sh` scripts to run concurrently.

## Example

A typical execution is:

```bash
python3 tess_lc_downloader.py \
    -f tests/test_multi.csv \
    -m 16 0.7 0.7 \
    -c /datos/scratch/user \
    -d 4
```

The program performs the following stages:

```text
Input
  ↓
Read TIC IDs
  ↓
Split targets into batches
  ↓
Search MAST with multiprocessing
  ↓
Select the best light-curve products
  ↓
Create consolidated metadata
  ↓
Generate download scripts
  ↓
Run download scripts in parallel
  ↓
Download FITS files into the final directory structure
```

## Light-Curve Selection

For every TIC ID, the program queries the TESS products available through MAST.

The selection procedure is based on:

1. Shortest available exposure time.
2. Maximum number of consecutive sectors.
3. Preferred author/pipeline order.

The preferred authors are:

```text
TASOC
SPOC
QLP
TGLC
GSFC-ELEANOR-LITE
CDIPS
```

The selected product information is stored in the consolidated files.

## Multiprocessing

When multiprocessing is enabled, the target list is split into batches.

For example, with:

```text
10 targets
3 workers
```

the input may be divided into:

```text
Worker/batch 0 → targets 0–3
Worker/batch 1 → targets 4–7
Worker/batch 2 → targets 8–9
```

Each batch produces its own output files.

The `ResourceAwarePool` dynamically controls task submission according to the requested CPU and RAM limits.

## Generated Files

### Worker logs

Each processing batch generates its own log:

```text
LOGS/
├── log_000.log
├── log_001.log
├── log_002.log
└── ...
```

The logs contain information about the processing of the targets assigned to that batch.

### Consolidated files

Each batch produces a metadata file:

```text
CONSOLIDATED/
├── lc_consolidated_000.csv
├── lc_consolidated_001.csv
├── lc_consolidated_002.csv
└── ...
```

After all batches finish, these files are merged into:

```text
stars_consolidated.csv
```

### Generated download scripts

Each batch produces a Bash script:

```text
SCRIPTS/
├── lc_bulk_downloader_000.sh
├── lc_bulk_downloader_001.sh
├── lc_bulk_downloader_002.sh
└── ...
```

Each script contains the `curl` commands required to download the selected light curves.

The scripts are generated with:

```sh
#!/bin/sh
```

and are executed through `run_batches.sh`.

## Download Organization

Downloaded FITS files are stored directly in a two-level directory hierarchy based on their TIC ID.

For example:

```text
TIC 262875675
```

is stored under:

```text
LIGHTCURVES_c/
└── 262/
    └── 875675/
```

A resulting file may look like:

```text
LIGHTCURVES_c/
└── 262/
    └── 875675/
        ├── TIC_262875675_S95_200.0s_QLP_lc.fits
        ├── TIC_262875675_S96_200.0s_QLP_lc.fits
        └── TIC_262875675_S97_200.0s_QLP_lc.fits
```

The directories are created by Python before the corresponding download commands are executed.

## Downloading

The generated scripts are executed by:

```text
scripts/run_batches.sh
```

This script receives:

```text
number_of_workers
script_1
script_2
...
```

and executes at most the requested number of download scripts simultaneously.

For example:

```bash
./scripts/run_batches.sh 3 \
    ./SCRIPTS/lc_bulk_downloader_000.sh \
    ./SCRIPTS/lc_bulk_downloader_001.sh \
    ./SCRIPTS/lc_bulk_downloader_002.sh \
    ./SCRIPTS/lc_bulk_downloader_003.sh
```

Three scripts are started initially. Once all three finish, the next group is started.

Therefore, the `-d` option controls the number of simultaneously running download scripts, not the number of `curl` processes inside each script.

## Failed Targets

Targets for which no suitable product can be obtained are recorded in:

```text
FAILED/
```

Each processing batch has its own failure file:

```text
FAILED/
├── FAILED_000.csv
├── FAILED_001.csv
└── ...
```

The TIC ID of each failed target is written to the corresponding file.

## Logging

The main program uses a general log:

```text
lc_downloader_general.log
```

Worker-specific logs are stored under:

```text
LOGS/
```

The worker logger records messages using the following format:

```text
timestamp - level - function - message
```

The `ResourceAwarePool` also maintains its own multiprocessing logging mechanism for reporting internal process-management events.

## Cache

Lightkurve is configured to use a local cache:

```text
.cache/lightkurve/mastDownload/
```

This avoids unnecessarily repeating downloaded MAST query information and allows Lightkurve to reuse cached data where appropriate.

The cache location can be changed with:

```bash
-c /path/to/cache/root
```

## Example Test Input

A small test file is provided under:

```text
tests/test_multi.csv
```

It contains a set of TIC targets together with additional stellar metadata and can be used to test the complete workflow.

A typical test execution is:

```bash
python3 tess_lc_downloader.py \
    -f tests/test_multi.csv \
    -m 2 0.7 0.7 \
    -c . \
    -d 1
```

## Workflow Summary

The complete workflow is:

```text
                 ┌──────────────────┐
                 │    Input file     │
                 │     TIC IDs       │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │   Read targets   │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ Split into       │
                 │ processing       │
                 │ batches          │
                 └────────┬─────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
           Worker 0    Worker 1    Worker N
              │           │           │
              ▼           ▼           ▼
          Query MAST   Query MAST   Query MAST
              │           │           │
              ▼           ▼           ▼
          Select LC     Select LC    Select LC
              │           │           │
              ▼           ▼           ▼
           CSV + SH    CSV + SH     CSV + SH
              │           │           │
              └───────────┼───────────┘
                          ▼
                Consolidated metadata
                          │
                          ▼
                 Download scripts
                          │
                          ▼
                run_batches.sh
                          │
                  ┌───────┴───────┐
                  ▼       ▼       ▼
               script  script  script
                  │       │       │
                  └───────┼───────┘
                          ▼
                    FITS files
                          │
                          ▼
                 LIGHTCURVES_c/
```

## Notes

The program is currently designed for Linux systems.

The search and selection stage is separated from the download stage so that the MAST queries can be completed first and the resulting download scripts can subsequently be executed with a configurable level of parallelism.
