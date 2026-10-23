#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROGRAM="$PROJECT_ROOT/src/tess_lc_downloader/tess_lc_downloader.py"
INPUT="$PROJECT_ROOT/src/tess_lc_downloader/tests/test_multi.csv"

echo "=========================================="
echo " TEST: tess_lc_downloader"
echo "=========================================="

echo
echo "[1/7] Checking project files..."

test -f "$PROGRAM"
test -f "$INPUT"
test -f "$PROJECT_ROOT/src/tess_lc_downloader/scripts/run_batches.sh"

echo "OK"

echo
echo "[2/7] Checking run_batches.sh permissions..."

if [[ ! -x "$PROJECT_ROOT/src/tess_lc_downloader/scripts/run_batches.sh" ]]; then
    echo "ERROR: run_batches.sh is not executable."
    exit 1
fi

echo "OK"

echo
echo "[3/7] Cleaning previous test output..."

rm -rf \
    "$PROJECT_ROOT/LOGS" \
    "$PROJECT_ROOT/CONSOLIDATED" \
    "$PROJECT_ROOT/SCRIPTS" \
    "$PROJECT_ROOT/FAILED" \
    "$PROJECT_ROOT/LIGHTCURVES_c" \
    "$PROJECT_ROOT/.test_cache" \
    "$PROJECT_ROOT/lc_downloader_general.log" \
    "$PROJECT_ROOT/stars_consolidated.csv"

echo "OK"

echo
echo "[4/7] Running program..."

cd "$PROJECT_ROOT"

python3 "$PROGRAM" \
    -f "$INPUT" \
    -m 2 0.7 0.7 \
    -c "$PROJECT_ROOT/.test_cache" \
    -d 1

echo "Program finished."

echo
echo "[5/7] Checking output directories..."

for directory in \
    LOGS \
    CONSOLIDATED \
    SCRIPTS \
    FAILED \
    LIGHTCURVES_c
do
    if [[ ! -d "$PROJECT_ROOT/$directory" ]]; then
        echo "ERROR: Missing directory: $directory"
        exit 1
    fi
done

echo "OK"

echo
echo "[6/7] Checking generated files..."

# General log
test -f "$PROJECT_ROOT/lc_downloader_general.log"

# Worker logs
worker_logs=("$PROJECT_ROOT"/LOGS/log_*.log)

# Consolidated files
consolidated_files=("$PROJECT_ROOT"/CONSOLIDATED/lc_consolidated_*.csv)

# Downloader scripts
download_scripts=("$PROJECT_ROOT"/SCRIPTS/lc_bulk_downloader_*.sh)

if [[ ${#worker_logs[@]} -ne 2 ]]; then
    echo "ERROR: Expected 2 worker logs, found ${#worker_logs[@]}"
    exit 1
fi

if [[ ${#consolidated_files[@]} -ne 2 ]]; then
    echo "ERROR: Expected 2 consolidated files, found ${#consolidated_files[@]}"
    exit 1
fi

if [[ ${#download_scripts[@]} -ne 2 ]]; then
    echo "ERROR: Expected 2 downloader scripts, found ${#download_scripts[@]}"
    exit 1
fi

# Final consolidated catalogue
test -f "$PROJECT_ROOT/stars_consolidated.csv"

echo "OK"

echo
echo "[7/7] Checking generated downloader scripts..."

for script in "${download_scripts[@]}"; do

    # Correct shebang
    if ! grep -q '^#!/bin/sh' "$script"; then
        echo "ERROR: Invalid shebang in $script"
        exit 1
    fi

    # At least one curl command
    if ! grep -q '^curl ' "$script"; then
        echo "ERROR: No curl command found in $script"
        exit 1
    fi

    # Downloads should target LIGHTCURVES_c
    if ! grep -q '/LIGHTCURVES_c/' "$script"; then
        echo "ERROR: Script does not contain a LIGHTCURVES_c destination: $script"
        exit 1
    fi

done

echo "OK"

echo
echo "=========================================="
echo " TEST PASSED SUCCESSFULLY"
echo "=========================================="
