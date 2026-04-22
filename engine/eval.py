# eval.py — Search and evaluation for the Go engine
#
# This is the brain of the engine. It contains two main responsibilities:
#
# 1. STATIC EVALUATION — how good is the current board position for Black?
#    Two versions exist:
#    - static_eval():       full 5-component eval — used for display and post-game
#    - static_eval_cheap(): fast O(groups) version — used at every leaf node
#
# 2. SEARCH — which move should the engine play?
#    The engine uses Negamax Alpha-Beta search with several enhancements:
#    - Undo-based play: zero board copies during search (fast!)
#    - Transposition table (TT): skip positions we've already evaluated
#    - Principal Variation Search (PVS): use narrow windows to prune faster
#    - Killer moves: remember moves that were strong at this depth before
#    - History heuristic: reward moves that historically caused cutoffs
#    - Null move pruning: skip evaluation subtrees when position is already strong
#    - Late Move Reductions (LMR): search uninteresting moves at reduced depth
#    - Iterative deepening + aspiration windows: search depth-1 first, then deeper
#    - Superko enforcement: skip moves that repeat a prior board position
#
# Color convention: Board.BLACK = 1, Board.WHITE = 2.
# Score convention: positive = Black ahead, negative = White ahead.

from board import Board
from constants import board_size, komi
from environment import Position
from moves import move_gen
from tables import manhattan
from tt import tt_probe, tt_store, tt_clear, TT_EXACT, TT_LOWER, TT_UPPER
import math

# Convenience constants.
_TOTAL = board_size * board_size   # total intersections (81 for 9×9)
_INF = float('inf')                # used as ±infinity in alpha-beta windows


# ═══════════════════════════════════════════════════════════════════════
# 1. Final Score (game-end scoring using Benson's algorithm)
# ═══════════════════════════════════════════════════════════════════════

def final_score(position: Position) -> tuple[float, float]:
    """Compute definitive territory score at game end using Benson's algorithm.

    Uses board.calculateArea() for pass-alive territory.
    Returns (black_score, white_score).
    """
    board = position.board
    # result will be filled by calculateArea: each cell marked BLACK, WHITE, or EMPTY.
    result = [Board.EMPTY] * board.arrsize

    # calculateArea(result, nonPassAliveStones, safeBigTerritories,
    #               unsafeBigTerritories, isMultiStoneSuicideLegal)
    # Benson's algorithm identifies groups that are unconditionally alive (cannot
    # be captured regardless of future play). Their surrounded territory is counted.
    board.calculateArea(result, True, True, False, False)

    black_territory = 0
    white_territory = 0

    # Count how many intersections are assigned to each player.
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            if result[loc] == Board.BLACK:
                black_territory += 1
            elif result[loc] == Board.WHITE:
                white_territory += 1

    # Final score = territory + captured enemy stones.
    # White also gets komi (compensation for going second).
    black_score = black_territory + position.black_prisoners
    white_score = white_territory + position.white_prisoners + komi

    return (black_score, white_score)


# ═══════════════════════════════════════════════════════════════════════
# 2. Static Evaluation (heuristic, called at depth 0)
# ═══════════════════════════════════════════════════════════════════════

