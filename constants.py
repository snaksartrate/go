board_size = 9
komi = 6.5

# we will require this since we are now working on a new branch
# 0 is blank, 1 is white, 2 is black

ENCODE_MAP = [0b00, 0b01, 0b10]

DECODE_MAP = {
    0b00: 0,
    0b01: 1,
    0b10: 2
}

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

