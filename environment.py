import numpy as np
from functools import total_ordering

import constants as C
import utility_functions as uf

board_size = C.board_size
encode_map = C.ENCODE_MAP
decode_map = C.DECODE_MAP

class BitBoard:
    def __init__(self):
        self.black = np.zeros(board_size * board_size // 8 + 1, dtype=np.uint8) # doing mod 8 gives (4 * (k^2 + k) + 1) mod 8 which is (4 * even + 1) mod 8 = 1,
        self.white = np.zeros(board_size * board_size // 8 + 1, dtype=np.uint8) # so just waste 7 bits, that's fine

    def get(self, index : int) -> int:
        bit_row = index // 8
        bit_col = index % 8
        if (self.black[bit_row] >> bit_col) & np.uint8(1):
            return 2
        if (self.white[bit_row] >> bit_col) & np.uint8(1):
            return 1
        return 0
    
    def set(self, index : int, black : bool):
        bit_row = index // 8
        bit_col = index % 8
        if ((self.black[bit_row] >> bit_col) or (self.white[bit_row] >> bit_col)) & 1: # p and r or q and r simplifies to (p or q) and r
            raise ValueError("position already occupied")
        if black:
            self.black[bit_row] |= 1 << bit_col
        else:
            self.white[bit_row] |= 1 << bit_col

    # def get_rc(self, row : int, col : int) -> int:
    #     return self.get(row * board_size + col)
    
    # def set_rc(self, row : int, col : int, black : bool):
    #     self.set(row * board_size + col, black)

    # def display(self):
    #     symbols = ('.', 'W', 'B')
    #     for r in range(board_size):
    #         row = []
    #         for c in range(board_size):
    #             row.append(symbols[self.get(r, c)])
    #         print(' '.join(row))

@total_ordering
class Move:
    def __init__(self, index : int, captures_opponent : bool | None = None, puts_opponent_in_atari : bool | None = None, saves_me_from_atari : bool | None = None, cuts_opponents_groups : bool | None = None, connects_my_groups : bool | None = None, increases_my_liberties : bool | None = None, is_not_self_atari : bool | None = None):
        self.val = np.uint16(index)
        if captures_opponent:
            self.val |= 1 << 15
        if puts_opponent_in_atari:
            self.val |= 1 << 14
        if saves_me_from_atari:
            self.val |= 1 << 13
        if cuts_opponents_groups:
            self.val |= 1 << 12
        if connects_my_groups:
            self.val |= 1 << 11
        if increases_my_liberties:
            self.val |= 1 << 10
        if is_not_self_atari:
            self.val |= 1 << 9
    
    def __eq__(self, other):
        return (self.val >> 9) == (other.val >> 9)

    def __lt__(self, other):
        return (self.val >> 9) < (other.val >> 9)
    
    def __repr__(self):
        priority = int(self.val >> 9)
        index = int(self.val & 0x1FF) # yes this line is AI, I was making a lot of bugs, finally understood it :p
        return f"priority = {priority}, index = {index}"
    
    def captures_opponent(self, b : bool):
        if b:
            self.val |= 1 << 15

    def puts_opponent_in_atari(self, b : bool):
        if b:
            self.val |= 1 << 14

    def saves_me_from_atari(self, b : bool):
        if b:
            self.val |= 1 << 13

    def cuts_opponents_groups(self, b : bool):
        if b:
            self.val |= 1 << 12

    def connects_my_groups(self, b : bool):
        if b:
            self.val |= 1 << 11

    def increases_my_liberties(self, b : bool):
        if b:
            self.val |= 1 << 10

    def is_not_self_atari(self, b : bool):
        if b:
            self.val |= 1 << 9
    
class Position:
    def __init__(self):
        self.bitboard = BitBoard()
        self.black_to_play = True
        self.parent = id[Position]
        self.previous_move = Move

# import sys
# print(sys.getsizeof(BitBoard()))
# print(sys.getsizeof(0))
# print(sys.getsizeof(1))
# print(sys.getsizeof(2))
# print(sys.getsizeof('.'))
# print(sys.getsizeof('w'))
# print(sys.getsizeof('b'))

