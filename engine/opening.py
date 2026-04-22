# opening.py — Opening book for quick early-game move selection
#
# Stores known-good opening sequences for 9×9 to avoid expensive search
# on the first 3–5 moves.
#
# Why an opening book? The search algorithm is very good in the mid/late game
# but standard openings in Go are well-understood. Hardcoding a few key first
# moves saves search time and ensures the engine plays sensibly from move 1.

from board import Board


# Precomputed tengen (center point)
def _tengen_9x9():
    """Center point of a 9x9 board."""
    # Tengen is the very center of the board — a classic strong first move.
    # Board.loc_static(x, y, board_size) converts (x=4, y=4) to the engine's
    # internal location integer without needing a Board instance.
    return Board.loc_static(4, 4, 9)


TENGEN = _tengen_9x9()

# Corner points for 3-3 opening
def _corner_3_3():
    """3-3 point (lower-left corner, from Black's perspective)."""
    # The 3-3 point is a common corner approach in 9×9 Go.
    # It immediately secures corner territory.
    return Board.loc_static(2, 2, 9)


CORNER_3_3 = _corner_3_3()

# Precomputed opening book: key is a frozenset of (pla, loc) tuples
# representing stones on the board (in sequence), value is the recommended move.
#
# A frozenset is used as the key because sets are order-independent — we just
# care about which stones are on the board, not the order they were placed.
OPENING_BOOK = {
    # Move 1: Empty board → Play tengen (center)
    frozenset(): TENGEN,
    
    # Move 2: After Black plays tengen → White plays 3-3
    frozenset([(Board.BLACK, TENGEN)]): CORNER_3_3,
}


def book_lookup(board: Board) -> int | None:
    """Check if current board position matches an opening book entry.
    
    Returns the recommended move (loc) if found, else None.
    """
    # Scan the entire board and collect all placed stones as (color, location) pairs.
    # This snapshot is then used to look up a matching entry in the opening book.
    stones = frozenset(
        (board.board[board.loc(x, y)], board.loc(x, y))
        for y in range(board.y_size)
        for x in range(board.x_size)
        if board.board[board.loc(x, y)] in (Board.BLACK, Board.WHITE)
    )
    
    # Look up in the book — returns a recommended move, or None if position is unknown.
    return OPENING_BOOK.get(stones)
