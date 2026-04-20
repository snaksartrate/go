# eval.py — Search and evaluation for the Go engine
#
# Negamax alpha-beta with:
#   - Undo-based play (zero board copies during search)
#   - Transposition table (TT) for avoiding redundant searches
#   - Principal Variation Search (PVS) for zero-width window efficiency
#   - Killer moves (2 per depth)
#   - History heuristic (depth² bonus on cutoff)
#   - Null move pruning (with safety: skip if pass_count>0, depth≤2, or in atari)
#   - Late Move Reductions (LMR) for non-promising moves
#   - Iterative deepening with widening aspiration windows
#
# Static evaluation:
#   - static_eval_cheap(): O(groups) eval for leaf nodes
#   - static_eval(): full 5-component eval for display/post-game
#
# Color convention: Board.BLACK = 1, Board.WHITE = 2.

from board import Board
from constants import board_size, komi
from environment import Position
from moves import move_gen
from tables import manhattan
from tt import tt_probe, tt_store, tt_clear, TT_EXACT, TT_LOWER, TT_UPPER
import math

_TOTAL = board_size * board_size
_INF = float('inf')


# ═══════════════════════════════════════════════════════════════════════
# 1. Final Score (game-end scoring using Benson's algorithm)
# ═══════════════════════════════════════════════════════════════════════

def final_score(position: Position) -> tuple[float, float]:
    """Compute definitive territory score at game end using Benson's algorithm.

    Uses board.calculateArea() for pass-alive territory.
    Returns (black_score, white_score).
    """
    board = position.board
    result = [Board.EMPTY] * board.arrsize

    # calculateArea(result, nonPassAliveStones, safeBigTerritories,
    #               unsafeBigTerritories, isMultiStoneSuicideLegal)
    board.calculateArea(result, True, True, False, False)

    black_territory = 0
    white_territory = 0

    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            if result[loc] == Board.BLACK:
                black_territory += 1
            elif result[loc] == Board.WHITE:
                white_territory += 1

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
    score += position.black_prisoners
    score -= position.white_prisoners
    score -= komi

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
            if visited[loc] or board.board[loc] != Board.EMPTY:
                continue

            # BFS this empty region
            region = []
            stack = [loc]
            visited[loc] = True
            borders_black = False
            borders_white = False
            all_groups_safe = True  # all adjacent groups have ≥ 2 liberties
            adjacent_heads = set()

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

            if all_groups_safe:
                if borders_black and not borders_white:
                    black_territory += len(region)
                elif borders_white and not borders_black:
                    white_territory += len(region)

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
                continue
            visited_groups.add(head)

            pla = val
            stone_count = board.group_stone_count[head]
            lib_count = board.group_liberty_count[head]

            # Count eye points: walk the group's liberties looking for simple eyes
            eye_count = 0
            eyes_checked = set()

            # Walk the group's stones via linked list
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
                    break

            # Scoring
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
            if lib_count == 1:
                # In atari — treat as nearly captured
                score -= sign * 3.0 * stone_count
            elif lib_count == 2:
                # Low liberties — mild penalty
                score -= sign * 0.8 * stone_count

            # Reward thick groups
            score += sign * 0.05 * lib_count

    # ── Component 3: Influence map ──
    # For each stone, spread influence to empty cells within Manhattan
    # distance 3. influence = 1/(1 + distance). Black positive, White negative.
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

            # Spread to all empty cells within Manhattan distance 3
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
                            inf = sign / (1.0 + dist)
                            influence[target_loc] = influence.get(target_loc, 0.0) + inf

    # Sum influence as territory estimate (discounted)
    for loc, inf_val in influence.items():
        if inf_val > 0.3:
            score += 0.4  # probable Black territory
        elif inf_val < -0.3:
            score -= 0.4  # probable White territory

    return score


def _eval_for_current_player(position: Position) -> float:
    """Return static_eval from the current player's perspective (for negamax)."""
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
    
    # Component 1: Prisoners and komi
    score += position.black_prisoners
    score -= position.white_prisoners
    score -= komi
    
    # Component 2: Group scoring based on liberties and stones
    visited_heads = set()
    
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            val = board.board[loc]
            if val != Board.BLACK and val != Board.WHITE:
                continue
            
            head = board.group_head[loc]
            if head in visited_heads:
                continue
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
_killers = []
_MAX_DEPTH = 20

