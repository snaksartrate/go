# constants.py — Global settings and coordinate mappings for the Go engine
#
# This file is the single source of truth for all board configuration.
# Every other file imports from here so you only have to change things once.

# The board is 9×9 (standard small Go board).
board_size = 9

# Komi is the points added to White's score to compensate for Black going first.
# 6.5 is the standard komi for 9×9 Go.
komi = 6.5

# coords[i][j] gives the (row, col) pair for board position (i, j),
# using 1-based indexing (so the top-left corner is (1,1) not (0,0)).
coords = [
    [(i + 1, j + 1) for j in range(board_size)]
    for i in range(board_size)
]

# Column labels for displaying the board to a human.
# Note: 'I' is skipped on purpose — it's a Go convention to avoid confusion with '1'.
for_display_coords_x = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J'] # Skip 'I'

# Row labels for display, counting DOWN from board_size (9) to 1.
# Row 0 on screen = label "9", row 8 on screen = label "1".
for_display_coords_y = [str(i) for i in range(board_size, 0, -1)]

# for_display_coords[i][j] maps board column i and board row j
# to a human-readable label pair like ('E', '5').
for_display_coords = [
    [(for_display_coords_x[i], for_display_coords_y[j]) for j in range(board_size)]
    for i in range(board_size)
]

# The five star points (hoshi) on a 9×9 board, given as (col, row) pairs
# using 1-based indexing. These are the marked dots you see on a real board.
STAR_POINTS_9x9 = {(2, 2), (2, 6), (4, 4), (6, 2), (6, 6)}
