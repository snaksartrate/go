from environment import Position, Board, Unit
from constants import board_size

def adjacent(source : int) -> list:
    adj = [source + 1, source - 1, source + board_size, source - board_size]
    limit = board_size * board_size
    return [a for a in adj if 0 <= a and a < limit]

def dfs(grid : list, source : int) -> set:
    colour = grid[source]
    unit = {source}
    stack = [source]
    visited = {source}
    curr = source
    while stack:
        curr = stack.pop()
        for adj in adjacent(curr):
            if grid[adj] == colour and adj not in visited:
                visited.add(adj)
                stack.append(adj)
                unit.add(adj)
    return unit

def generate_liberties(unit : Unit, grid : list):
    for cell in unit.unit:
        for adj in adjacent(cell):
            if not grid[adj]:
                unit.liberties.add(adj)
    unit.liberty_count = len(unit.liberties)

def get_units(board : Board) -> tuple[set[Unit], set[Unit]]:
    board_size = len(board.grid)
    black_units = set()
    white_units = set()
    for i in range(board_size * board_size):
        if not board.grid[i] or any(i in unit.unit for unit in black_units) or any(i in unit.unit for unit in white_units):
            continue
        u = Unit(dfs(board.grid, i))
        generate_liberties(u)
        if board.grid[i] == 1:
            u.colour_is_black = True
            black_units.add(u)
        else:
            u.colour_is_black = False
            white_units.add(u)
    return black_units, white_units