board_size = 9
komi = 6.5
mp = {'w' : -1, '_' : 0, 'b' : 1}
val = ('w', '_', 'b') # -1 corresponds to white on the grid, 0 to empty square, and 1 to black
valid_notation_chars = ('_', 'w', 'b') # i dont know why i have two vars doing the same thing but i think i should keep it; also, i dont want to think about it

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

