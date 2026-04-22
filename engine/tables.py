# tables.py — Precomputed lookup tables for the Go engine
#
# All tables here are built ONCE when this module loads, then reused
# throughout the engine for O(1) lookups.
#
# Why precompute? Operations like "find all neighbors of this intersection" are
# called millions of times during search. Computing them once and caching the
# results makes the engine much faster.
#
# These tables use KataGo's loc index: (x+1) + (board_size+1)*(y+1)
# That formula adds a 1-cell padding border around the board so the engine
# can easily detect wall cells without bounds checks.

from constants import board_size
from board import Board

# Create a temporary Board just to use its coordinate helpers and constants.
# We delete it at the bottom of the file once all tables are built.
_tmp_board = Board(board_size)
_DY = _tmp_board.dy        # Stride used to convert (x,y) to loc index
_ARRSIZE = _tmp_board.arrsize  # Total size of the internal board array (includes border)

# ---------------------------------------------------------------------------
# ADJACENT[loc] — tuple of orthogonal neighbor locs
#
# For each intersection 'loc', ADJACENT[loc] lists up to 4 neighbors
# (up, down, left, right) that are actually ON the board (not walls).
# This lets the engine check neighbors in O(1) instead of computing each time.
# ---------------------------------------------------------------------------
ADJACENT = [()] * _ARRSIZE
for _y in range(board_size):
    for _x in range(board_size):
        _loc = _tmp_board.loc(_x, _y)
        _adj = []
        # board.adj contains offsets for up/down/left/right in loc-space.
        for _dloc in _tmp_board.adj:
            _neighbor = _loc + _dloc
            # Only include the neighbor if it's on the actual board (not a wall cell).
            if _tmp_board.is_on_board(_neighbor):
                _adj.append(_neighbor)
        ADJACENT[_loc] = tuple(_adj)

# ---------------------------------------------------------------------------
# DISTANCE_2[loc] — frozenset of cells within Chebyshev distance 2
#
# Chebyshev distance 2 means all cells within a 5×5 square centered on loc
# (including diagonals). Used by the evaluator to spread influence.
# ---------------------------------------------------------------------------
DISTANCE_2 = [frozenset()] * _ARRSIZE
for _y in range(board_size):
    for _x in range(board_size):
        _loc = _tmp_board.loc(_x, _y)
        _cells = set()
        # Check all offsets from -2 to +2 in both x and y.
        for _dy in range(-2, 3):
            for _dx in range(-2, 3):
                _nx, _ny = _x + _dx, _y + _dy
                # Make sure the neighbor is within board bounds.
                if 0 <= _nx < board_size and 0 <= _ny < board_size:
                    _neighbor = _tmp_board.loc(_nx, _ny)
                    if _neighbor != _loc:  # Exclude the cell itself
                        _cells.add(_neighbor)
        DISTANCE_2[_loc] = frozenset(_cells)

# ---------------------------------------------------------------------------
# IS_EDGE[loc], IS_CORNER[loc]
#
# Quick boolean lookups. IS_EDGE[loc] is True if the intersection is on
# any edge of the board. IS_CORNER[loc] is True only for the four corner cells.
# Used by the evaluator to adjust scores (edge/corner stones are weaker).
# ---------------------------------------------------------------------------
IS_EDGE = [False] * _ARRSIZE
IS_CORNER = [False] * _ARRSIZE
for _y in range(board_size):
    for _x in range(board_size):
        _loc = _tmp_board.loc(_x, _y)
        _on_edge = (_x == 0 or _x == board_size - 1 or _y == 0 or _y == board_size - 1)
        _is_corner = (_x == 0 or _x == board_size - 1) and (_y == 0 or _y == board_size - 1)
        IS_EDGE[_loc] = _on_edge
        IS_CORNER[_loc] = _is_corner

# ---------------------------------------------------------------------------
# STAR_POINTS_9x9 — set of star point locs
#
# The five hoshi (star point) intersections on a 9×9 board,
# stored as engine locs for fast membership testing.
# ---------------------------------------------------------------------------
STAR_POINTS_9x9 = frozenset({
    _tmp_board.loc(2, 2),
    _tmp_board.loc(2, 6),
    _tmp_board.loc(4, 4),
    _tmp_board.loc(6, 2),
    _tmp_board.loc(6, 6),
})

# ---------------------------------------------------------------------------
# Manhattan distance for locs
# ---------------------------------------------------------------------------
def manhattan(loc1: int, loc2: int) -> int:
    """Manhattan distance between two board locs."""
    # KataGo loc: (x+1) + dy*(y+1)
    # x = (loc % dy) - 1, y = (loc // dy) - 1
    # We recover (x, y) by reversing the loc formula, then compute |Δx| + |Δy|.
    x1, y1 = (loc1 % _DY) - 1, (loc1 // _DY) - 1
    x2, y2 = (loc2 % _DY) - 1, (loc2 // _DY) - 1
    return abs(x1 - x2) + abs(y1 - y2)

# Cleanup temporary variables so they don't pollute the module's namespace.
del _tmp_board, _DY, _ARRSIZE, _x, _y, _loc, _adj, _neighbor, _cells, _dx, _dy, _nx, _ny, _on_edge, _is_corner
