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

def count_liberties(board : BitBoard, start : int, stone : int) -> int:
    # DFS over a group of same-colour stones, counting unique empty adjacent squares.
    # Returns early with a sentinel of 2 once more than 1 liberty is found, to support
    # early-exit callers that only care whether count == 1.
    lib_visited = [False] * (board_size * board_size)
    stone_visited = [False] * (board_size * board_size)
    stack = [start]
    stone_visited[start] = True
    n = 0
    while stack:
        curr = stack.pop()
        for a in adjacent(curr):
            val = board.get(a)
            if not val and not lib_visited[a]:
                lib_visited[a] = True
                n += 1
                if n > 1:
                    return n   # caller can early-exit on > 1
            elif val == stone and not stone_visited[a]:
                stone_visited[a] = True
                stack.append(a)
    return n


def is_capture(position : Position, move : int) -> bool:
    # After placing and captures, does any adjacent opponent group have 0 liberties?
    copied_board = position.bitboard.copy()
    copied_position = Position(copied_board, position.black_to_play, position.parent, move=None)
    stone = 2 if copied_position.black_to_play else 1
    opp_stone = 3 - stone
    copied_position.bitboard.set(move, copied_position.black_to_play)
    perform_captures(copied_position.bitboard, copied_position.black_to_play)
    checked = set()
    for a in adjacent(move):
        if copied_position.bitboard.get(a) == opp_stone and a not in checked:
            n = count_liberties(copied_position.bitboard, a, opp_stone)
            if n == 0:
                return True
            grp_visited = [False] * (board_size * board_size)
            stack = [a]
            grp_visited[a] = True
            while stack:
                curr = stack.pop()
                checked.add(curr)
                for adj in adjacent(curr):
                    if not grp_visited[adj] and copied_position.bitboard.get(adj) == opp_stone:
                        grp_visited[adj] = True
                        stack.append(adj)
    return False


def is_atari_on_opponent(position : Position, move : int) -> bool:
    # After placing and captures, does any adjacent opponent group have exactly 1 liberty?
    copied_board = position.bitboard.copy()
    copied_position = Position(copied_board, position.black_to_play, position.parent, move=None)
    stone = 2 if copied_position.black_to_play else 1
    opp_stone = 3 - stone
    copied_position.bitboard.set(move, copied_position.black_to_play)
    perform_captures(copied_position.bitboard, copied_position.black_to_play)
    checked = set()
    for a in adjacent(move):
        if copied_position.bitboard.get(a) == opp_stone and a not in checked:
            n = count_liberties(copied_position.bitboard, a, opp_stone)
            if n == 1:
                return True
            grp_visited = [False] * (board_size * board_size)
            stack = [a]
            grp_visited[a] = True
            while stack:
                curr = stack.pop()
                checked.add(curr)
                for adj in adjacent(curr):
                    if not grp_visited[adj] and copied_position.bitboard.get(adj) == opp_stone:
                        grp_visited[adj] = True
                        stack.append(adj)
    return False


def saves_from_atari(position : Position, move : int) -> bool:
    # Before placing: is any adjacent friendly group in atari, with move as its only liberty?
    # move is still empty on the board — counted naturally as a liberty during DFS.
    copied_board = position.bitboard.copy()
    copied_position = Position(copied_board, position.black_to_play, position.parent, move=None)
    stone = 2 if copied_position.black_to_play else 1
    checked = set()
    for a in adjacent(move):
        if copied_position.bitboard.get(a) == stone and a not in checked:
            n = count_liberties(copied_position.bitboard, a, stone)
            if n == 1:
                return True
            grp_visited = [False] * (board_size * board_size)
            stack = [a]
            grp_visited[a] = True
            while stack:
                curr = stack.pop()
                checked.add(curr)
                for adj in adjacent(curr):
                    if not grp_visited[adj] and copied_position.bitboard.get(adj) == stone:
                        grp_visited[adj] = True
                        stack.append(adj)
    return False


def is_cut(position : Position, move : int) -> bool:
    # Is move adjacent to 2+ distinct opponent groups?
    copied_board = position.bitboard.copy()
    copied_position = Position(copied_board, position.black_to_play, position.parent, move=None)
    stone = 2 if copied_position.black_to_play else 1
    opp_stone = 3 - stone
    opp_groups = 0
    checked = set()
    for a in adjacent(move):
        if copied_position.bitboard.get(a) == opp_stone and a not in checked:
            opp_groups += 1
            if opp_groups >= 2:
                return True
            grp_visited = [False] * (board_size * board_size)
            stack = [a]
            grp_visited[a] = True
            while stack:
                curr = stack.pop()
                checked.add(curr)
                for adj in adjacent(curr):
                    if not grp_visited[adj] and copied_position.bitboard.get(adj) == opp_stone:
                        grp_visited[adj] = True
                        stack.append(adj)
    return False


