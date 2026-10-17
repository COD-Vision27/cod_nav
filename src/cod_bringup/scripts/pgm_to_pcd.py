#!/usr/bin/env python3
"""Convert a 2D occupancy grid (PGM + nav2 map YAML) into a 3D PCD point cloud.

Used to build a `prior_pcd_file` for small_gicp_relocalization from an
existing nav2 map, so the relocalizer has a target to align scans against.

A 2D grid has no vertical structure: every point lands on one plane. Extruding
occupied cells in Z (--z-max > --z-min) turns each wall pixel into a vertical
surface, which gives GICP something to constrain roll/pitch/z against.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image


def parse_map_yaml(path):
    """Parse the handful of keys nav2's map_server cares about, no yaml dep."""
    raw = {}
    with open(path) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line or ':' not in line:
                continue
            key, value = line.split(':', 1)
            raw[key.strip()] = value.strip()

    def need(key):
        if key not in raw:
            sys.exit(f"error: '{key}' missing from {path}")
        return raw[key]

    origin = json.loads(need('origin'))
    if len(origin) < 2:
        sys.exit(f"error: 'origin' in {path} needs at least [x, y]")
    return {
        'resolution': float(need('resolution')),
        'origin': (float(origin[0]), float(origin[1])),
        'negate': int(need('negate')),
        'occupied_thresh': float(raw.get('occupied_thresh', 0.65)),
        'free_thresh': float(raw.get('free_thresh', 0.196)),
    }


def load_grid(pgm_path, params):
    image = Image.open(pgm_path).convert('L')
    grid = np.asarray(image, dtype=np.float64)
    if params['negate']:
        p = grid / 255.0
    else:
        p = (255.0 - grid) / 255.0

    occupied = p > params['occupied_thresh']
    free = p < params['free_thresh']
    unknown = ~occupied & ~free
    return {'occupied': occupied, 'free': free, 'unknown': unknown}


def cells_to_xy(mask, params):
    """Map image (row, col) -> world (x, y). Row 0 is the top row, i.e. max y."""
    res = params['resolution']
    ox, oy = params['origin']
    rows, cols = mask.shape
    row, col = np.nonzero(mask)
    x = ox + (col + 0.5) * res
    y = oy + (rows - row - 0.5) * res
    return x, y


def extrude_z(x, y, z_min, z_max, z_step):
    if z_max <= z_min:
        return x, y, np.full_like(x, z_min)
    levels = np.arange(z_min, z_max + z_step * 0.5, z_step)
    x = np.tile(x, levels.size)
    y = np.tile(y, levels.size)
    z = np.repeat(levels, x.size // levels.size)
    return x, y, z


def voxel_downsample(x, y, z, voxel):
    keys = np.stack(
        [np.round(x / voxel), np.round(y / voxel), np.round(z / voxel)], axis=1)
    _, idx = np.unique(keys, axis=0, return_index=True)
    return x[idx], y[idx], z[idx]


def write_pcd(path, xyz, binary):
    count = xyz.shape[0]
    header = [
        '# .PCD v0.7 - Point Cloud Data file format',
        'VERSION 0.7',
        'FIELDS x y z',
        'SIZE 4 4 4',
        'TYPE F F F',
        'COUNT 1 1 1',
        f'WIDTH {count}',
        'HEIGHT 1',
        'VIEWPOINT 0 0 0 1 0 0 0',
        f'POINTS {count}',
        'DATA ' + ('binary' if binary else 'ascii'),
    ]
    text = '\n'.join(header) + '\n'
    if binary:
        with open(path, 'wb') as f:
            f.write(text.encode('ascii'))
            f.write(xyz.astype('<f4').tobytes())
    else:
        with open(path, 'w') as f:
            f.write(text)
            np.savetxt(f, xyz, fmt='%.6f')


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pgm', help='input occupancy grid (.pgm)')
    parser.add_argument('--yaml', help='nav2 map yaml (default: same basename)')
    parser.add_argument('-o', '--output', help='output .pcd (default: <pgm>.pcd)')
    parser.add_argument('--include', default='occupied',
                        choices=['occupied', 'free', 'unknown', 'all'],
                        help='which cells to convert (default: occupied)')
    parser.add_argument('--z-min', type=float, default=0.0,
                        help='lower Z of the extruded walls (default: 0.0)')
    parser.add_argument('--z-max', type=float, default=0.0,
                        help='upper Z; > z-min extrudes walls vertically')
    parser.add_argument('--z-step', type=float, default=0.1,
                        help='Z spacing when extruding (default: 0.1)')
    parser.add_argument('--voxel', type=float, default=0.0,
                        help='voxel-downsample size, 0 disables (default: 0)')
    parser.add_argument('--binary', action='store_true',
                        help='write binary PCD instead of ascii')
    args = parser.parse_args()

    yaml_path = args.yaml or os.path.splitext(args.pgm)[0] + '.yaml'
    if not os.path.isfile(yaml_path):
        sys.exit(f"error: no map yaml at {yaml_path} (pass --yaml)")
    params = parse_map_yaml(yaml_path)

    if args.z_max > args.z_min and args.z_step <= 0.0:
        sys.exit("error: --z-step must be > 0 when extruding")

    grids = load_grid(args.pgm, params)
    mask = (np.ones_like(grids['occupied']) if args.include == 'all'
            else grids[args.include])
    if not mask.any():
        sys.exit(f"error: no '{args.include}' cells in {args.pgm}")

    x, y = cells_to_xy(mask, params)
    x, y, z = extrude_z(x, y, args.z_min, args.z_max, args.z_step)
    if args.voxel > 0.0:
        x, y, z = voxel_downsample(x, y, z, args.voxel)

    xyz = np.column_stack([x, y, z]).astype(np.float32)
    out = args.output or os.path.splitext(args.pgm)[0] + '.pcd'
    write_pcd(out, xyz, args.binary)

    span = xyz.max(axis=0) - xyz.min(axis=0)
    print(f"wrote {xyz.shape[0]} points to {out}")
    print(f"  include={args.include} extent(m)={np.round(span, 2)}")


if __name__ == '__main__':
    main()