# Futility pruning margins (indexed by depth from leaves)
FUTILITY_MARGIN = [0, 2.0, 4.0, 6.0]

# History heuristic: history[pla][flat_index]
# Indexed by player (BLACK=1, WHITE=2) and a flat board index.
_history = None


def _init_killers(max_depth: int):
    """Initialize killer table before each iterative deepening iteration."""
    global _killers
    _killers = [[None, None] for _ in range(max_depth + 1)]


def _init_history():
    """Initialize history table once per root search (at start of get_best_move)."""
    global _history
    arrsize = (board_size + 1) * (board_size + 2) + 1  # Fixed size formula
    _history = {
        Board.BLACK: [0] * arrsize,
        Board.WHITE: [0] * arrsize,
    }


def _age_history():
    """Age history scores between ID iterations (don't zero them)."""
    for pla in (Board.BLACK, Board.WHITE):
        h = _history[pla]
        for i in range(len(h)):
            h[i] >>= 1  # Right-shift (divide by 2)


def _update_killers(depth: int, move: int):
    """Store a killer move at the given depth (2 slots, FIFO)."""
    if depth < len(_killers) and _killers[depth][0] != move:
        _killers[depth][1] = _killers[depth][0]
        _killers[depth][0] = move


def _update_history(pla: int, move: int, depth: int):
    """Increment history table on a beta cutoff."""
    if move < len(_history[pla]):
        _history[pla][move] += depth * depth


def _is_capture_move(board: Board, pla: int, loc: int) -> bool:
    """Check if this move captures at least one enemy stone (O(4))."""
    opp = Board.get_opp(pla)
    for dloc in board.adj:
        adj = loc + dloc
        if board.board[adj] == opp and board.group_liberty_count[board.group_head[adj]] == 1:
            return True
    return False


def _lmr_reduction(depth: int, move_idx: int) -> int:
    """Compute Late Move Reduction depth reduction.
    
    Standard formula: max(0, floor(0.75 + ln(depth) * ln(move_idx) / 2.25))
    """
    if depth < 3 or move_idx < 3:
        return 0
    r = int(0.75 + math.log(depth) * math.log(move_idx) / 2.25)
    return max(0, min(r, depth - 1))


def quiescence(position: Position, alpha: float, beta: float, qdepth: int = 4) -> float:
    """Quiescence search: expand only capture moves until position is quiet.
    
    Returns score from current player's perspective.
    Limits recursion depth to qdepth to avoid blowup.
    """
    board = position.board
    pla = position.current_player
    
    # Evaluate the current position (stand pat)
    stand_pat = _eval_for_current_player_cheap(position)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat
    if qdepth <= 0:
        return alpha
    
    # Generate capture moves only
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
            score = -quiescence(position, -beta, -alpha, qdepth - 1)
            position.pop()
            
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
    
    return alpha


