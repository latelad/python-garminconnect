#!/usr/bin/env bash

set -euo pipefail

# Number of days to refresh.
# Usage:
#   ./custom/update_garmin.sh
#   ./custom/update_garmin.sh 35
DAYS="${1:-35}"

# Find repository root based on this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${REPO_ROOT}/.venv/Scripts/python.exe"
HEALTH_SCRIPT="${SCRIPT_DIR}/export_health.py"
ACTIVITY_SCRIPT="${SCRIPT_DIR}/export_activities.py"

if ! [[ "${DAYS}" =~ ^[0-9]+$ ]] || [[ "${DAYS}" -lt 1 ]]; then
    echo "Error: days must be a positive integer."
    echo "Usage: ./custom/update_garmin.sh [days]"
    exit 1
fi

if [[ ! -f "${PYTHON}" ]]; then
    echo "Error: virtual-environment Python was not found:"
    echo "  ${PYTHON}"
    echo
    echo "Create the virtual environment first:"
    echo "  py -m venv .venv --copies"
    echo "  source .venv/Scripts/activate"
    echo "  pip install -e ."
    exit 1
fi

if [[ ! -f "${HEALTH_SCRIPT}" ]]; then
    echo "Error: health exporter not found:"
    echo "  ${HEALTH_SCRIPT}"
    exit 1
fi

if [[ ! -f "${ACTIVITY_SCRIPT}" ]]; then
    echo "Error: activity exporter not found:"
    echo "  ${ACTIVITY_SCRIPT}"
    exit 1
fi

echo "Garmin data update"
echo "=================="
echo "Repository : ${REPO_ROOT}"
echo "Lookback   : ${DAYS} days"
echo

echo "[1/2] Updating health/recovery data..."
"${PYTHON}" "${HEALTH_SCRIPT}" --days "${DAYS}" --update

echo
echo "[2/2] Updating activity data..."
"${PYTHON}" "${ACTIVITY_SCRIPT}" --days "${DAYS}" --update

echo
echo "Garmin update completed successfully."
echo
echo "Output files:"
echo "  ${SCRIPT_DIR}/output/garmin_health.csv"
echo "  ${SCRIPT_DIR}/output/garmin_activities.csv"
