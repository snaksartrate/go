import numpy as np

import constants as C
from environment import Position
from moves import get_group_stats, move_gen, make_a_move
from utility_functions import adjacent

board_size = C.board_size
total_squares = board_size * board_size


# ---------------------------------------------------------------------------
# 1. Final Score  (territory scoring — used when both players pass)
#    Score = Territory + Prisoners + Komi (white only)
#    Territory = empty points surrounded entirely by one colour (flood-fill)
# ---------------------------------------------------------------------------

def final_score(position: Position) -> tuple[float, float]:
    """
    Compute the definitive territory score at game end.
    Returns (black_score, white_score).

    Steps from score_calculation.txt:
      1. Flood-fill every empty region.
      2. If a region borders only Black stones -> Black territory.
         If a region borders only White stones -> White territory.
         Otherwise -> dame (neutral, doesn't count).
      3. black_score = black_territory + black_prisoners
         white_score = white_territory + white_prisoners + komi
    """
    board = position.bitboard

    # Flood-fill empty regions to determine territory
    visited = [False] * total_squares
    black_territory = 0
    white_territory = 0

    for i in range(total_squares):
        if visited[i] or board.get(i) != 0:
            continue

        # BFS / flood-fill this empty region
        region = []
        stack = [i]
        visited[i] = True
        borders_black = False
        borders_white = False

        while stack:
            curr = stack.pop()
            region.append(curr)
            for a in adjacent(curr):
                val = board.get(a)
                if val == 0 and not visited[a]:
                    visited[a] = True
                    stack.append(a)
                elif val == 2:  # Black stone
                    borders_black = True
                elif val == 1:  # White stone
                    borders_white = True

        # Assign territory only if the region is enclosed by a single colour
        if borders_black and not borders_white:
            black_territory += len(region)
        elif borders_white and not borders_black:
            white_territory += len(region)
        # else: dame — doesn't count for either side

    black_score = black_territory + position.black_prisoners
    white_score = white_territory + position.white_prisoners + C.komi

    return (black_score, white_score)


# ---------------------------------------------------------------------------
# 2. Static Evaluation  (heuristic — used at depth == 0 during search)
#    A linear combination of:
#      - Approximate territory (empty squares adjacent only to one colour)
#      - Prisoners captured so far
#      - Group safety / strength (liberty-based penalties & bonuses)
#      - Komi
#    Positive = Black is ahead.  Negative = White is ahead.
# ---------------------------------------------------------------------------

def static_eval(position: Position) -> float:
    """
    Heuristic evaluation for mid-game positions.
    Positive score means Black is winning.
    Negative score means White is winning.
    """
    score = 0.0
    board = position.bitboard

    # --- Prisoners & Komi (from score_calculation.txt) ---
    score += position.black_prisoners
    score -= position.white_prisoners
    score -= C.komi

    # --- Board traversal: territory estimate + group safety ---
    visited_stones = set()

    black_territory_estimate = 0
    white_territory_estimate = 0

    # We also flood-fill empty regions for a rough territory count,
    # identical to final_score but weighted as an *estimate* since
    # territories are rarely sealed mid-game.
    visited_empty = [False] * total_squares

    for i in range(total_squares):
        val = board.get(i)

        # -- Empty intersection: flood-fill for approximate territory --
        if val == 0 and not visited_empty[i]:
            region = []
            stack = [i]
            visited_empty[i] = True
            borders_black = False
            borders_white = False

            while stack:
                curr = stack.pop()
                region.append(curr)
                for a in adjacent(curr):
                    av = board.get(a)
                    if av == 0 and not visited_empty[a]:
                        visited_empty[a] = True
                        stack.append(a)
                    elif av == 2:
                        borders_black = True
                    elif av == 1:
                        borders_white = True

            if borders_black and not borders_white:
                black_territory_estimate += len(region)
            elif borders_white and not borders_black:
                white_territory_estimate += len(region)
            # dame / contested: worth 0

        # -- Group safety (Black) --
        elif val == 2 and i not in visited_stones:
            stones, libs = get_group_stats(board, i)
            visited_stones.update(stones)

            if len(libs) == 1:
                score -= 1.5 * len(stones)   # in atari — weighted by group size
            elif len(libs) == 2:
                score -= 0.6 * len(stones)   # vulnerable

            score += 0.05 * len(libs)        # slight reward for thick groups

        # -- Group safety (White) --
        elif val == 1 and i not in visited_stones:
            stones, libs = get_group_stats(board, i)
            visited_stones.update(stones)

            if len(libs) == 1:
                score += 1.5 * len(stones)   # white in atari — good for black
            elif len(libs) == 2:
                score += 0.6 * len(stones)

            score -= 0.05 * len(libs)

    # Territory estimate (weighted slightly below 1.0 because mid-game
    # territories aren't fully sealed yet)
    score += black_territory_estimate * 0.8
    score -= white_territory_estimate * 0.8

    return score


