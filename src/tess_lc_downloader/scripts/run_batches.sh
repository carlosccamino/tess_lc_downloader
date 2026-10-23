#!/bin/bash

# Usage:
#   ./run_batches.sh N script1.sh script2.sh script3.sh ...

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <workers> <script1.sh> [script2.sh ...]"
    exit 1
fi

workers="$1"
shift

# Check that workers is a positive integer
if ! [[ "$workers" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: workers must be a positive integer"
    exit 1
fi

scripts=("$@")

for ((i=0; i<${#scripts[@]}; i+=workers)); do

    echo "========================================"
    echo "Starting batch:"
    echo "========================================"

    pids=()

    # Launch up to 'workers' scripts
    for ((j=i; j<i+workers && j<${#scripts[@]}; j++)); do
        script="${scripts[j]}"

        if [[ ! -f "$script" ]]; then
            echo "ERROR: file not found: $script"
            continue
        fi

        echo "→ Starting $script"
        sh "$script" &
        pids+=("$!")
    done

    # Wait for all scripts in the batch to finish
    for pid in "${pids[@]}"; do
        wait "$pid"
    done

    echo "Batch finished."
    echo
done

echo "All scripts have finished."