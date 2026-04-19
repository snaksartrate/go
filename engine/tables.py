# tables.py — Precomputed lookup tables for the Go engine
# These tables use KataGo's loc index: (x+1) + (board_size+1)*(y+1)

from constants import board_size
from board import Board

# Instantiate a temporary board to get loc mappings and dy
_tmp_board = Board(board_size)
_DY = _tmp_board.dy
_ARRSIZE = _tmp_board.arrsize

# ---------------------------------------------------------------------------
# ADJACENT[loc] — tuple of orthogonal neighbor locs
# ---------------------------------------------------------------------------
ADJACENT = [()] * _ARRSIZE
for _y in range(board_size):
    for _x in range(board_size):
        _loc = _tmp_board.loc(_x, _y)
        _adj = []
        for _dloc in _tmp_board.adj:
            _neighbor = _loc + _dloc
            if _tmp_board.is_on_board(_neighbor):
                _adj.append(_neighbor)
        ADJACENT[_loc] = tuple(_adj)

# ---------------------------------------------------------------------------
# DISTANCE_2[loc] — frozenset of cells within Chebyshev distance 2
# ---------------------------------------------------------------------------
DISTANCE_2 = [frozenset()] * _ARRSIZE
for _y in range(board_size):
    for _x in range(board_size):
        _loc = _tmp_board.loc(_x, _y)
        _cells = set()
        for _dy in range(-2, 3):
            for _dx in range(-2, 3):
                _nx, _ny = _x + _dx, _y + _dy
                if 0 <= _nx < board_size and 0 <= _ny < board_size:
                    _neighbor = _tmp_board.loc(_nx, _ny)
                    if _neighbor != _loc:
                        _cells.add(_neighbor)
        DISTANCE_2[_loc] = frozenset(_cells)

# ---------------------------------------------------------------------------
# IS_EDGE[loc], IS_CORNER[loc]
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
    x1, y1 = (loc1 % _DY) - 1, (loc1 // _DY) - 1
    x2, y2 = (loc2 % _DY) - 1, (loc2 // _DY) - 1
    return abs(x1 - x2) + abs(y1 - y2)

# Cleanup
del _tmp_board, _DY, _ARRSIZE, _x, _y, _loc, _adj, _neighbor, _cells, _dx, _dy, _nx, _ny, _on_edge, _is_corner
