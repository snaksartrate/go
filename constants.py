board_size = 9
komi = 6.5
valid_notation_chars = ('_', 'w', 'b')

for_display_coords_x = [chr(ord('A') + i) for i in range(board_size)]
for_display_coords_y = [str(i + 1) for i in range(board_size)]

for_display_coords = [
    [(for_display_coords_x[i], for_display_coords_y[j]) for j in range(board_size)]
    for i in range(board_size)
]

coords = [
    [(i + 1, j + 1) for j in range(board_size)]
    for i in range(board_size)
]