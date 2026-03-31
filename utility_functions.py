import constants as C

board_size = C.board_size

def is_valid_notation(notation : str, board_size = board_size) -> bool:
    if len(notation) != board_size * board_size:
        return False
    return set(notation).issubset(C.valid_notation_chars)

def adjacent(source : int) -> list[int]:
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

