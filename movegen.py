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

def make_a_move(board : Board, move : int, black_to_play : bool) -> Position: # remove this function later. it is so fucking redundant.
    board.grid[move] = 1 if black_to_play else -1

def validate(position : Position, pseudo_legal : list, black_to_play : bool) -> list:
    # check for pseudo_legal[0] -> the "pass" move, after the for loop
    illegal_moves = set()
    for i in range(1, len(pseudo_legal)):
        # perform validity checks, remove invalid moves
        new_position = deepcopy(position)
        make_a_move(new_position.board, pseudo_legal[i], black_to_play)
        new_position.black_units, new_position.white_units = get_units(new_position.board)
        if black_to_play:
            for unit in new_position.black_units:
                if not unit.liberty_count:
                    illegal_moves.add(i)
        else:
            for unit in new_position.white_units:
                if not unit.liberty_count:
                    illegal_moves.add(i)
        pass # are more checks still left?
    return [move for move in pseudo_legal if move not in illegal_moves]

def move_gen(position : Position):
    pseudo_legal = get_pseudo_legal(position.board)
    moves = validate(position, pseudo_legal, position.black_to_play)