def static_eval(position: Position) -> float:
    """Heuristic evaluation. Positive = Black ahead, negative = White ahead.

    Five components:
      1. Territory (flood-fill with liberty filter)
      2. Eye-space per group
      3. Influence map
      4. Capture threats
      5. Prisoners + komi
    """
    board = position.board
    score = 0.0

    # ── Component 5: Prisoners and komi ──
    # Captured stones and komi are the simplest part of the score.
    score += position.black_prisoners    # Black captured these from White
    score -= position.white_prisoners    # White captured these from Black
    score -= komi                        # White's handicap compensation

    # ── Component 1: Territory estimate ──
    # Flood-fill empty regions. Only count as territory if ALL adjacent
    # groups have ≥ 2 liberties. This is a deliberate approximation —
    # undercounts in ladder situations where a 2-liberty group is dead.
    visited = [False] * board.arrsize
    black_territory = 0
    white_territory = 0

    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            # Skip cells we already processed or cells that have stones.
            if visited[loc] or board.board[loc] != Board.EMPTY:
                continue

            # BFS: expand this empty region to find all connected empty cells.
            region = []
            stack = [loc]
            visited[loc] = True
            borders_black = False       # True if region touches a Black stone
            borders_white = False       # True if region touches a White stone
            all_groups_safe = True  # all adjacent groups have ≥ 2 liberties
            adjacent_heads = set()  # tracks groups we've already checked

            while stack:
                curr = stack.pop()
                region.append(curr)
                for dloc in board.adj:
                    adj = curr + dloc
                    val = board.board[adj]
                    if val == Board.EMPTY and not visited[adj]:
                        visited[adj] = True
                        stack.append(adj)
                    elif val == Board.BLACK:
                        borders_black = True
                        head = board.group_head[adj]
                        if head not in adjacent_heads:
                            adjacent_heads.add(head)
                            # A group with fewer than 2 liberties is weak — we
                            # won't count its surrounding space as secure territory.
                            if board.group_liberty_count[head] < 2:
                                all_groups_safe = False
                    elif val == Board.WHITE:
                        borders_white = True
                        head = board.group_head[adj]
                        if head not in adjacent_heads:
                            adjacent_heads.add(head)
                            if board.group_liberty_count[head] < 2:
                                all_groups_safe = False
                    # WALL is ignored

            # Count the region as territory only if it's surrounded by one color
            # and all bordering groups have at least 2 liberties (are reasonably safe).
            if all_groups_safe:
                if borders_black and not borders_white:
                    black_territory += len(region)
                elif borders_white and not borders_black:
                    white_territory += len(region)

    # Apply a 0.9 discount (territory estimates are imprecise heuristics).
    score += black_territory * 0.9
    score -= white_territory * 0.9

    # ── Component 2: Eye-space scoring ──
    # For each group, count eye points using board.is_simple_eye().
    # Groups with 2+ eyes are alive (big bonus). Groups with 0 eyes
    # get a penalty proportional to size.
    visited_groups = set()

    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            val = board.board[loc]
            if val != Board.BLACK and val != Board.WHITE:
                continue

            head = board.group_head[loc]
            if head in visited_groups:
                continue   # Already processed this group
            visited_groups.add(head)

            pla = val
            stone_count = board.group_stone_count[head]
            lib_count = board.group_liberty_count[head]

            # Count eye points: walk the group's liberties looking for simple eyes.
            # A "simple eye" is an empty cell completely surrounded by friendly stones.
            eye_count = 0
            eyes_checked = set()

            # Walk the group's stones via the circular linked list (group_next).
            cur = head
            while True:
                for dloc in board.adj:
                    adj = cur + dloc
                    if adj not in eyes_checked and board.board[adj] == Board.EMPTY:
                        eyes_checked.add(adj)
                        if board.is_simple_eye(pla, adj):
                            eye_count += 1
                cur = board.group_next[cur]
                if cur == head:
                    break   # Completed the circular linked list

            # Apply eye-based bonuses and penalties.
            sign = 1.0 if pla == Board.BLACK else -1.0

            if eye_count >= 2:
                # Group is alive — bonus proportional to size
                score += sign * 2.0 * stone_count
            elif eye_count == 1:
                # Partial safety
                score += sign * 0.5 * stone_count
            else:
                # No eyes — penalty if few liberties
                if lib_count <= 2:
                    score -= sign * 1.0 * stone_count

            # ── Component 4: Capture threats ──
            # Groups in or near atari are in immediate danger, so penalise them.
            if lib_count == 1:
                # In atari — treat as nearly captured
                score -= sign * 3.0 * stone_count
            elif lib_count == 2:
                # Low liberties — mild penalty
                score -= sign * 0.8 * stone_count

            # Small bonus for thick (high-liberty) groups.
            score += sign * 0.05 * lib_count

    # ── Component 3: Influence map ──
    # Each stone "radiates" influence to nearby empty cells.
    # Influence = 1/(1 + Manhattan_distance). Black influence is positive,
    # White is negative. If the net influence at a cell exceeds a threshold,
    # we count it as probable territory for that player.
    # O(stones × area_within_distance_3) — acceptable at depth 0 only.
    influence = {}  # loc -> float

    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            val = board.board[loc]
            if val != Board.BLACK and val != Board.WHITE:
                continue

            sign = 1.0 if val == Board.BLACK else -1.0
            flat_i = y * board_size + x

            # Spread to all empty cells within Manhattan distance 3.
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < board_size and 0 <= ny < board_size:
                        flat_j = ny * board_size + nx
                        dist = abs(dx) + abs(dy)
                        if dist > 3 or dist == 0:
                            continue
                        target_loc = board.loc(nx, ny)
                        if board.board[target_loc] == Board.EMPTY:
                            # Influence drops off with distance.
                            inf = sign / (1.0 + dist)
                            influence[target_loc] = influence.get(target_loc, 0.0) + inf

    # Threshold: only count cells with a clear net influence for one side.
    for loc, inf_val in influence.items():
        if inf_val > 0.3:
            score += 0.4  # probable Black territory
        elif inf_val < -0.3:
            score -= 0.4  # probable White territory

    return score


