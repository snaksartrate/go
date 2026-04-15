import numpy as np

import constants as C
from environment import Position
from moves import get_group_stats, adjacent, move_gen, make_a_move

def static_eval(position: Position) -> float:
    """
    Evaluates the static board state.
    Positive score means Black is winning.
    Negative score means White is winning.
    """
    score = 0.0
    board = position.bitboard
    
    # 1. Core Material & Rules
    score += position.black_prisoners
    score -= position.white_prisoners
    score -= C.komi
    
    # 2. Board Traversal for Territory, Influence, and Safety
    visited_stones = set()
    
    black_influence = 0
    white_influence = 0
    
    for i in range(C.board_size * C.board_size):
        val = board.get(i)
        
        # Evaluate Empty Intersections (Territory / Influence)
        if val == 0:
            b_adj = 0
            w_adj = 0
            for a in adjacent(i):
                adj_val = board.get(a)
                if adj_val == 2: b_adj += 1
                elif adj_val == 1: w_adj += 1
            
            # If an empty square borders only black stones, it is black influence
            if b_adj > 0 and w_adj == 0:
                black_influence += 1
            # If an empty square borders only white stones, it is white influence
            elif w_adj > 0 and b_adj == 0:
                white_influence += 1
                
        # Evaluate Black Groups (Safety & Liberties)
        elif val == 2:
            if i not in visited_stones:
                stones, libs = get_group_stats(board, i)
                visited_stones.update(stones)
                
                # Penalty for weak groups
                if len(libs) == 1:
                    score -= 1.5  # In Atari (Severe Danger)
                elif len(libs) == 2:
                    score -= 0.6  # 2 Liberties (Vulnerable)
                
                # Slight reward for thick, strong groups
                score += 0.05 * len(libs)
                
        # Evaluate White Groups (Safety & Liberties)
        elif val == 1:
            if i not in visited_stones:
                stones, libs = get_group_stats(board, i)
                visited_stones.update(stones)
                
                # Penalty for weak groups (inverted for white)
                if len(libs) == 1:
                    score += 1.5  # White in Atari (Good for Black)
                elif len(libs) == 2:
                    score += 0.6  # White is vulnerable
                
                # Slight reward for thick, strong groups
                score -= 0.05 * len(libs)

    # 3. Apply Influence Weights
    # An empty space controlled by a player is worth about 0.5 points of potential
    score += black_influence * 0.5
    score -= white_influence * 0.5
    
    return score

def alpha_beta(position: Position, depth: int, alpha: float, beta: float) -> tuple[float, np.uint16]:
    """
    Minimax search with Alpha-Beta pruning.
    Returns a tuple of (best_evaluation_score, best_move_uint16).
    """
    PASS_MOVE = np.uint16(C.board_size * C.board_size)
    
    # 1. Terminal Node Check: Double Pass
    # If this move and the parent's move were both Passes, the game is over.
    if position.previous_move is not None and (position.previous_move & 0x1FF) == PASS_MOVE:
        if position.parent is not None and position.parent.previous_move is not None:
            if (position.parent.previous_move & 0x1FF) == PASS_MOVE:
                return static_eval(position), PASS_MOVE

    # 2. Base Case: Reached maximum depth
    if depth == 0:
        return static_eval(position), PASS_MOVE

    # 3. Generate and Order Moves
    # We get prioritized legal moves, and append PASS at the very end
    # as it's usually only the best option when no beneficial moves remain.
    candidate_moves = move_gen(position)
    candidate_moves.append(PASS_MOVE)

    best_move = PASS_MOVE

    # 4. Maximizing Player (Black)
    if position.black_to_play:
        max_eval = -float('inf')
        
        for move in candidate_moves:
            next_pos = make_a_move(position, move)
            
            # Recursive call (Black's turn is over, so next is White)
            eval_score, _ = alpha_beta(next_pos, depth - 1, alpha, beta)
            
            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move
                
            # Alpha-Beta Pruning
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break # Beta cutoff: White has a better alternative earlier in the tree
                
        return max_eval, best_move

    # 5. Minimizing Player (White)
    else:
        min_eval = float('inf')
        
        for move in candidate_moves:
            next_pos = make_a_move(position, move)
            
            # Recursive call (White's turn is over, so next is Black)
            eval_score, _ = alpha_beta(next_pos, depth - 1, alpha, beta)
            
            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move
                
            # Alpha-Beta Pruning
            beta = min(beta, eval_score)
            if beta <= alpha:
                break # Alpha cutoff: Black has a better alternative earlier in the tree
                
        return min_eval, best_move


def get_best_move(position: Position, search_depth: int = 3) -> np.uint16:
    """
    Entry point for the engine to find the best move.
    Initializes Alpha-Beta bounds.
    """
    best_score, best_move = alpha_beta(position, search_depth, -float('inf'), float('inf'))
    
    # Optional: If you want to log what the engine thinks the score is, print best_score here
    # print(f"Engine evaluation score: {best_score}")
    
    return best_move

