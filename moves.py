from copy import deepcopy
import numpy as np

from environment import Position, BitBoard, Move
from eval import adjacent, get_units

def get_pseudo_legal(board : BitBoard) -> list[Move]: # 9 LSB show the square where we place a stone; range goes from 0-360, both included; MSB for whether a capture or not
    pseudo_legal = [None] # if the player decides to pass
    board_size = len(board.grid)
    for i in range(board_size * board_size):
        if not board.grid[i]:
            pseudo_legal.append(Move(i))
    return pseudo_legal

def perform_captures(board : Board, black_to_play : bool): # deletes the stone which can be captured
    black_units, white_units = board.get_units()
    remove_captured_ones_from = white_units if black_to_play else black_units
    for unit in remove_captured_ones_from:
        if not unit.liberty_count:
            for point in unit.points:
                board.grid[point] = 0

def make_a_move(board : Board, black_to_play : bool, move : Move) -> Board:
    board.grid[move.move] = 0 if move == None else (1 if black_to_play else -1)
    perform_captures(board, black_to_play)
    return board

def remove_suicides(board : Board, pseudo_legal : list[Move], black_to_play : bool) -> list[int]:
    # if i pass, i wont be able to suicide, simple. so just skip pseudo_legal[0]
    illegal_moves = set()
    for i in range(1, len(pseudo_legal)):
        new_board = board.copy()
        new_board = make_a_move(new_board, pseudo_legal[i], black_to_play)
        black_units, white_units = new_board.get_units()
        is_suicide = False
        if black_to_play:
            for unit in black_units:
                if not unit.liberty_count:
                    is_suicide = True
        else:
            for unit in white_units:
                if not unit.liberty_count:
                    is_suicide = True
        if is_suicide:
            if black_to_play:
                for unit in white_units:
                    if any(cell in unit for cell in adjacent(pseudo_legal[i].move)) and not unit.liberty_count:
                        is_suicide = False
                        break
            else:
                for unit in black_units:
                    if any(cell in unit for cell in adjacent(pseudo_legal[i].move)):
                        if unit.liberty_count == 0:
                            is_suicide = False
                            break
        if is_suicide:
            illegal_moves.add(pseudo_legal[i])
    return [move for move in pseudo_legal if move not in illegal_moves]

def remove_ko(position : Position, pseudo_legal : list[Move]) -> list[int]:
    black_to_play = position.black_to_play
    illegal_moves = set()
    for move in pseudo_legal:
        new_position = Position(position.board.copy())
        if position.parent == make_a_move(new_position, move):
            illegal_moves.add(move)
    new_position = make_a_move(position)
    return [move for move in pseudo_legal if move not in illegal_moves]

def give_attributes_to(moves : list[Move], position : Position) -> list[Move]:
    return moves

def sort_moves(moves : list[Move]) -> None:
    pass

def move_gen(position : Position):
    moves = get_pseudo_legal(position.bitboard)
    moves = remove_suicides(position.bitboard, moves, position.black_to_play)
    moves = remove_ko(position, moves)
    moves = give_attributes_to(moves, position)
    sort_moves(moves)
    return moves