def _eval_for_current_player(position: Position) -> float:
    """Return static_eval from the current player's perspective (for negamax).
    
    Negamax requires scores to always be from the perspective of the player
    who just moved. Black's score is positive in static_eval, so we negate
    it when it's White's turn.
    """
    raw = static_eval(position)
    return raw if position.black_to_play else -raw


def static_eval_cheap(position: Position) -> float:
    """Fast O(groups) evaluation for leaf nodes during search.
    
    Uses only group-based metrics (liberty counts, stone counts).
    No flood-fill, no influence map — suitable for being called at
    every leaf node.
    
    Returns score from Black's perspective (positive = Black advantage).
    """
    board = position.board
    score = 0.0
    
    # Component 1: Prisoners and komi (same as full eval)
    score += position.black_prisoners
    score -= position.white_prisoners
    score -= komi
    
    # Component 2: Group scoring based on liberties and stones.
    # For each group, we apply a simple formula:
    #   - 1 liberty (atari): big penalty — the group is about to be captured
    #   - 2 liberties: small penalty — the group is in mild danger
    #   - 3+ liberties: bonus proportional to stones and liberty count
    visited_heads = set()
    
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            val = board.board[loc]
            if val != Board.BLACK and val != Board.WHITE:
                continue
            
            head = board.group_head[loc]
            if head in visited_heads:
                continue   # Already processed this group
            visited_heads.add(head)
            
            sign = 1.0 if val == Board.BLACK else -1.0
            stone_count = board.group_stone_count[head]
            lib_count = board.group_liberty_count[head]
            
            # Atari penalty
            if lib_count == 1:
                score -= sign * 4.0 * stone_count
            elif lib_count == 2:
                score -= sign * 0.5 * stone_count
            else:
                # Reward liberties and thickness
                score += sign * (0.1 * lib_count + 0.3) * stone_count
    
    return score


def _eval_for_current_player_cheap(position: Position) -> float:
    """Return static_eval_cheap from the current player's perspective."""
    raw = static_eval_cheap(position)
    return raw if position.black_to_play else -raw


# ═══════════════════════════════════════════════════════════════════════
# 3. Negamax Alpha-Beta Search with TT, PVS, and LMR
# ═══════════════════════════════════════════════════════════════════════

# Killer move table: killers[depth] = [move1, move2]
# Killer moves are moves that previously caused a beta cutoff at the same depth.
# We carry them forward to try them early next time we search at the same depth.
_killers = []
_MAX_DEPTH = 20

# Futility pruning margins (indexed by depth from leaves).
# If static_eval + margin <= alpha at low depths, prune the whole subtree.
FUTILITY_MARGIN = [0, 2.0, 4.0, 6.0]

# History heuristic table: history[pla][loc] accumulates a bonus whenever a move
# at 'loc' caused a beta cutoff (proved to be strong). Used during move ordering.
_history = None


def _init_killers(max_depth: int):
    """Initialize killer table before each iterative deepening iteration."""
    global _killers
    # Two killer slots per depth level — we remember the two most recent cutoff moves.
    _killers = [[None, None] for _ in range(max_depth + 1)]


def _init_history():
    """Initialize history table once per root search (at start of get_best_move)."""
    global _history
    # One array per player, indexed by board loc.
    arrsize = (board_size + 1) * (board_size + 2) + 1  # Fixed size formula
    _history = {
        Board.BLACK: [0] * arrsize,
        Board.WHITE: [0] * arrsize,
    }


def _age_history():
    """Age history scores between ID iterations (don't zero them)."""
    # Right-shifting divides by 2, keeping historical signal while preventing
    # very old moves from dominating move ordering in future iterations.
    for pla in (Board.BLACK, Board.WHITE):
        h = _history[pla]
        for i in range(len(h)):
            h[i] >>= 1  # Right-shift (divide by 2)


