this readme is outdated

position has data members board, turn, score, parent
children are created on the fly

board is a bitboard
one for black, one for white
it is a list of np.uint8 integers
considering the size of the go board starts from 3\*3 and goes up to 19\*19

moves are also integers
they'll be stored as np.uint16
first 7 MSBs represent priority
7 factors -> true means high priority, false means low priority, arranged in decreasing order of importance
the next 9 bits, the 9 LSBs store move index. it can go from 0 to 361 (worst case), occupying all 9 bits, unsigned way
therefore high priority moves will be sorted by simple int comparisons