# ---------------------------------------------------------------------------
# 3. Beam search helpers
#    - Tier-based filtering: always keep tactical moves, limit the rest
#    - Progressive widening: wider near root, narrower at leaves
# ---------------------------------------------------------------------------

def get_beam_width(depth: int, max_depth: int) -> int:
    """Wider search near root, narrower at leaves."""
    if depth >= max_depth - 1:   # near root
        return 20
    elif depth >= 2:
        return 12
    else:
        return 8


def filter_moves_by_tier(moves: list, beam_width: int) -> list:
    """Keep all critical moves, limit others to beam_width total."""
    tier1 = []   # Captures, ataris, saves  (bits 15, 14, 13)
    tier2 = []   # Cuts, connects           (bits 12, 11)
    tier3 = []   # Everything else

    for m in moves:
        if m & 0xE000:
            tier1.append(m)
        elif m & 0x1800:
            tier2.append(m)
        else:
            tier3.append(m)

    result = tier1 + tier2 + tier3
    return result[:beam_width]


# ---------------------------------------------------------------------------
# 4. Transposition table  (bounded to avoid memory blow-up)
# ---------------------------------------------------------------------------

_transposition_table: dict = {}
_TT_MAX_SIZE = 100_000


def _tt_store(key, value):
    if len(_transposition_table) >= _TT_MAX_SIZE:
        _transposition_table.clear()   # simple eviction: wipe and start fresh
    _transposition_table[key] = value


# ---------------------------------------------------------------------------
# 5. Alpha-Beta Search
#    From eval.txt:
#      - if previous two moves were pass  -> return final_score (not static_eval)
#      - if depth == 0                    -> return static_eval
#      - else: try all legal moves, then try pass as a last resort
# ---------------------------------------------------------------------------

def alpha_beta(position: Position, depth: int, alpha: float, beta: float,
               max_depth: int = 3) -> tuple[float, np.uint16]:
    """
    Minimax search with Alpha-Beta pruning.
    Returns (best_evaluation_score, best_move_uint16).
    """
    PASS_MOVE = np.uint16(total_squares)

    # 1. Terminal: two consecutive passes -> game over, use real final score
    if position.previous_move is not None and (position.previous_move & 0x1FF) == PASS_MOVE:
        if position.parent is not None and position.parent.previous_move is not None:
            if (position.parent.previous_move & 0x1FF) == PASS_MOVE:
                black_score, white_score = final_score(position)
                return (black_score - white_score), PASS_MOVE

    # 2. Leaf node: depth exhausted -> heuristic evaluation
    if depth == 0:
        return static_eval(position), PASS_MOVE

    # 3. Transposition table lookup
    board_hash = hash(position.bitboard.black.tobytes() + position.bitboard.white.tobytes())
    tt_key = (board_hash, position.black_to_play, depth)
    if tt_key in _transposition_table:
        return _transposition_table[tt_key]

    # 4. Generate legal moves, apply beam search, then append pass at end
    candidate_moves = move_gen(position)
    beam = get_beam_width(depth, max_depth)
    candidate_moves = filter_moves_by_tier(candidate_moves, beam)
    candidate_moves.append(PASS_MOVE)

    best_move = PASS_MOVE

    # 5. Maximizing player (Black)
    if position.black_to_play:
        max_eval = -float('inf')

        for move in candidate_moves:
            next_pos = make_a_move(position, move)
            eval_score, _ = alpha_beta(next_pos, depth - 1, alpha, beta, max_depth)

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break  # beta cutoff

        _tt_store(tt_key, (max_eval, best_move))
        return max_eval, best_move

    # 6. Minimizing player (White)
    else:
        min_eval = float('inf')

        for move in candidate_moves:
            next_pos = make_a_move(position, move)
            eval_score, _ = alpha_beta(next_pos, depth - 1, alpha, beta, max_depth)

            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move

            beta = min(beta, eval_score)
            if beta <= alpha:
                break  # alpha cutoff

        _tt_store(tt_key, (min_eval, best_move))
        return min_eval, best_move


# ---------------------------------------------------------------------------
# 6. Public entry point
# ---------------------------------------------------------------------------

def get_best_move(position: Position, search_depth: int = 3) -> np.uint16:
    """
    Entry point for the engine to find the best move.
    Initializes Alpha-Beta bounds.
    """
    _transposition_table.clear()   # fresh table per top-level search
    best_score, best_move = alpha_beta(
        position, search_depth, -float('inf'), float('inf'),
        max_depth=search_depth
    )
    return best_move