def _update_killers(depth: int, move: int):
    """Store a killer move at the given depth (2 slots, FIFO)."""
    # FIFO: the new move becomes slot 0; the old slot 0 moves to slot 1.
    if depth < len(_killers) and _killers[depth][0] != move:
        _killers[depth][1] = _killers[depth][0]
        _killers[depth][0] = move


def _update_history(pla: int, move: int, depth: int):
    """Increment history table on a beta cutoff."""
    # Deeper cutoffs are more valuable, so bonus = depth² (not just depth).
    if move < len(_history[pla]):
        _history[pla][move] += depth * depth


def _is_capture_move(board: Board, pla: int, loc: int) -> bool:
    """Check if this move captures at least one enemy stone (O(4))."""
    opp = Board.get_opp(pla)
    # A capture occurs when an adjacent enemy group has exactly 1 liberty
    # and we're about to fill it.
    for dloc in board.adj:
        adj = loc + dloc
        if board.board[adj] == opp and board.group_liberty_count[board.group_head[adj]] == 1:
            return True
    return False


def _lmr_reduction(depth: int, move_idx: int) -> int:
    """Compute Late Move Reduction depth reduction.
    
    Standard formula: max(0, floor(0.75 + ln(depth) * ln(move_idx) / 2.25))
    
    LMR: moves tried late in the list (high move_idx) are likely unimportant,
    so we search them at a reduced depth. If one of them turns out to be good,
    we re-search it at full depth.
    """
    # Shallow depths or early moves don't benefit from reduction.
    if depth < 3 or move_idx < 3:
        return 0
    r = int(0.75 + math.log(depth) * math.log(move_idx) / 2.25)
    return max(0, min(r, depth - 1))


def quiescence(position: Position, alpha: float, beta: float, qdepth: int = 4) -> float:
    """Quiescence search: expand only capture moves until position is quiet.
    
    The "horizon effect": at depth 0 the engine might evaluate a position just
    before a large capture, giving a misleading score. Quiescence search fixes
    this by continuing to look at captures until no captures are left (quiet).
    
    Returns score from current player's perspective.
    Limits recursion depth to qdepth to avoid blowup.
    """
    board = position.board
    pla = position.current_player
    
    # "Stand pat" score: how good is the position RIGHT NOW without making any move?
    # If this is already >= beta, we're done — the opponent won't allow this.
    stand_pat = _eval_for_current_player_cheap(position)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat   # We can do at least this well without moving
    if qdepth <= 0:
        return alpha   # Depth limit reached
    
    # Only look at capture moves — skip quiet moves to keep this fast.
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            if board.board[loc] != Board.EMPTY:
                continue
            
            # Skip non-capture moves
            if not _is_capture_move(board, pla, loc):
                continue
            
            # Skip suicides
            if board.would_be_single_stone_suicide(pla, loc):
                continue
            
            # Skip ko
            if loc == board.simple_ko_point:
                continue
            
            position.push(loc)
            
            # Skip superko violations — this board position was seen before.
            if position.is_superko_repeat():
                position.pop()
                continue
            
            # Recurse; negate because the next call scores from the opponent's view.
            score = -quiescence(position, -beta, -alpha, qdepth - 1)
            position.pop()
            
            if score >= beta:
                return beta   # Beta cutoff — opponent won't allow this line
            if score > alpha:
                alpha = score
    
    return alpha


