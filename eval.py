import heapq

from environment import Position, Board, Unit, Move

def alpha_beta(position : Position) -> Move:
    pq = []
