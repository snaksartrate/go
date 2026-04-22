# utility_functions.py — Miscellaneous helper functions used across the engine
#
# These are small, self-contained utilities that don't belong in any specific
# module. Think of this as a "toolbox" file.

import constants as C
import tables as T
from board import Board

# Cache the board size locally so we don't keep calling C.board_size everywhere.
board_size = C.board_size

def is_valid_notation(notation : str, board_size = board_size) -> bool:
    # Checks whether a string representation of a board position has exactly
    # board_size² characters (one character per intersection).
    # For a 9×9 board that is 81 characters.
    if len(notation) != board_size * board_size:
        return False
    # Note: This checks characters '0', '1', '2' or similar defined in constants
    # Valid characters should be checked against C.valid_notation_chars if it exists
    return True 

def adjacent(source : int) -> list[int]:
    """Returns adjacent locs for a given board loc."""
    # ADJACENT is a precomputed table (from tables.py) that lists the up/down/left/right
    # neighbors for each board intersection. This avoids recomputing them every time.
    return list(T.ADJACENT[source])

def dfs(grid : list, source : int) -> set[int]:
    """Perform DFS on a grid indexed by loc."""
    # Depth-first search starting from 'source'.
    # Visits every connected intersection that has the same color as the source.
    # Returns the set of all such connected intersections (i.e. a connected group).
    colour = grid[source]
    unit = {source}
    stack = [source]
    visited = [False] * len(grid)
    visited[source] = True
    while stack:
        curr = stack.pop()
        # Check all four orthogonal neighbors of the current intersection.
        for adj in adjacent(curr):
            # Only expand to neighbors that are the same color and not yet visited.
            if adj < len(grid) and grid[adj] == colour and not visited[adj]:
                visited[adj] = True
                stack.append(adj)
                unit.add(adj)
    return unit

def index(row, col) -> int:
    """Returns local flat index (0-80). Note: Use Board.loc() for engine work."""
    # Converts a (row, col) pair into a single integer index from 0 to 80.
    # This is a simple row-major flat index — NOT the same as KataGo's loc format,
    # which adds padding borders. Use Board.loc(x, y) when interfacing with Board.
    return row * board_size + col