def is_connection(position : Position, move : int) -> bool:
    # Is move adjacent to 2+ distinct friendly groups?
    copied_board = position.bitboard.copy()
    copied_position = Position(copied_board, position.black_to_play, position.parent, move=None)
    stone = 2 if copied_position.black_to_play else 1
    friendly_groups = 0
    checked = set()
    for a in adjacent(move):
        if copied_position.bitboard.get(a) == stone and a not in checked:
            friendly_groups += 1
            if friendly_groups >= 2:
                return True
            grp_visited = [False] * (board_size * board_size)
            stack = [a]
            grp_visited[a] = True
            while stack:
                curr = stack.pop()
                checked.add(curr)
                for adj in adjacent(curr):
                    if not grp_visited[adj] and copied_position.bitboard.get(adj) == stone:
                        grp_visited[adj] = True
                        stack.append(adj)
    return False


def increases_liberties(position : Position, move : int) -> bool:
    # Net liberty gain for friendly groups after placing at move.
    # Before: union of liberties of all distinct friendly groups adjacent to move (excluding move itself).
    # After: liberties of the merged group once stone is placed at move.
    copied_board = position.bitboard.copy()
    copied_position = Position(copied_board, position.black_to_play, position.parent, move=None)
    stone = 2 if copied_position.black_to_play else 1
    board = copied_position.bitboard

    checked_before = set()
    libs_before = set()
    for a in adjacent(move):
        if board.get(a) == stone and a not in checked_before:
            lib_visited = [False] * (board_size * board_size)
            stone_visited = [False] * (board_size * board_size)
            stack = [a]
            stone_visited[a] = True
            while stack:
                curr = stack.pop()
                checked_before.add(curr)
                for adj in adjacent(curr):
                    val = board.get(adj)
                    if not val and not lib_visited[adj]:
                        lib_visited[adj] = True
                        libs_before.add(adj)
                    elif val == stone and not stone_visited[adj]:
                        stone_visited[adj] = True
                        stack.append(adj)
    libs_before.discard(move)  # move itself was empty before but will be filled

    board.set(move, stone == 2)  # place stone
    libs_after = set()
    lib_visited = [False] * (board_size * board_size)
    stone_visited = [False] * (board_size * board_size)
    stack = [move]
    stone_visited[move] = True
    while stack:
        curr = stack.pop()
        for adj in adjacent(curr):
            val = board.get(adj)
            if not val and not lib_visited[adj]:
                lib_visited[adj] = True
                libs_after.add(adj)
            elif val == stone and not stone_visited[adj]:
                stone_visited[adj] = True
                stack.append(adj)

    return len(libs_after) > len(libs_before)


def is_not_self_atari(position : Position, move : int) -> bool:
    # After placing and captures, does the resulting group have more than 1 liberty?
    copied_board = position.bitboard.copy()
    copied_position = Position(copied_board, position.black_to_play, position.parent, move=None)
    stone = 2 if copied_position.black_to_play else 1
    copied_position.bitboard.set(move, copied_position.black_to_play)
    perform_captures(copied_position.bitboard, copied_position.black_to_play)
    n = count_liberties(copied_position.bitboard, move, stone)
    return n > 1


def give_attributes(position : Position, move : np.uint16) -> np.uint16:
    move_idx = int(move) & 0x1FF  # bits 0-8: the square index
    result = np.uint16(move_idx)

    if is_capture(position, move_idx):
        result |= np.uint16(1 << 15)
    if is_atari_on_opponent(position, move_idx):
        result |= np.uint16(1 << 14)
    if saves_from_atari(position, move_idx):
        result |= np.uint16(1 << 13)
    if is_cut(position, move_idx):
        result |= np.uint16(1 << 12)
    if is_connection(position, move_idx):
        result |= np.uint16(1 << 11)
    if increases_liberties(position, move_idx):
        result |= np.uint16(1 << 10)
    if is_not_self_atari(position, move_idx):
        result |= np.uint16(1 << 9)

    return result


def assign_priority(position : Position, moves : list[np.uint16]) -> list[np.uint16]:
    for i in range(len(moves)):
        moves[i] = give_attributes(position, moves[i])
    return np.sort(np.array(moves, dtype=np.uint16))[::-1].tolist()

def move_gen(position : Position):
    moves = pseudo_legal(position.bitboard)
    moves = remove_suicides(position.bitboard, moves, position.black_to_play)
    moves = moves if not position.parent else remove_ko(position.parent.bitboard, position, moves)
    moves = assign_priority(position, moves)
    return moves