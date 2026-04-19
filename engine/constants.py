board_size = 9
komi = 6.5

coords = [
    [(i + 1, j + 1) for j in range(board_size)]
    for i in range(board_size)
]

for_display_coords_x = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J'] # Skip 'I'
for_display_coords_y = [str(i) for i in range(board_size, 0, -1)]

for_display_coords = [
    [(for_display_coords_x[i], for_display_coords_y[j]) for j in range(board_size)]
    for i in range(board_size)
]

STAR_POINTS_9x9 = {(2, 2), (2, 6), (4, 4), (6, 2), (6, 6)}
