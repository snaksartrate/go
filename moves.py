import numpy as np

import constants as C
import utility_functions as uf
from environment import Position, BitBoard

board_size = C.board_size

def pseudo_legal(board : BitBoard) -> list[np.uint16]:
    pseudo_legal = []
    for i in range(board_size * board_size):
        if not board.get(i):
            pseudo_legal.append(np.uint16(i))
    return pseudo_legal

def remove_suicides(board : BitBoard, moves : list[np.uint16], black : bool) -> list[np.uint16]:
    stone = 2 if black else 1
    opp_stone = 1 if black else 2
    is_suicide = [False for _ in range(len(moves))]
    for i in range(len(moves)):
        move = moves[i]
        new_board = board.copy()
        new_board.set(move, black)

        # now the move has been played
        # now we begin to check if it is a suicide

        # assume this move was a suicide
        suicide = True

        # now check the adjacent squares
        adjacent = uf.adjacent(move)
        for a in adjacent:
            if board.get(a) != opp_stone:   # if any of the adjacent square is either free or of same colour
                suicide = False             # it just cant be a suicide
        if not suicide:                     # therfore we
            continue                        # just skip to the next move

        # okay, it looks like a suicide
        # but does it kill any of the opposing units?
        # obviously, if it does, it kills the ones surrounding
        # now all four adjacent ones are opp colour
        # let us dfs them

        for a in adjacent:
            no_of_liberties = 0

            # begin dfs
            # since the goal is to find whether this group dies or not, we will terminate at any point where death is inevitable, i.e. no_of_liberties > 0

            # previously we assumed it wasnt a suicide
            # we are confirming the opposite case now
            # so we consider it to be a suicide
            # therefore the opposing colour doesnt die
            dies = False

            stack = [a]
            visited = [False] * (board_size * board_size)
            while stack:
                p