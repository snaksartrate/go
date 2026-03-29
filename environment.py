import constants as C

def is_valid_notation(notation : str, board_size = C.board_size) -> bool:
    if len(notation) != C.board_size * C.board_size:
        return False
    return set(notation).issubset(C.valid_notation_chars)

class Board:
    def __init__(self, notation = None):
        self.grid = [0 for _ in range(C.board_size * C.board_size)]
        if notation and is_valid_notation(notation):
            for i in range(C.board_size * C.board_size):
                self.grid[i] = C.mp[notation[i]]
    
    def copy(self):
        pass

    def get_notation(self) -> str:
        s = ''
        for num in self.grid:
            s += C.val[num + 1] # -1 corresponds to white on the grid, 0 to empty square, and 1 to black
        return s

class Unit:
    def __init__(self, unit : set):
        self.unit = unit
        self.liberties = set()
        self.liberty_count = 0
        self.colour_is_black = None

class Position:
    def __init__(self, notation = None, parent = None):
        self.board = Board(notation)
        self.score = -C.komi
        self.black_to_play = True
        self.eval = 0
        self.parent = parent
        self.children = set()
        self.liberties = set()
        self.liberty_count = 0
        self.ko = None
        self.black_units = set()
        self.white_units = set()

    def get_notation(self) -> str:
        return self.board.get_notation()
    