#!/usr/bin/env bash
#
# Build a prior PCD point cloud for small_gicp_relocalization from a nav2 PGM map.
#
#   ./pgm2pcd.sh
#       -> src/cod_bringup/maps/rmul2026.pgm  to  src/cod_bringup/maps/rmul2026_walls.pcd
#
#   ./pgm2pcd.sh <map.pgm> [extra pgm_to_pcd.py args...]
#
# Run from the workspace root (the directory holding this script).
# Walls are extruded 0 -> 1.2 m in Z so GICP has vertical structure to lock onto.
set -euo pipefail

WS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAP_DIR="${WS_DIR}/src/cod_bringup/maps"
CONVERTER="${WS_DIR}/src/cod_bringup/scripts/pgm_to_pcd.py"

if [ ! -f "${CONVERTER}" ]; then
  echo "error: converter not found: ${CONVERTER}" >&2
  echo "       run this script from the workspace root." >&2
  exit 1
fi

PGM="${1:-${MAP_DIR}/rmul2026.pgm}"
[ "$#" -ge 1 ] && shift

if [ ! -f "${PGM}" ]; then
  echo "error: no such map: ${PGM}" >&2
  exit 1
fi

OUT="${PGM%.pgm}_walls.pcd"
echo "converting ${PGM}"
echo "        -> ${OUT}"
python3 "${CONVERTER}" "${PGM}" --z-max 1.2 --z-step 0.1 -o "${OUT}" "$@"
