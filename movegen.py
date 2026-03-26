from environment import Position, Board

def get_pseudo_legal(board : Board, black_to_play : bool) -> list:
    pseudo_legal = [board] # if the player decides to pass
    stone = 1 if black_to_play else 2
    board_size = len(board.grid)
    for i in range(board_size * board_size):
        if not board.grid[i]:
            board.grid[i] = stone
            pseudo_legal.append(board.copy())
            board.grid[i] = 0
    return pseudo_legal

def validate(pseudo_legal : list, black_to_play : bool) -> list:
    for i in range(len(pseudo_legal)):
        # perform validity checks, remove invalid moves
        pass
    return pseudo_legal

def move_gen(position : Position):
    pseudo_legal = get_pseudo_legal(position.black_to_play, position.black_to_play)
    moves = validate(pseudo_legal, position.black_to_play)
