#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(dirname -- "$SCRIPT_DIR")
RETENTION_DAYS=${RETENTION_DAYS:-7}

case "$RETENTION_DAYS" in
    ''|*[!0-9]*)
        echo "RETENTION_DAYS must be a non-negative integer" >&2
        exit 2
        ;;
esac

RETENTION_MINUTES=$((RETENTION_DAYS * 24 * 60))

for directory in \
    "$PROJECT_ROOT/instance/source_docs" \
    "$PROJECT_ROOT/instance/output_docs"
do
    [ -d "$directory" ] || continue
    find "$directory" -type f -mmin "+$RETENTION_MINUTES" -print -delete
done
