# moves.py — Move generation for the Go engine
#
# This file answers the question: "What moves should the engine consider, and in
# what order should it try them?"
#
# Good move ordering is critical for alpha-beta search performance. The earlier
# the engine finds a strong move, the more of the search tree it can prune away.
#
# All move scoring is O(4) per candidate — no BFS, no flood-fill.
# Uses KataGo Board's incremental group data (group_head, group_liberty_count,
# group_stone_count) for O(1) lookups.

from board import Board
from constants import board_size
from environment import Position

# Total number of intersections on the board (9×9 = 81).
_TOTAL = board_size * board_size


# ---------------------------------------------------------------------------
# Move scoring constants — higher = more interesting move
#
# These are rough priority weights. The exact values are tuned heuristically.
# A capture move is always tried before an atari move, which is tried before
# a connecting move, etc.
# ---------------------------------------------------------------------------
_SCORE_CAPTURE    = 10000   # captures an enemy group
_SCORE_SAVE       = 5000    # saves a friendly group from atari
_SCORE_ATARI      = 3000    # puts an enemy group into atari
_SCORE_CONNECT    = 1000    # connects two friendly groups
_SCORE_CUT        = 800     # cuts between two enemy groups
_SCORE_EXTEND     = 200     # increases liberty count of a friendly group
_SCORE_EYE_BLOCK  = -5000   # filling own eye — almost always terrible


def fast_score_move(board: Board, pla: int, loc: int) -> int:
    """Score a candidate move in O(4) using group_head / group_liberty_count.

    Returns an integer score. Higher = more interesting / should be tried first.
    """
    # Get the opponent's color (Board.BLACK=1 → WHITE=2, and vice versa).
    opp = Board.get_opp(pla)
    score = 0

    # Flags set as we inspect each of the up to 4 neighbors.
    is_cap = False    # True if playing here would capture at least one enemy group
    is_save = False   # True if playing here would save a friendly group from atari
    is_atari = False  # True if playing here puts an enemy group into atari (1 liberty)

    # These sets prevent double-counting when two adjacent cells belong to the same group.
    seen_friend_heads = set()
    seen_enemy_heads = set()

    # Counters used to detect connection and cut bonuses.
    friend_groups = 0   # number of distinct friendly groups adjacent to this move
    enemy_groups = 0    # number of distinct enemy groups adjacent to this move
    direct_liberties = 0  # empty cells directly adjacent (immediate liberties if placed)

    # Track the total number of enemy stones that would be captured by this move.
    capture_size = 0

    # Inspect each of the four orthogonal neighbors (up/down/left/right).
    for dloc in board.adj:
        adj = loc + dloc
        val = board.board[adj]

        if val == Board.EMPTY:
            # An empty neighbor means a free liberty if we play here.
            direct_liberties += 1

        elif val == pla:
            # Friendly stone — check if the group it belongs to is in danger.
            head = board.group_head[adj]
            if head not in seen_friend_heads:
                seen_friend_heads.add(head)
                friend_groups += 1
                lib = board.group_liberty_count[head]
                if lib == 1:
                    # This friendly group is in atari — playing here saves it
                    is_save = True
                elif lib == 2:
                    # Friendly group with 2 libs — extending is good
                    score += _SCORE_EXTEND

        elif val == opp:
            # Enemy stone — check if the group it belongs to is vulnerable.
            head = board.group_head[adj]
            if head not in seen_enemy_heads:
                seen_enemy_heads.add(head)
                enemy_groups += 1
                lib = board.group_liberty_count[head]
                if lib == 1:
                    # Enemy group in atari — this captures it
                    is_cap = True
                    capture_size += board.group_stone_count[head]
                elif lib == 2:
                    # Puts enemy into atari
                    is_atari = True

    # Composite score — combine all detected tactical situations.
    if is_cap:
        # Bigger captures score higher so the engine prefers capturing large groups.
        score += _SCORE_CAPTURE + capture_size * 100
    if is_save:
        score += _SCORE_SAVE
    if is_atari:
        score += _SCORE_ATARI
    if friend_groups >= 2:
        # This move connects two separate friendly groups into one — generally good.
        score += _SCORE_CONNECT
    if enemy_groups >= 2:
        # This move sits between two enemy groups — a "cut" that isolates them.
        score += _SCORE_CUT

    # Penalize filling own eye heavily — destroying your own two-eye life is bad.
    if board.is_simple_eye(pla, loc):
        score += _SCORE_EYE_BLOCK

    return score


def move_gen(position: Position, killers: list | None = None, 
             history: dict | None = None) -> list[int]:
    """Generate and score all legal moves for the current player.

    Returns a list of locs sorted by score descending.
    Incorporates killer move bonuses and history heuristic if provided.

    KataGo's Board does NOT maintain an empty-squares set, so we scan
    all board locations. On 9x9 (81 squares) this is trivial.
    """
    board = position.board
    pla = position.current_player
    # simple_ko_point is the one intersection the current player cannot play in
    # due to the simple ko rule (can't immediately recapture a single stone).
    ko = board.simple_ko_point

    scored_moves = []

    # ── Step 1: Handle killer moves ──
    # Killer moves are moves that caused a "beta cutoff" (proved to be very strong)
    # at the same depth in a sibling branch. They are tried first with a 1500 bonus.
    killer_set = set()
    if killers:
        for k_loc in killers:
            if k_loc is not None and board.would_be_legal(pla, k_loc):
                killer_set.add(k_loc)
                sc = fast_score_move(board, pla, k_loc) + 1500  # killer bonus
                scored_moves.append((sc, k_loc))

    # ── Step 2: Scan every intersection for legal moves ──
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)

            # Skip non-empty intersections — can't place a stone there.
            if board.board[loc] != Board.EMPTY:
                continue

            # Skip the ko point — playing here would be illegal this turn.
            if loc == ko:
                continue

            # Skip single-stone suicides — placing here would immediately kill
            # your own lone stone with no captures, which is always illegal.
            if board.would_be_single_stone_suicide(pla, loc):
                continue

            # Skip already-added killer moves to avoid duplicates.
            if loc in killer_set:
                continue

            sc = fast_score_move(board, pla, loc)
            
            # ── History heuristic bonus ──
            # Moves that caused beta cutoffs in previous search iterations are
            # rewarded with extra score so they get tried earlier next time.
            if history is not None and loc < len(history[pla]):
                hist_bonus = history[pla][loc]
                sc += hist_bonus
            
            scored_moves.append((sc, loc))

    # Sort all candidate moves from highest to lowest score.
    # The search will try the highest-scored move first, maximizing pruning.
    scored_moves.sort(key=lambda x: x[0], reverse=True)

    # Return just the locations — scores were only needed for ordering.
    return [loc for _, loc in scored_moves]