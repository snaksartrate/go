# eval.py — Search and evaluation for the Go engine
#
# Negamax alpha-beta with:
#   - Undo-based play (zero board copies during search)
#   - Killer moves (2 per depth)
#   - History heuristic (depth² bonus on cutoff)
#   - Null move pruning (with safety: skip if pass_count>0, depth≤2, or in atari)
#   - Iterative deepening with aspiration windows
#
# Static evaluation has 5 components:
#   1. Territory (flood-fill, require ≥2 liberties on all adjacent groups)
#   2. Eye-space scoring (is_simple_eye per group, 2+ eyes = alive)
#   3. Influence map (1/(1+manhattan_dist) within distance 3)
#   4. Capture threats (atari/low-liberty penalties)
#   5. Prisoners and komi
#
# Color convention: Board.BLACK = 1, Board.WHITE = 2.

from board import Board
from constants import board_size, komi
from environment import Position
from moves import move_gen
from tables import manhattan

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


# ═══════════════════════════════════════════════════════════════════════
# 3. Negamax Alpha-Beta Search
# ═══════════════════════════════════════════════════════════════════════

# Killer move table: killers[depth] = [move1, move2]
_killers = []
_MAX_DEPTH = 20

# History heuristic: history[pla][flat_index]
# Indexed by player (BLACK=1, WHITE=2) and a flat board index.
_history = None


def _init_search_tables(max_depth: int):
    """Initialize killer and history tables before a new search."""
    global _killers, _history
    _killers = [[None, None] for _ in range(max_depth + 1)]
    _history = {
        Board.BLACK: [0] * (board_size + 2) * (board_size + 1) * 2,
        Board.WHITE: [0] * (board_size + 2) * (board_size + 1) * 2,
    }


def _update_killers(depth: int, move: int):
    """Store a killer move at the given depth (2 slots, FIFO)."""
    if _killers[depth][0] != move:
        _killers[depth][1] = _killers[depth][0]
        _killers[depth][0] = move


def _update_history(pla: int, move: int, depth: int):
    """Increment history table on a beta cutoff."""
    if move < len(_history[pla]):
        _history[pla][move] += depth * depth


def _has_group_in_atari(board: Board, pla: int) -> bool:
    """Check if any group of the given player has exactly 1 liberty."""
    seen = set()
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            if board.board[loc] == pla:
                head = board.group_head[loc]
                if head not in seen:
                    seen.add(head)
                    if board.group_liberty_count[head] == 1:
                        return True
    return False


def negamax(position: Position, depth: int, alpha: float, beta: float,
            max_depth: int) -> tuple[float, int]:
    """Negamax alpha-beta with undo-based play.

    Returns (score, best_move_loc) from the current player's perspective.
    Positive score = current player is winning.
    """
    board = position.board

    # ── Terminal: two consecutive passes = game over ──
    if position.pass_count >= 2:
        bs, ws = final_score(position)
        raw = bs - ws  # positive = Black ahead
        return (raw if position.black_to_play else -raw), Board.PASS_LOC

    # ── Leaf: depth exhausted ──
    if depth <= 0:
        return _eval_for_current_player(position), Board.PASS_LOC

    pla = position.current_player
    opp = position.opponent
    current_depth_idx = max_depth - depth

    # ── Null move pruning ──
    # Safety: skip if pass_count > 0, depth ≤ 2, or friendly group in atari
    if (depth > 2 and
            position.pass_count == 0 and
            not _has_group_in_atari(board, pla)):
        # Try passing at reduced depth
        position.push(Board.PASS_LOC)
        null_score, _ = negamax(position, depth - 3, -beta, -beta + 0.01, max_depth)
        null_score = -null_score
        position.pop()
        if null_score >= beta:
            return beta, Board.PASS_LOC

    # ── Generate moves ──
    killers_for_depth = _killers[current_depth_idx] if current_depth_idx < len(_killers) else None
    candidate_moves = move_gen(position, killers=killers_for_depth)

    # Append pass as the last option
    candidate_moves.append(Board.PASS_LOC)

    best_move = Board.PASS_LOC
    best_score = -_INF

    for move in candidate_moves:
        position.push(move)
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

    return best_score, best_move


# ═══════════════════════════════════════════════════════════════════════
# 4. Iterative Deepening with Aspiration Windows
# ═══════════════════════════════════════════════════════════════════════

def get_best_move(position: Position, search_depth: int = 5) -> int:
    """Entry point: find the best move using iterative deepening.

    Returns a KataGo loc (use Board.PASS_LOC for pass).
    """
    _init_search_tables(search_depth)

    best_move = Board.PASS_LOC
    prev_score = 0.0

    for depth in range(1, search_depth + 1):
        if depth <= 2:
            # Shallow depths: full window
            alpha = -_INF
            beta = _INF
        else:
            # Aspiration window: ±1.5 from previous iteration
            alpha = prev_score - 1.5
            beta = prev_score + 1.5

        score, move = negamax(position, depth, alpha, beta, max_depth=depth)

        # Handle aspiration window failures
        if score <= alpha:
            # Fail-low: re-search with full alpha
            score, move = negamax(position, depth, -_INF, beta, max_depth=depth)
        elif score >= beta:
            # Fail-high: re-search with full beta
            score, move = negamax(position, depth, alpha, _INF, max_depth=depth)

        prev_score = score
        best_move = move

    return best_move