def negamax(position: Position, depth: int, alpha: float, beta: float,
            max_depth: int) -> tuple[float, int]:
    """Negamax alpha-beta with TT, PVS, and LMR.
    
    Negamax is a simplification of minimax: instead of alternating between
    maximizing and minimizing, every call maximizes — but the score is negated
    when returning up a level (since what's bad for one player is good for the other).
    
    Returns (score, best_move_loc) from the current player's perspective.
    Positive score = current player is winning.
    
    alpha: the best score the current player is guaranteed to achieve so far
    beta:  the best score the opponent is guaranteed to achieve so far
    If score >= beta, we prune (the opponent won't let this line happen anyway).
    """
    board = position.board
    original_alpha = alpha
    
    # ── TT Probe ──
    # Before doing any work, check if we've seen this position before at this depth.
    # sit_zobrist() includes whose turn it is (so Black-to-play ≠ White-to-play).
    zobrist = board.sit_zobrist()
    tt_score, tt_move = tt_probe(zobrist, depth, alpha, beta)
    if tt_score is not None:
        # Cache hit — return the stored result directly, no search needed.
        return tt_score, tt_move if tt_move is not None else Board.PASS_LOC
    
    # ── Terminal: two consecutive passes = game over ──
    if position.pass_count >= 2:
        # Both players passed — score the final position using Benson's algorithm.
        bs, ws = final_score(position)
        raw = bs - ws  # positive = Black ahead
        result_score = (raw if position.black_to_play else -raw)
        tt_store(zobrist, depth, result_score, TT_EXACT, Board.PASS_LOC)
        return result_score, Board.PASS_LOC
    
    # ── Leaf: depth exhausted, use quiescence search ──
    if depth <= 0:
        # Don't call static_eval directly — extend into captures first.
        leaf_score = quiescence(position, alpha, beta)
        tt_store(zobrist, depth, leaf_score, TT_EXACT, Board.PASS_LOC)
        return leaf_score, Board.PASS_LOC
    
    pla = position.current_player
    opp = position.opponent
    # Convert from remaining depth to "depth from root" for indexing the killer table.
    current_depth_idx = max_depth - depth
    
    # ── Null move pruning ──
    # "If I skip my turn and the opponent still can't improve beyond beta,
    # then beta is a lower bound for what I can achieve — prune."
    # Safety: skip if pass_count > 0, depth ≤ 2, or friendly group in atari
    # (null move is dangerous when we're under immediate threat).
    if (depth > 2 and
            position.pass_count == 0 and
            position.atari_count[pla] == 0):
        # Try passing at reduced depth (depth-3 is the standard R=3 reduction).
        position.push(Board.PASS_LOC)
        null_score, _ = negamax(position, depth - 3, -beta, -beta + 0.01, max_depth)
        null_score = -null_score
        position.pop()
        if null_score >= beta:
            # Even doing nothing beats beta — opponent won't let this happen.
            tt_store(zobrist, depth, beta, TT_LOWER, Board.PASS_LOC)
            return beta, Board.PASS_LOC
    
    # ── Futility pruning ──
    # At shallow depths near leaves, if static eval + margin is still below alpha,
    # prune the entire subtree (no move can raise the score enough).
    if (1 <= depth <= 3 and
            abs(alpha) < 500 and
            position.atari_count[pla] == 0):
        static = _eval_for_current_player_cheap(position)
        margin = FUTILITY_MARGIN[depth]
        if static + margin <= alpha:
            # Even the best conceivable move at this depth won't beat alpha — prune.
            return alpha, Board.PASS_LOC
    
    # ── Generate moves ──
    killers_for_depth = _killers[current_depth_idx] if current_depth_idx < len(_killers) else None
    candidate_moves = move_gen(position, killers=killers_for_depth, history=_history)
    
    # If the TT suggested a best move from a previous search, try it first.
    # This is very effective because the TT move is often the best move.
    if tt_move is not None and tt_move not in candidate_moves:
        if board.would_be_legal(pla, tt_move):
            candidate_moves.insert(0, tt_move)
    
    # Always include pass as the last resort option.
    candidate_moves.append(Board.PASS_LOC)
    
    best_move = Board.PASS_LOC
    best_score = -_INF
    is_first_move = True
    
    for move_idx, move in enumerate(candidate_moves):
        is_capture = (move != Board.PASS_LOC and _is_capture_move(board, pla, move))
        is_killer = (killers_for_depth is not None and 
                     move in killers_for_depth)
        
        # ── LMR: reduce depth for late, non-promising moves ──
        # Capturing moves and killer moves are always searched at full depth.
        reduction = 0
        if not is_first_move and not is_capture and not is_killer:
            reduction = _lmr_reduction(depth, move_idx)
        
        position.push(move)
        
        # Skip moves that create a repeated board position (superko rule).
        if position.is_superko_repeat():
            position.pop()
            continue
        
        # ── PVS (Principal Variation Search) ──
        # The first move (the most likely best move) is searched with the full window.
        # All subsequent moves are first searched with a zero-width window (fast probe).
        # If the zero-width search beats alpha, we re-search with the full window.
        if is_first_move:
            # Full window search for the first (and likely best) move.
            score, _ = negamax(position, depth - 1, -beta, -alpha, max_depth)
            score = -score   # Negate because the child returns from the opponent's view
            is_first_move = False
        else:
            # Zero-window search: just check if this move beats alpha.
            score, _ = negamax(position, depth - 1 - reduction, -alpha - 1, -alpha, max_depth)
            score = -score
            
            # If it looks promising — either it beat alpha (despite LMR), or
            # it's within the window — do a full re-search at full depth.
            if score > alpha and (reduction > 0 or score < beta):
                score, _ = negamax(position, depth - 1, -beta, -alpha, max_depth)
                score = -score
        
        position.pop()
        
        # Update best score and best move found so far.
        if score > best_score:
            best_score = score
            best_move = move
        
        if score > alpha:
            alpha = score   # We found a move that improves our guaranteed minimum
        
        if alpha >= beta:
            # Beta cutoff: the opponent already has a line better than this.
            # No need to search remaining moves — they can't change anything.
            if move != Board.PASS_LOC:
                _update_killers(current_depth_idx, move)   # Remember this move as a killer
                _update_history(pla, move, depth)           # Reward in the history table
            break
    
    # ── TT Store ──
    # Determine the flag based on whether the score is exact, a lower bound, or upper bound.
    if best_score <= original_alpha:
        flag = TT_UPPER   # All moves were worse than alpha — score is an upper bound
    elif best_score >= beta:
        flag = TT_LOWER   # We got a beta cutoff — score is a lower bound
    else:
        flag = TT_EXACT   # Score falls inside the window — it's exact
    tt_store(zobrist, depth, best_score, flag, best_move)
    
    return best_score, best_move


