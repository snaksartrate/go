import numpy as np

import constants as C
from utility_functions import adjacent
from environment import Position, BitBoard

board_size = C.board_size

def pseudo_legal(board : BitBoard) -> list[np.uint16]:
    pseudo_legal = []
    for i in range(board_size * board_size):
        if not board.get(i):
            pseudo_legal.append(np.uint16(i))
    return pseudo_legal

visited = [False] * (board_size * board_size)

def is_suicide(board : BitBoard, input_move : np.uint16, black_to_play : bool) -> bool:
    move = input_move & 0x1FF
    for a in adjacent(move):
        if not board.get(a):
            return False
    stone = 2 if black_to_play else 1
    opp_stone = 3 - stone
    # now im gonna do a dfs to check if my recently placed stone has any liberties
    # so im also gonna look for its neighbours and so on and if i get a liberty, return false
    stack = [move]
    visited = [False] * (board_size * board_size)
    visited[move] = True
    while stack:
        curr = stack.pop()
        if not board.get(curr):
            return False
        for a in adjacent(curr):
            if not visited[a] and board.get(a) == stone:
                stack.append(a)
                visited[a] = True
    # now i know that my stone / unit is surrounded
    # time to check if it is killing my opp
    # begin dfs from adjacent if it is of opp colour
    for a in adjacent(move):
        if board.get(a) == opp_stone:
            this_unit_isnt_dying = False
            # begin dfs
            # if there exists any stone / unit that is dying, return false
            # if there exists any stone / unit with a liberty, it aint dying. just look for the next stone. if any one doesnt have a liberty, it aint a suicide. return false
            # if all of them dont die? what to do? think about this # i think this is like
            '''
            . . W B B W . . .
            . . . W B W . . .
            . . . W B W . . .
            . . . W . W . . .
            . . . . W . . . .
            . . . . . . . . .
            '''
            # so yeah, hypothetical position and overthinking. this code is correct.
            stack = [a]
            visited[a] = True # we can use the same visited array because we are looking for stones of opposite colour and a valid position is guaranteed
            while stack:
                curr = stack.pop()
                for adj in adjacent(curr):
                    val = board.get(adj)
                    if not val:
                        this_unit_isnt_dying = True
                        break
                    if not visited[adj] and val == opp_stone:
                        stack.append(adj)
                        visited[adj] = True
                if this_unit_isnt_dying:
                    break
            if not this_unit_isnt_dying:
                return False
    return True

def remove_suicides(board : BitBoard, moves : list[np.uint16], black : bool) -> list[np.uint16]:
    stone = 2 if black else 1
    opp_stone = 1 if black else 2
    is_suicide_move = [False for _ in range(len(moves))]
    for i in range(len(moves)):
        move = moves[i]
        new_board = board.copy()
        new_board.set(move, black)
        if is_suicide(new_board, move[i], black):
            is_suicide_move[i] = True
    return [moves[i] for i in range(len(moves)) if not is_suicide_move[i]]

def perform_captures(board : BitBoard, black_to_play : bool) -> None:
    stone = 2 if black_to_play else 1
    opp_stone = 3 - stone
    visited = [False] * (board_size * board_size)
    for i in range(board_size * board_size):
        if not visited[i]:
            stack = [i]
            visited[i] = True
            n = 0 # number of liberties
            while stack:
                curr = stack.pop()
                for a in adjacent(stack):
                    val = board.get(a)
                    if not val:
                        n += 1
                    elif val == opp_stone:
                        p

def make_a_move(position : Position, move : np.uint16) -> Position:
    black_to_play = not position.black_to_play
    new_position = Position(position.bitboard, black_to_play, position, move)
    new_position.bitboard.set(move, black_to_play)
    perform_captures()
    return position

def remove_ko(parent : Position, current : Position, moves : list[np.uint16]) -> list[np.uint16]:
    pass

def assign_priority(moves : list[np.uint16]) -> list[np.uint16]:
    return np.sort(np.array(moves))[::-1].tolist()

def move_gen(position : Position):
    moves = pseudo_legal(position.bitboard)
    moves = remove_suicides(position.bitboard, moves, position.black_to_play)
    moves = remove_ko()
    moves = assign_priority(moves)
    return moves