def negamax(position: Position, depth: int, alpha: float, beta: float,
            max_depth: int) -> tuple[float, int]:
    """Negamax alpha-beta with TT, PVS, and LMR.
    
    Returns (score, best_move_loc) from the current player's perspective.
    Positive score = current player is winning.
    """
    board = position.board
    original_alpha = alpha
    
    # ── TT Probe ──
    zobrist = board.sit_zobrist()
    tt_score, tt_move = tt_probe(zobrist, depth, alpha, beta)
    if tt_score is not None:
        return tt_score, tt_move if tt_move is not None else Board.PASS_LOC
    
    # ── Terminal: two consecutive passes = game over ──
    if position.pass_count >= 2:
        bs, ws = final_score(position)
        raw = bs - ws  # positive = Black ahead
        result_score = (raw if position.black_to_play else -raw)
        tt_store(zobrist, depth, result_score, TT_EXACT, Board.PASS_LOC)
        return result_score, Board.PASS_LOC
    
    # ── Leaf: depth exhausted, use quiescence search ──
    if depth <= 0:
        leaf_score = quiescence(position, alpha, beta)
        tt_store(zobrist, depth, leaf_score, TT_EXACT, Board.PASS_LOC)
        return leaf_score, Board.PASS_LOC
    
    pla = position.current_player
    opp = position.opponent
    current_depth_idx = max_depth - depth
    
    # ── Null move pruning ──
    # Safety: skip if pass_count > 0, depth ≤ 2, or friendly group in atari
    if (depth > 2 and
            position.pass_count == 0 and
            position.atari_count[pla] == 0):
        # Try passing at reduced depth
        position.push(Board.PASS_LOC)
        null_score, _ = negamax(position, depth - 3, -beta, -beta + 0.01, max_depth)
        null_score = -null_score
        position.pop()
        if null_score >= beta:
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
            return alpha, Board.PASS_LOC
    
    # ── Generate moves ──
    killers_for_depth = _killers[current_depth_idx] if current_depth_idx < len(_killers) else None
    candidate_moves = move_gen(position, killers=killers_for_depth, history=_history)
    
    # Try TT move first (best move hint for move ordering)
    if tt_move is not None and tt_move not in candidate_moves:
        if board.would_be_legal(pla, tt_move):
            candidate_moves.insert(0, tt_move)
    
    # Append pass as the last option
    candidate_moves.append(Board.PASS_LOC)
    
    best_move = Board.PASS_LOC
    best_score = -_INF
    is_first_move = True
    
    for move_idx, move in enumerate(candidate_moves):
        is_capture = (move != Board.PASS_LOC and _is_capture_move(board, pla, move))
        is_killer = (killers_for_depth is not None and 
                     move in killers_for_depth)
        
        # LMR: reduce depth for late, non-promising moves
        reduction = 0
        if not is_first_move and not is_capture and not is_killer:
            reduction = _lmr_reduction(depth, move_idx)
        
        position.push(move)
        
        # PVS: first move gets full window, others get zero-window
        if is_first_move:
            score, _ = negamax(position, depth - 1, -beta, -alpha, max_depth)
            score = -score
            is_first_move = False
        else:
            # Zero-window search (with LMR reduction)
            score, _ = negamax(position, depth - 1 - reduction, -alpha - 1, -alpha, max_depth)
            score = -score
            
            # Re-search if promising
            if score > alpha and (reduction > 0 or score < beta):
                score, _ = negamax(position, depth - 1, -beta, -alpha, max_depth)
                score = -score
        
        position.pop()
        
        if score > best_score:
            best_score = score
            best_move = move
        
        if score > alpha:
            alpha = score
        
        if alpha >= beta:
            # Beta cutoff — update killer and history tables
            if move != Board.PASS_LOC:
                _update_killers(current_depth_idx, move)
                _update_history(pla, move, depth)
            break
    
    # ── TT Store ──
    if best_score <= original_alpha:
        flag = TT_UPPER
    elif best_score >= beta:
        flag = TT_LOWER
    else:
        flag = TT_EXACT
    tt_store(zobrist, depth, best_score, flag, best_move)
    
    return best_score, best_move


# ═══════════════════════════════════════════════════════════════════════
# 4. Iterative Deepening with Widening Aspiration Windows
# ═══════════════════════════════════════════════════════════════════════

from opening import book_lookup


def get_best_move(position: Position, search_depth: int = 5) -> int:
    """Entry point: find the best move using iterative deepening.
    
    Checks opening book first (eliminates search for move 1–3).
    Uses:
    - Transposition table (cleared once per search)
    - History table (persisted across ID iterations, aged between them)
    - Killer moves (reset for each depth level)
    - Widening aspiration windows for efficiency
    
    Returns a KataGo loc (use Board.PASS_LOC for pass).
    """
    # ── Check opening book first ──
    book_move = book_lookup(position.board)
    if book_move is not None:
        return book_move
    
    tt_clear()           # Clear TT once per root search
    _init_history()      # Initialize history once per root search
    _init_killers(search_depth)  # Initialize killers ONCE for max depth
    
    best_move = Board.PASS_LOC
    prev_score = 0.0
    
    for depth in range(1, search_depth + 1):
        # Age history between ID iterations (killers stay; we just search deeper)
        if depth > 1:
            _age_history()
        
        if depth <= 2:
            # Shallow depths: full window
            alpha = -_INF
            beta = _INF
            score, move = negamax(position, depth, alpha, beta, max_depth=depth)
        else:
            # Widening aspiration window for depth >= 3
            delta = 3.0
            alpha = prev_score - delta
            beta = prev_score + delta
            
            while True:
                score, move = negamax(position, depth, alpha, beta, max_depth=depth)
                
                if score <= alpha:
                    # Fail-low: widen lower bound
                    alpha -= delta * 2
                    delta *= 2
                elif score >= beta:
                    # Fail-high: widen upper bound
                    beta += delta * 2
                    delta *= 2
                else:
                    # Score inside window — good
                    break
        
        prev_score = score
        best_move = move
    
    return best_move
