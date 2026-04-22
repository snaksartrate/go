# opening.py — Opening book for quick early-game move selection
#
# Stores known-good opening sequences for 9×9 to avoid expensive search
# on the first 3–5 moves.

from board import Board


# Precomputed tengen (center point)
def _tengen_9x9():
    """Center point of a 9x9 board."""
    return Board.loc_static(4, 4, 9)


TENGEN = _tengen_9x9()

# Corner points for 3-3 opening
def _corner_3_3():
    """3-3 point (lower-left corner, from Black's perspective)."""
    return Board.loc_static(2, 2, 9)


CORNER_3_3 = _corner_3_3()

# Precomputed opening book: key is a frozenset of (pla, loc) tuples
# representing stones on the board (in sequence), value is the recommended move.
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
    # Build a set of all non-empty stones currently on the board
    stones = frozenset(
        (board.board[board.loc(x, y)], board.loc(x, y))
        for y in range(board.y_size)
        for x in range(board.x_size)
        if board.board[board.loc(x, y)] in (Board.BLACK, Board.WHITE)
    )
    
    # Look up in the book
    return OPENING_BOOK.get(stones)
