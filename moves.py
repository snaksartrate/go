from copy import deepcopy
import numpy as np

import constants as C
from environment import Position, BitBoard, Move
from eval import adjacent, get_units

board_size = C.board_size
visited = [False] * (board_size * board_size)
liberties = [0] * (board_size * board_size)
NULL_MOVE = np.uint16(0x1FF)

if True:
    def check_captures_opponent(position : Position, moves : list[np.uint16]):
        pass

    def check_puts_opponent_in_atari(position : Position, moves : list[np.uint16]):
        pass

    def check_saves_me_from_atari(position : Position, moves : list[np.uint16]):
        pass

    def check_cuts_opponents_groups(position : Position, moves : list[np.uint16]):
        pass

    def check_connects_my_groups(position : Position, moves : list[np.uint16]):
        pass

    def check_increases_my_liberties(position : Position, moves : list[np.uint16]):
        pass

    def check_is_not_self_atari(position : Position, moves : list[np.uint16]):
        pass

def get_pseudo_legal(board : BitBoard) -> list[Move]: # 9 LSB show the square where we place a stone; range goes from 0-360, both included; MSB for whether a capture or not
    pseudo_legal = []
    for i in range(board_size * board_size):
        if not board.get(i):
            pseudo_legal.append(Move(i))
    return pseudo_legal

def perform_captures(board : BitBoard, black_to_play : bool): # deletes the stone which can be captured
    capturable_stone = 1 if black_to_play else 2
    for i in range(board_size * board_size):
        if board.get(i) == capturable_stone:
            colour = board.get(i)
            no_of_liberties = 0
            stack = [i]
            while stack:
                curr = stack.pop()
                visited[curr] = True
                for adj in adjacent(curr):
                    if not board.get(adj):
                        no_of_liberties += 1
                    elif board.get(adj) == colour and not visited[adj]:
                        stack.append(adj)
                        visited[adj] = True
            if not no_of_liberties:
                stack = [i]
                while stack:
                    curr = stack.pop()
                    for adj in adjacent(curr):
                        if board.get(adj) == colour:
                            stack.append(adj)
                            board.empty(adj)
    for i in range(board_size * board_size):
        visited[i] = False

def make_a_move(board : BitBoard, move : np.uint16, black_to_play : bool) -> BitBoard:
    board.set(int(move & 0x1FF), black_to_play)
    perform_captures(board, black_to_play)
    return board

def remove_suicides(board : BitBoard, pseudo_legal : list[np.uint16], black_to_play : bool) -> list[np.uint16]:
    # no need to check the pass move
    # if i pass, i wont be able to suicide
    # just skip pseudo_legal[0]
    is_suicide = [False] * len(pseudo_legal)
    for i in range(1, len(pseudo_legal)):
        move = pseudo_legal[i]
        new_board = make_a_move(board.copy(), move, black_to_play)
        opp_colour = 1 if black_to_play else 2
        # consider the move to be suicide
        suicide = True
        for adj in adjacent(move):
            if new_board.get(adj) != opp_colour:
                suicide = False # so if any liberty is found, it is not a suicide
                break # therefore, early exit
        if not suicide:
            continue # early exit
        if suicide: # check if it kills others
            for i in range(board_size * board_size):
                visited[i] = False
                liberties[i] = 0
            for adj in adjacent(move): # to check for dying opponent's units, we will look for the units whose liberty just got to 0, i.e. whose liberty just changed, and the only possible units could be the one who had a liberty as the move that was played, and therfore look for immediately adjacent units only
                no_of_liberties = 0 # check if a unit is dying # i dont need to check what is in place of that adjacent intersection. it is an opposite stone. if it were anything else, i would have already exited
                stack = [adj] # begin dfs
                visited[adj] = True
                while stack:
                    curr = stack.pop()
                    for a in adjacent(curr):
                        if not new_board.get(a):
                            no_of_liberties += 1
                        if new_board.get(a) == opp_colour:
                            stack.append(a)
                            visited[a] = True
            if not no_of_liberties:
                suicide = False
            if suicide:
                is_suicide[move] = True
    for s in is_suicide:
        s = False
    return [move for move in pseudo_legal if not is_suicide[move]]

def remove_ko(position : Position, pseudo_legal : list[np.uint16]) -> list[np.uint16]:
    black_to_play = position.black_to_play
    illegal_moves = set()
    for move in pseudo_legal:
        new_position = Position(position.board.copy())
        if position.parent == make_a_move(new_position, move):
            illegal_moves.add(move)
    new_position = make_a_move(position)
    return [move for move in pseudo_legal if move not in illegal_moves]

def give_attributes_to(moves : list[np.uint16], position : Position) -> list[np.uint16]:
    check_captures_opponent(position, moves)
    check_connects_my_groups(position, moves)
    check_cuts_opponents_groups(position, moves)
    check_increases_my_liberties(position, moves)
    check_is_not_self_atari(position, moves)
    check_puts_opponent_in_atari(position, moves)
    check_saves_me_from_atari(position, moves)
    return moves

def sort_moves(moves : list[np.uint16]):
    pass

def move_gen(position : Position) -> list[np.uint16]:
    moves = get_pseudo_legal(position.bitboard)
    moves = remove_suicides(position.bitboard, moves, position.black_to_play)
    moves = remove_ko(position, moves)
    moves = give_attributes_to(moves, position)
    sort_moves(moves)
    moves.append(NULL_MOVE)
    return moves
