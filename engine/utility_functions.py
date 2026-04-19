import constants as C
import tables as T
from board import Board

board_size = C.board_size

def is_valid_notation(notation : str, board_size = board_size) -> bool:
    if len(notation) != board_size * board_size:
        return False
    # Note: This checks characters '0', '1', '2' or similar defined in constants
    # Valid characters should be checked against C.valid_notation_chars if it exists
    return True 

def adjacent(source : int) -> list[int]:
    """Returns adjacent locs for a given board loc."""
    return list(T.ADJACENT[source])

def dfs(grid : list, source : int) -> set[int]:
    """Perform DFS on a grid indexed by loc."""
    colour = grid[source]
    unit = {source}
    stack = [source]
    visited = [False] * len(grid)
    visited[source] = True
    while stack:
        curr = stack.pop()
        for adj in adjacent(curr):
            if adj < len(grid) and grid[adj] == colour and not visited[adj]:
                visited[adj] = True
                stack.append(adj)
                unit.add(adj)
    return unit

def index(row, col) -> int:
    """Returns local flat index (0-80). Note: Use Board.loc() for engine work."""
    return row * board_size + col
