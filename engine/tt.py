# tt.py — Zobrist-keyed Transposition Table for the minimax search
#
# What is a transposition table (TT)?
# During search, the engine often reaches the same board position via different
# move orders (called "transpositions"). Without the TT, it would re-search those
# positions from scratch every time, wasting a lot of time.
# The TT stores results from previously completed searches so they can be reused.
#
# How is a position identified?
# Each board position is identified by its Zobrist hash — a 64-bit integer that
# uniquely (with very high probability) represents the board layout. It is computed
# incrementally as stones are placed/removed, making it O(1).
#
# Each entry stores: (zobrist_key, depth, score, flag, best_move)
# Stores (zobrist_key, depth, score, flag, best_move) tuples to avoid
# re-searching the same position at different paths.

# Number of TT slots. 1<<22 = 4,194,304 slots (about 4 million).
# The & mask trick replaces a slow modulo with a fast bitwise AND.
TT_SIZE = 1 << 22          # 4 M entries; ~160 MB at 40 bytes/entry
TT_MASK = TT_SIZE - 1

# Score interpretation flags — tell the searcher how to interpret the stored score.
TT_EXACT = 0               # score is exact (alpha < score < beta)
TT_LOWER = 1               # score is a lower bound (beta cutoff, fail-high)
TT_UPPER = 2               # score is an upper bound (alpha cutoff, fail-low)

# The actual transposition table: a flat list of slots.
# Each slot is either None (empty) or [zobrist, depth, score, flag, best_move].
_tt = [None] * TT_SIZE


def tt_clear():
    """Wipe the entire transposition table (call at start of root search)."""
    # We reset the TT at the beginning of each new root search so stale results
    # from the previous move don't interfere. This is the simplest strategy;
    # alternatives like aging exist but add complexity.
    global _tt
    _tt = [None] * TT_SIZE


def tt_probe(zobrist: int, depth: int, alpha: float, beta: float) -> tuple[float | None, int | None]:
    """
    Probe the TT for a position.
    
    Returns: (score, best_move)
        - score: the cached score if TT hit with sufficient depth and compatible flag, else None
        - best_move: the best move hint (for move ordering) if available, else None
    
    A TT hit requires:
        - zobrist key matches
        - stored depth >= requested depth
        - flag is compatible with [alpha, beta]:
          - TT_EXACT: always valid
          - TT_LOWER (fail-high): only valid if stored_score >= beta
          - TT_UPPER (fail-low): only valid if stored_score <= alpha
    """
    # Map the 64-bit zobrist key to a table slot using a bitmask (fast modulo).
    slot = _tt[zobrist & TT_MASK]
    
    # Slot is empty — no hit.
    if slot is None:
        return None, None
    
    tt_zobrist, tt_depth, tt_score, tt_flag, tt_move = slot
    
    # Hash collision — different position mapped to same slot (rare but possible).
    if tt_zobrist != zobrist:
        return None, None
    
    # Depth check: stored position must have been searched to at least our depth.
    # If the stored search was shallower, the score may not be reliable enough,
    # but we can still use the best_move as a hint for move ordering.
    if tt_depth < depth:
        # Depth insufficient, but best_move hint is still useful for ordering
        return None, tt_move
    
    # Use the score only if the stored flag is compatible with our current window.
    if tt_flag == TT_EXACT:
        return tt_score, tt_move
    elif tt_flag == TT_LOWER and tt_score >= beta:
        # Fail-high cut: stored score is lower bound, and it beats beta
        return tt_score, tt_move
    elif tt_flag == TT_UPPER and tt_score <= alpha:
        # Fail-low: stored score is upper bound, and it's <= alpha
        return tt_score, tt_move
    
    # Score can't be trusted for this window, but we can still use best_move for ordering.
    return None, tt_move


def tt_store(zobrist: int, depth: int, score: float, flag: int, best_move: int):
    """
    Store a position in the transposition table.
    
    Replacement strategy: always replace if depth >= existing depth.
    This ensures deeper information overwrites shallower info.
    """
    # Determine which slot this position maps to.
    idx = zobrist & TT_MASK
    existing = _tt[idx]
    
    # Only replace if the slot is empty, or our new search went deeper.
    # Deeper searches produce more reliable scores, so we prefer them.
    if existing is None or depth >= existing[1]:
        _tt[idx] = [zobrist, depth, score, flag, best_move]
