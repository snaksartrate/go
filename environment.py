import numpy as np

from constants import board_size

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
    
    def empty(self, index : int):
        bit_row = index // 8
        bit_col = index % 8
        self.black[bit_row] &= ~(1 << bit_col)

    # def get_rc(self, row : int, col : int) -> int:
    #     return self.get(row * board_size + col)
    
    # def set_rc(self, row : int, col : int, black : bool):
    #     self.set(row * board_size + col, black)

    # def empty_rc(self, row : int, col : int):
    #     self.empty(row * board_size + col)

    def copy(self):
        new_board = BitBoard()
        for i in range(board_size * board_size):
            if self.get(i):
                new_board.set(i, self.get(i) - 1)
        return new_board

    # def display(self):
    #     symbols = ('.', 'W', 'B')
    #     for r in range(board_size):
    #         row = []
    #         for c in range(board_size):
    #             row.append(symbols[self.get(r, c)])
    #         print(' '.join(row))

class Position:
    def __init__(self, board : BitBoard, black_to_play : bool, prev, move : np.uint16):
        self.bitboard = board if board is not None else BitBoard()
        self.black_to_play = black_to_play
        self.parent = prev
        self.previous_move = move

# import sys
# print(sys.getsizeof(BitBoard()))
# print(sys.getsizeof(0))
# print(sys.getsizeof(1))
# print(sys.getsizeof(2))
# print(sys.getsizeof('.'))
# print(sys.getsizeof('w'))
# print(sys.getsizeof('b'))

