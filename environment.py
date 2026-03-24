from constants import komi, board_size, valid_notation_chars

def is_valid_notation(notation : str, board_size=board_size) -> bool:
    if len(notation) != board_size * board_size:
        return False
    return set(notation).issubset(valid_notation_chars)

class Board:
    def __init__(self, notation = None):
        self.grid = [0 for _ in range(board_size * board_size)]
        self.notation = '_' * board_size * board_size if not notation else notation
        if notation and is_valid_notation(notation):
            mp = {'_' : 0, 'b' : 1, 'w' : 2}
            for i in range(board_size * board_size):
                self.grid[i] = mp[notation[i]]
    
    def copy(self):
        return Board(self.notation[:])

class Position:
    def __init__(self, notation = None, parent = None):
        self.board = Board(notation)
        self.score = -komi
        self.black_to_play = True
        self.eval = 0
        self.parent = parent
        self.children = []