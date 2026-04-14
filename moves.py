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
                move |= 0x8000 # 0b1000_0000_0000_0000 -> 0, 0, 0, and 0 * (1 + 2 + 4) + 1 * 8 = 8 # in hexadecimal
                return False
    return True

def remove_suicides(board : BitBoard, moves : list[np.uint16], black : bool) -> list[np.uint16]:
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
        if not visited[i] and board.get(i) == opp_stone:
            stack = [i]
            visited[i] = True
            n = 0 # number of liberties
            while stack:
                curr = stack.pop()
                for a in adjacent(curr):
                    val = board.get(a)
                    if not val and not visited[a]:
                        n += 1
                        visited[a] = True
                    elif val == opp_stone:
                        stack.append(a)
                        visited[a] = True
            if not n:
                stack = [i]
                board.empty(i)
                while stack:
                    curr = stack.pop()
                    for a in adjacent(curr):
                        val = board.get(a)
                        if val == opp_stone:
                            stack.append(a)
                            board.empty(a)
    return

def make_a_move(position : Position, move : np.uint16) -> Position:
    black_to_play = not position.black_to_play
    new_position = Position(position.bitboard, black_to_play, position, move)
    new_position.bitboard.set(move, black_to_play)
    perform_captures(new_position.bitboard, black_to_play)
    return position

def remove_ko(parent_board : BitBoard, current : Position, moves : list[np.uint16]) -> list[np.uint16]:
    is_ko = [False] * (len(moves))
    for i in range(len(moves)):
        if parent_board == make_a_move(current, moves[i]).bitboard:
            is_ko[i] = True
    return [moves[i] for i in range(len(moves)) if not is_ko[i]]

def check_capture(board : BitBoard, move : np.uint16) -> np.uint16:
    if move & 0x8000:
        return move
    stone = board.get(move)
    opp_stone = 3 - stone
    visited = [False] * (board_size * board_size)
    is_a_capture = True
    for a in adjacent(move):
        if board.get(a) == opp_stone:
            stack = [a]
            visited[a] = True
            while not is_a_capture and stack:
                curr = stack.pop()
                for adj in adjacent(curr):
                    if not board.get(adj):
                        is_a_capture = False
                        break
                    if not visited[adj] and board.get(adj) == opp_stone:
                        visited[adj] = True
                        stack.append(adj)
    return move | ((1 & is_a_capture) << 15)

def assign_priority(position : Position, moves : list[np.uint16]) -> list[np.uint16]:
    for i in range(len(moves)):
        # perform checks
        pass
    return np.sort(np.array(moves))[::-1].tolist()

def move_gen(position : Position):
    moves = pseudo_legal(position.bitboard)
    moves = remove_suicides(position.bitboard, moves, position.black_to_play)
    moves = remove_ko(position.parent.bitboard, position, moves)
    moves = assign_priority(position, moves)
    return moves
