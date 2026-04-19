# moves.py — Move generation for the Go engine
#
# All move scoring is O(4) per candidate — no BFS, no flood-fill.
# Uses KataGo Board's incremental group data (group_head, group_liberty_count,
# group_stone_count) for O(1) lookups.

from board import Board
from constants import board_size
from environment import Position

_TOTAL = board_size * board_size


# ---------------------------------------------------------------------------
# Move scoring constants — higher = more interesting move
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
    opp = Board.get_opp(pla)
    score = 0

    is_cap = False
    is_save = False
    is_atari = False

    seen_friend_heads = set()
    seen_enemy_heads = set()

    friend_groups = 0
    enemy_groups = 0
    direct_liberties = 0

    capture_size = 0

    for dloc in board.adj:
        adj = loc + dloc
        val = board.board[adj]

        if val == Board.EMPTY:
            direct_liberties += 1

        elif val == pla:
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

    # Composite score
    if is_cap:
        score += _SCORE_CAPTURE + capture_size * 100
    if is_save:
        score += _SCORE_SAVE
    if is_atari:
        score += _SCORE_ATARI
    if friend_groups >= 2:
        score += _SCORE_CONNECT
    if enemy_groups >= 2:
        score += _SCORE_CUT

    # Penalize filling own eye heavily
    if board.is_simple_eye(pla, loc):
        score += _SCORE_EYE_BLOCK

    return score


def move_gen(position: Position, killers: list | None = None) -> list[int]:
    """Generate and score all legal moves for the current player.

    Returns a list of (score, loc) tuples sorted by score descending.
    Killer moves are included and scored with a bonus if legal.

    KataGo's Board does NOT maintain an empty-squares set, so we scan
    all board locations. On 9x9 (81 squares) this is trivial.
    """
    board = position.board
    pla = position.current_player
    ko = board.simple_ko_point

    scored_moves = []

    # Try killer moves first (if provided and legal)
    killer_set = set()
    if killers:
        for k_loc in killers:
            if k_loc is not None and board.would_be_legal(pla, k_loc):
                killer_set.add(k_loc)
                sc = fast_score_move(board, pla, k_loc) + 1500  # killer bonus
                scored_moves.append((sc, k_loc))

    # Scan all board positions for legal moves
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)

            # Skip non-empty
            if board.board[loc] != Board.EMPTY:
                continue

            # Skip ko point
            if loc == ko:
                continue

            # Skip single-stone suicide
            if board.would_be_single_stone_suicide(pla, loc):
                continue

            # Skip if already added as killer
            if loc in killer_set:
                continue

            sc = fast_score_move(board, pla, loc)
            scored_moves.append((sc, loc))

    # Sort descending by score
    scored_moves.sort(key=lambda x: x[0], reverse=True)

    # Return just the locations (score is for ordering only)
    return [loc for _, loc in scored_moves]