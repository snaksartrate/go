import constants as C
import utility_functions as uf

board_size = C.board_size

class Unit:
    def __init__(self, unit : set[int], liberties : set[int], colour_is_black : bool):
        self.points = unit
        self.liberties = liberties if liberties is not None else set()
        self.colour_is_black = colour_is_black

    @property
    def liberty_count(self):
        return len(self.liberties)

class Board:
    def __init__(self, notation : str):
        self.grid = [0 for _ in range(board_size * board_size)]
        if notation and uf.is_valid_notation(notation):
            for i in range(board_size * board_size):
                self.grid[i] = C.mp[notation[i]]

    @property
    def notation(self) -> str:
        s = ''
        for num in self.grid:
            s += C.val[num + 1] # -1 corresponds to white on the grid, 0 to empty square, and 1 to black
        return s

    def copy(self): # -> Board:
        notation = self.get_notation()
        return Board(notation)

    def generate_liberties(unit : Unit, grid : list):
        for cell in unit.unit:
            for adj in uf.adjacent(cell):
                if not grid[adj]:
                    unit.liberties.add(adj)
        unit.liberty_count = len(unit.liberties)

    def get_units(self) -> tuple[set[Unit], set[Unit]]:
        black_units = set()
        white_units = set()
        for i in range(board_size * board_size):
            if not self.grid[i] or any(i in unit.unit for unit in black_units) or any(i in unit.unit for unit in white_units):
                continue
            u = Unit(uf.dfs(self.grid, i))
            self.generate_liberties(u)
            if self.grid[i] == 1:
                u.colour_is_black = True
                black_units.add(u)
            else:
                u.colour_is_black = False
                white_units.add(u)
        return black_units, white_units

class Move:
    def __init__(self, move : int, capture : bool):
        self.move = move
        self.capture = capture

class Position:
    def __init__(self, notation : str, player : bool, score : float, parent: "Position" | None = None, children: list["Move"] | None = None):
        self.board = Board(notation)
        self.black_to_play = player
        self.eval = score
        self.parent = parent
        self.children = children if children is not None else [] # hopefully sorted

    @property
    def notation(self) -> str:
        return self.board.notation
    
    def get_liberties(self): # perform len(positoin.get_liberties()[0]) for number of black liberties (i dont know what the usage would be) and len(positoin.get_liberties()[1]) for white liberties
        black_units, white_units = self.board.get_units()
        black_liberties = set()
        white_liberties = set()
        for point in (unit.liberties for unit in black_units):
            black_liberties.add(point)
        for point in (unit.liberties for unit in white_units):
            white_liberties.add(point)
        return black_liberties, white_liberties
    
