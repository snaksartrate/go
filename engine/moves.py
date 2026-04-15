import numpy as np

import constants as C
from utility_functions import adjacent
from environment import Position, BitBoard

board_size = C.board_size
total_squares = board_size * board_size

def pseudo_legal(board : BitBoard) -> list[np.uint16]:
    pseudo_legal = []
    for i in range(board_size * board_size):
        if not board.get(i):
            pseudo_legal.append(np.uint16(i))
    return pseudo_legal

visited = [False] * (board_size * board_size)

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

def is_suicide(board: BitBoard, input_move: np.uint16, black_to_play: bool) -> bool:
    move = int(input_move & 0x1FF)
    stone = 2 if black_to_play else 1
    opp_stone = 3 - stone

    # 1. Safe if it has at least one empty adjacent square
    for a in adjacent(move):
        if board.get(a) == 0:
            return False

    # 2. Safe if it captures an opponent group (Opponent group has exactly 1 liberty, which is 'move')
    for a in adjacent(move):
        if board.get(a) == opp_stone:
            _, libs = get_group_stats(board, a)
            if len(libs) == 1 and move in libs:
                return False # We capture them, so it's not suicide

    # 3. Safe if it connects to a friendly group that has MORE than 1 liberty
    for a in adjacent(move):
        if board.get(a) == stone:
            _, libs = get_group_stats(board, a)
            # If the group has > 1 liberty, connecting to it won't kill us
            # (If it has exactly 1, that liberty is 'move', so connecting kills both)
            if len(libs) > 1:
                return False 

    # If it has no empty neighbors, captures nothing, and connects to no safe groups -> Suicide
    return True


def analyze_move_attributes(position: Position, move_idx: int) -> np.uint16:
    """
    The master analyzer (Fix #4). 
    Calculates all heuristic bits in one pass without copying the board.
    """
    board = position.bitboard
    stone = 2 if position.black_to_play else 1
    opp_stone = 3 - stone
    
    # Bits to set
    is_cap = is_atari = is_save = is_cut = is_conn = is_inc_lib = is_safe = False

    unique_friendly_libs =[] # List of liberty sets
    visited_friendly_stones = set()
    
    unique_enemy_groups =[] # List of tuples (stones, libs)
    visited_enemy_stones = set()
    
    direct_liberties = set()
    
    # 1. Inspect Neighbors (Fixed Deduplication logic)
    for a in adjacent(move_idx):
        val = board.get(a)
        if val == 0:
            direct_liberties.add(a)
        elif val == stone and a not in visited_friendly_stones:
            g_stones, g_libs = get_group_stats(board, a)
            visited_friendly_stones.update(g_stones)
            unique_friendly_libs.append(g_libs)
        elif val == opp_stone and a not in visited_enemy_stones:
            g_stones, g_libs = get_group_stats(board, a)
            visited_enemy_stones.update(g_stones)
            unique_enemy_groups.append((g_stones, g_libs))

    # 2. Evaluate Opponent-based Heuristics (Capture, Atari, Cut)
    for g_stones, g_libs in unique_enemy_groups:
        if len(g_libs) == 1 and move_idx in g_libs:
            is_cap = True
        elif len(g_libs) == 2 and move_idx in g_libs:
            is_atari = True
            
    if len(unique_enemy_groups) >= 2:
        is_cut = True

    # 3. Evaluate Friendly-based Heuristics (Save, Connect)
    for g_libs in unique_friendly_libs:
        if len(g_libs) == 1 and move_idx in g_libs:
            is_save = True
    
    if len(unique_friendly_libs) >= 2:
        is_conn = True

    # 4. Self-Atari and Liberty Increase Logic
    all_libs_before = direct_liberties.copy()
    for g_libs in unique_friendly_libs:
        all_libs_before.update(g_libs)
    all_libs_before.discard(move_idx)
    
    # If we capture anything, or have more than 1 liberty after playing, it's not self-atari
    if is_cap or len(all_libs_before) > 1:
        is_safe = True
        
    if len(all_libs_before) > 0: 
        is_inc_lib = True 

    # 5. Pack the Bits
    res = np.uint16(move_idx)
    if is_cap:     res |= 0x8000 # Bit 15
    if is_atari:   res |= 0x4000 # Bit 14
    if is_save:    res |= 0x2000 # Bit 13
    if is_cut:     res |= 0x1000 # Bit 12
    if is_conn:    res |= 0x0800 # Bit 11
    if is_inc_lib: res |= 0x0400 # Bit 10
    if is_safe:    res |= 0x0200 # Bit 9
    
    return res

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

# ---------------------------------------------------------------------------
# Helper: count total stones on the board
# ---------------------------------------------------------------------------
def count_stones(board: BitBoard) -> int:
    count = 0
    for i in range(total_squares):
        if board.get(i) != 0:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Helper: active zone — indices within max_distance of any existing stone
# ---------------------------------------------------------------------------
def get_active_zone(board: BitBoard, max_distance: int = 2) -> set:
    active = set()
    for i in range(total_squares):
        if board.get(i) != 0:
            active.add(i)
            for a in adjacent(i):
                active.add(a)
                if max_distance >= 2:
                    for b in adjacent(a):
                        active.add(b)
    return active


# ---------------------------------------------------------------------------
# Helper: optimised Ko check — avoids full make_a_move unless single capture
# ---------------------------------------------------------------------------
def is_simple_ko(position: Position, move_idx: int) -> bool:
    if not position.parent:
        return False
    board = position.bitboard
    opp_stone = 1 if position.black_to_play else 2

    capture_count = 0
    for a in adjacent(move_idx):
        if board.get(a) == opp_stone:
            stones, libs = get_group_stats(board, a)
            if len(libs) == 1 and move_idx in libs:
                capture_count += len(stones)

    if capture_count == 1:
        # Only single-stone captures can be simple ko — verify fully
        return make_a_move(position, np.uint16(move_idx)).bitboard == position.parent.bitboard
    return False


# ---------------------------------------------------------------------------
# Move generation (with distance filtering + optimised Ko)
# ---------------------------------------------------------------------------
def move_gen(position: Position):
    # 1. Get pseudo-legal
    moves = pseudo_legal(position.bitboard)

    # 2. Distance filtering (skip in opening — first ~10 stones)
    stone_count = count_stones(position.bitboard)
    if stone_count >= 10:
        active_zone = get_active_zone(position.bitboard, max_distance=2)
        moves = [m for m in moves if int(m) in active_zone]

    # 3. Filter Suicides
    moves = [m for m in moves if not is_suicide(position.bitboard, m, position.black_to_play)]

    # 4. Assign Priority and Analyze
    prioritized_moves = []
    for m in moves:
        prioritized_moves.append(analyze_move_attributes(position, int(m)))

    # 5. Filter Ko (optimised — only full check on single-stone captures)
    if position.parent:
        final_moves = []
        for m in prioritized_moves:
            if m & 0x8000:  # Bit 15 set (Capture)
                move_idx = int(m & 0x1FF)
                if is_simple_ko(position, move_idx):
                    continue
            final_moves.append(m)
        prioritized_moves = final_moves

    # 6. Sort Descending (Best moves first)
    return sorted(prioritized_moves, reverse=True)