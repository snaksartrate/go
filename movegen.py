from environment import Position, Board

def get_pseudo_legal_black(board : Board):
    pseudo_legal = []
    for intersection in board.grid:
        if intersection == 0:
            intersection = 1
            pseudo_legal.append(board.copy())
            intersection = 0
    return pseudo_legal

def move_gen_black(board : Board):
    pseudo_legal = []
    for intersection in board.grid:
        if intersection == 0:
            intersection = 1
            pseudo_legal.append(board)
            intersection = 0
    return pseudo_legal

def move_gen_white(board : Board):
    return []

def move_gen(position : Position):
    pseudo_legal = move_gen_black(position.board) if position.black_to_play else move_gen_white(position.board)