# ═══════════════════════════════════════════════════════════════════════
# 4. Iterative Deepening with Widening Aspiration Windows
# ═══════════════════════════════════════════════════════════════════════

from opening import book_lookup


def get_best_move(position: Position, search_depth: int = 5) -> int:
    """Entry point: find the best move using iterative deepening.
    
    What is iterative deepening?
    Instead of jumping straight to depth 5, we search depth 1 first, then 2,
    then 3 ... up to the target depth. This sounds wasteful, but the early
    iterations are cheap and they fill the TT and history tables with useful
    information that makes the deeper iterations much faster.
    
    Aspiration windows: instead of starting with alpha=-inf, beta=+inf,
    we start with a small window around the previous iteration's score.
    If the score falls outside the window, we "widen" and retry.
    
    Checks opening book first (eliminates search for move 1–3).
    Uses:
    - Transposition table (cleared once per search)
    - History table (persisted across ID iterations, aged between them)
    - Killer moves (reset for each depth level)
    - Widening aspiration windows for efficiency
    
    Returns a KataGo loc (use Board.PASS_LOC for pass).
    """
    # ── Check opening book first ──
    # If the current position matches a known good opening, skip search entirely.
    book_move = book_lookup(position.board)
    if book_move is not None:
        return book_move
    
    tt_clear()           # Clear TT once per root search
    _init_history()      # Initialize history once per root search
    _init_killers(search_depth)  # Initialize killers ONCE for max depth
    
    best_move = Board.PASS_LOC
    prev_score = 0.0    # Used as the center of the aspiration window
    
    # Iterative deepening loop: search from depth 1 up to the target depth.
    for depth in range(1, search_depth + 1):
        # Age history scores so old data has less influence each iteration.
        if depth > 1:
            _age_history()
        
        if depth <= 2:
            # Shallow depths: use full infinite window (no aspiration).
            alpha = -_INF
            beta = _INF
            score, move = negamax(position, depth, alpha, beta, max_depth=depth)
        else:
            # Widening aspiration window for depth >= 3.
            # Start with a narrow window around the previous iteration's score.
            delta = 3.0
            alpha = prev_score - delta
            beta = prev_score + delta
            
            while True:
                score, move = negamax(position, depth, alpha, beta, max_depth=depth)
                
                if score <= alpha:
                    # "Fail-low": the true score is below our lower bound.
                    # Widen the lower bound and retry.
                    alpha -= delta * 2
                    delta *= 2
                elif score >= beta:
                    # "Fail-high": the true score is above our upper bound.
                    # Widen the upper bound and retry.
                    beta += delta * 2
                    delta *= 2
                else:
                    # Score inside window — we have an accurate result for this depth.
                    break
        
        prev_score = score
        best_move = move    # The move from the deepest completed iteration
    
    return best_move
