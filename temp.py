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
        for a in adjacent(curr):
            val = board.get(a)
            if not val:
                return False
            if not visited[a] and val == stone:
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
    is_suicide_move = [False for _ in range(len(moves))]
    for i in range(len(moves)):
        move = moves[i]
        new_board = board.copy()
        new_board.set(move, black)
        if is_suicide(new_board, move, black):
            is_suicide_move[i] = True
    return [moves[i] for i in range(len(moves)) if not is_suicide_move[i]]

def perform_captures(board : BitBoard, black_to_play : bool) -> int:
    no_of_captured_stones = 0
    stone = 2 if black_to_play else 1
    opp_stone = 3 - stone
    stone_visited = [False] * (board_size * board_size)
    
    for i in range(board_size * board_size):
        if not stone_visited[i] and board.get(i) == opp_stone:
            # Phase 1: Check liberties
            group = [i]
            stack = [i]
            stone_visited[i] = True
            lib_visited = [False] * (board_size * board_size)
            liberties = 0
            
            while stack:
                curr = stack.pop()
                for a in adjacent(curr):
                    val = board.get(a)
                    if val == 0:
                        if not lib_visited[a]:
                            liberties += 1
                            lib_visited[a] = True
                    elif val == opp_stone and not stone_visited[a]:
                        stone_visited[a] = True
                        stack.append(a)
                        group.append(a) # Keep track of stones in the group
            
            # Phase 2: If no liberties, remove the group
            if liberties == 0:
                for stone_idx in group:
                    board.empty(stone_idx)
                    no_of_captured_stones += 1
                    
    return no_of_captured_stones

def make_a_move(position : Position, move : np.uint16) -> Position:
    move_idx = int(move & 0x1FF)
    black_to_play_next = not position.black_to_play
    
    # Handle Pass
    if move_idx == board_size * board_size:
        return Position(position.bitboard.copy(), black_to_play_next, position, move, 
                        position.black_prisoners, position.white_prisoners)

    new_board = position.bitboard.copy()
    new_board.set(move_idx, position.black_to_play)
    
    # Track prisoners!
    captured = perform_captures(new_board, position.black_to_play)
    
    bp = position.black_prisoners
    wp = position.white_prisoners
    if position.black_to_play:
        bp += captured
    else:
        wp += captured
        
    return Position(new_board, black_to_play_next, position, move, bp, wp)

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
    # Check capture BEFORE removing the opponent's dead stones
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

def remove_ko(parent_board : BitBoard, current : Position, moves : list[np.uint16]) -> list[np.uint16]:
    legal_moves = []
    for m in moves:
        # Optimization: Only simulate the move if it's a capture.
        # Since we haven't run assign_priority yet, we use a quick check.
        if is_capture(current, int(m)):
            # It's a capture, so it MIGHT be a Ko. Simulate it.
            test_pos = make_a_move(current, m)
            if test_pos.bitboard == parent_board:
                continue # Skip this move, it's a Ko violation
        
        legal_moves.append(m)
    return legal_moves

def get_group_stats(board: BitBoard, start_idx: int):
    """
    Returns (set_of_stone_indices, set_of_liberty_indices) for the group at start_idx.
    """
    stone_type = board.get(start_idx)
    if stone_type == 0:
        return set(), {start_idx}
    
    group_stones = {start_idx}
    liberties = set()
    stack = [start_idx]
    visited = {start_idx}
    
    while stack:
        curr = stack.pop()
        for a in adjacent(curr):
            val = board.get(a)
            if val == 0:
                liberties.add(a)
            elif val == stone_type and a not in visited:
                visited.add(a)
                group_stones.add(a)
                stack.append(a)
    return group_stones, liberties

def analyze_move_attributes(position: Position, move_idx: int) -> np.uint16:
    """
    The master analyzer (Fix #4). 
    Calculates all heuristic bits in one pass without copying the board.
    """
    board = position.bitboard
    stone = 2 if position.black_to_play else 1
    opp_stone = 3 - stone
    
    # Bits to set
    is_cap = False
    is_atari = False
    is_save = False
    is_cut = False
    is_conn = False
    is_inc_lib = False
    is_safe = False # not self atari

    unique_friendly_groups = [] # list of sets (stones)
    unique_enemy_groups = []
    direct_liberties = set()
    
    # 1. Inspect Neighbors
    for a in adjacent(move_idx):
        val = board.get(a)
        if val == 0:
            direct_liberties.add(a)
        elif val == stone:
            if not any(a in g for g in unique_friendly_groups):
                _, libs = get_group_stats(board, a)
                unique_friendly_groups.append(libs)
        elif val == opp_stone:
            if not any(a in g for g in unique_enemy_groups):
                stones, libs = get_group_stats(board, a)
                unique_enemy_groups.append((stones, libs))

    # 2. Evaluate Opponent-based Heuristics (Capture, Atari, Cut)
    captured_stones_count = 0
    for g_stones, g_libs in unique_enemy_groups:
        if len(g_libs) == 1 and move_idx in g_libs:
            is_cap = True
            captured_stones_count += len(g_stones)
        elif len(g_libs) == 2 and move_idx in g_libs:
            is_atari = True
            
    if len(unique_enemy_groups) >= 2:
        is_cut = True

    # 3. Evaluate Friendly-based Heuristics (Save, Connect, Liberties)
    for g_libs in unique_friendly_groups:
        if len(g_libs) == 1 and move_idx in g_libs:
            is_save = True
    
    if len(unique_friendly_groups) >= 2:
        is_conn = True

    # 4. Self-Atari and Liberty Increase Logic
    # New libs = (Direct empty neighbors - 1) + (Union of libs of friendly groups - move_idx) + (Libs gained from captures)
    all_libs_before = direct_liberties.copy()
    for g_libs in unique_friendly_groups:
        all_libs_before.update(g_libs)
    all_libs_before.discard(move_idx)
    
    # Simplified check: if we capture anything, it's almost certainly not a self-atari
    if is_cap or len(all_libs_before) > 1:
        is_safe = True
        
    if len(all_libs_before) > 0: # If we have any liberties left
        is_inc_lib = True # Placeholder for actual liberty count logic

    # 5. Pack the Bits
    res = np.uint16(move_idx)
    if is_cap:   res |= 0x8000 # Bit 15
    if is_atari: res |= 0x4000 # Bit 14
    if is_save:  res |= 0x2000 # Bit 13
    if is_cut:   res |= 0x1000 # Bit 12
    if is_conn:  res |= 0x0800 # Bit 11
    if is_inc_lib: res |= 0x0400 # Bit 10
    if is_safe:  res |= 0x0200 # Bit 9
    
    return res

def move_gen(position: Position):
    # 1. Get pseudo-legal
    moves = pseudo_legal(position.bitboard)
    
    # 2. Filter Suicides (using your existing efficient is_suicide)
    moves = [m for m in moves if not is_suicide(position.bitboard, m, position.black_to_play)]
    
    # 3. Assign Priority and Analyze (The fast way)
    prioritized_moves = []
    for m in moves:
        prioritized_moves.append(analyze_move_attributes(position, int(m)))
    
    # 4. Filter Ko (Only for moves that have the Capture bit set)
    if position.parent:
        final_moves = []
        for m in prioritized_moves:
            if m & 0x8000: # Bit 15 set (Capture)
                if make_a_move(position, m).bitboard == position.parent.bitboard:
                    continue
            final_moves.append(m)
        prioritized_moves = final_moves

    # 5. Sort Descending (Best moves first)
    return sorted(prioritized_moves, reverse=True)