#!/usr/bin/env sh
# SPDX-License-Identifier: MIT
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$SCRIPT_DIR/backup.py" restore "$@"
