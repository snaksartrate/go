# tt.py — Zobrist-keyed Transposition Table for the minimax search
#
# Stores (zobrist_key, depth, score, flag, best_move) tuples to avoid
# re-searching the same position at different paths.

TT_SIZE = 1 << 22          # 4 M entries; ~160 MB at 40 bytes/entry
TT_MASK = TT_SIZE - 1

# Score interpretation flags
TT_EXACT = 0               # score is exact (alpha < score < beta)
TT_LOWER = 1               # score is a lower bound (beta cutoff, fail-high)
TT_UPPER = 2               # score is an upper bound (alpha cutoff, fail-low)

# Transposition table: list of [zobrist, depth, score, flag, best_move]
# or None for empty slots
_tt = [None] * TT_SIZE


def tt_clear():
    """Wipe the entire transposition table (call at start of root search)."""
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
    slot = _tt[zobrist & TT_MASK]
    
    if slot is None:
        return None, None
    
    tt_zobrist, tt_depth, tt_score, tt_flag, tt_move = slot
    
    if tt_zobrist != zobrist:
        return None, None
    
    # Depth check: stored position must have been searched to at least our depth
    if tt_depth < depth:
        # Depth insufficient, but best_move hint is still useful for ordering
        return None, tt_move
    
    # Score validity based on flag
    if tt_flag == TT_EXACT:
        return tt_score, tt_move
    elif tt_flag == TT_LOWER and tt_score >= beta:
        # Fail-high cut: stored score is lower bound, and it beats beta
        return tt_score, tt_move
    elif tt_flag == TT_UPPER and tt_score <= alpha:
        # Fail-low: stored score is upper bound, and it's <= alpha
        return tt_score, tt_move
    
    # No usable score, but best_move hint remains valid
    return None, tt_move


def tt_store(zobrist: int, depth: int, score: float, flag: int, best_move: int):
    """
    Store a position in the transposition table.
    
    Replacement strategy: always replace if depth >= existing depth.
    This ensures deeper information overwrites shallower info.
    """
    idx = zobrist & TT_MASK
    existing = _tt[idx]
    
    # Replace if: slot empty, or new search is deeper
    if existing is None or depth >= existing[1]:
        _tt[idx] = [zobrist, depth, score, flag, best_move]
