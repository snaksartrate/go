from copy import deepcopy

from environment import Position, Board, Unit
from eval import get_units

def get_pseudo_legal(board : Board) -> list:
    pseudo_legal = [None] # if the player decides to pass
    board_size = len(board.grid)
    for i in range(board_size * board_size):
        if not board.grid[i]:
            pseudo_legal.append(i)
    return pseudo_legal

def make_a_move(position : Position, move : int, black_to_play : bool) -> Position: # remove this function later. it is so fucking redundant.
    position[move] = 1 if black_to_play else -1                                     # wait, what the fuck did i write?

def validate(position : Position, pseudo_legal : list, black_to_play : bool) -> list:
    # check for pseudo_legal[0] -> the "pass" move
    for i in range(1, len(pseudo_legal)):
        # perform validity checks, remove invalid moves
        new_position = deepcopy(position)
        new_position = make_a_move(new_position, pseudo_legal[i], black_to_play)
        black_units, white_units = get_units(new_position.board)
        if black_to_play:
            for unit in black_units:
                if unit.l
        pass
    return pseudo_legal

def move_gen(position : Position):
    pseudo_legal = get_pseudo_legal(position.board)
    moves = validate(position, pseudo_legal, position.black_to_play)
