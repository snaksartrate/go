The following response is organized into five parts:
1.  **Core Principle & Framework**: An overview of the evaluation approach.
2.  **Parameter List with Weights**: A detailed table of proposed parameters and their weights.
3.  **Implementation for Key Parameters**: Guidance on implementing the most critical features.
4.  **Implementation Considerations**: Notes on integration with search, speed, and tuning.
5.  **Integration with Your Search**: A quick note on using the evaluation in search.

---

## 1. Core Principle & Framework

The static evaluation function estimates the final score of a position. A common and effective approach is to construct it as a linear combination of weighted terms.

The evaluation can be defined as:
`eval = Σ (weight_i * feature_i)`

For a 9×9 board, the goal is to build a function that is both fast and accurate enough to provide a reliable signal for your alpha-beta search.

---

## 2. Parameter List with Weights

The following table lists a set of parameters, categorized by priority. The weights are a starting point for a 9×9 board and should be tuned based on performance.

| Category | Parameter Name | Description | Suggested Weight | Priority |
| :--- | :--- | :--- | :--- | :--- |
| **Core** | Black Territory | Number of points securely controlled by Black. | +1.0 | High |
| **Core** | White Territory | Number of points securely controlled by White. | -1.0 | High |
| **Core** | Black Prisoners | Number of stones captured by Black. | +1.0 | High |
| **Core** | White Prisoners | Number of stones captured by White. | -1.0 | High |
| **Core** | Komi | Compensation points for White (e.g., 6.5). | -6.5 | Fixed |
| **Strategic** | Black Influence | Points under Black's "sphere of influence" (potential territory). | +0.3 | High |
| **Strategic** | White Influence | Points under White's "sphere of influence". | -0.3 | High |
| **Tactical** | Atari Potential | Bonus for Black for each opponent group in atari, penalty for White. | +0.8 | Medium |
| **Tactical** | Group Safety | Penalty for each of own groups with only 1 eye or in danger. | -1.2 | High |
| **Tactical** | Connection Potential | Bonus for moves that connect own groups or cut opponent groups. | +0.7 | Medium |
| **Shape** | Good Shape Bonus | Bonus for forming good shapes (e.g., one-point jump). | +0.2 | Low |
| **Shape** | Bad Shape Penalty | Penalty for forming bad shapes (e.g., empty triangle). | -0.3 | Low |
| **Endgame** | Sente/Gote | Bonus for moves that keep sente (initiative). | +0.4 | Low |

### Notes on Parameters and Weights
*   **Territory vs. Influence**: "Territory" refers to points that are almost certainly secure. "Influence" refers to potential territory (moyo) that is less certain. Weights reflect this difference in certainty.
*   **Group Safety**: This is a complex but crucial feature. A simple implementation could check if a group has only one eye and no escape route, assigning a large penalty.
*   **Atari Potential**: Your `moves.py` already has a `is_atari_on_opponent` function. This feature is a direct bonus for that.
*   **Connection/Cut**: Also directly supported by your existing `is_connection` and `is_cut` functions.
*   **Weights**: These are initial suggestions. You will likely need to tune them (see Section 4.3).

---

## 3. Implementation for Key Parameters

This section provides guidance on implementing the most critical evaluation components.

### 3.1. Determining Territory

Your `perform_captures` function already removes dead stones. A simple method to estimate territory is:
1.  **Flood-fill from the edges**: Identify empty points connected to the board's edge.
2.  **Assign ownership**: If an empty point is only adjacent to stones of one color, or can only reach the edge by passing through one color's "influence," assign it to that player.
3.  **Count**: Sum the points assigned to each player.

For a 9×9 board, a simplified version of Bouzy's 5/21 algorithm is effective for calculating influence and territory. It works by repeatedly dilating (expanding) and then eroding (contracting) the influence of stones.

### 3.2. Evaluating Group Safety (Life and Death)

This is the hardest part of Go evaluation. A simplified but useful approach:
*   **Two Eyes**: If a group has two distinct, fully-enclosed eyes, it is unconditionally alive.
*   **One Eye**: A group with one eye is alive only if it has sufficient outside liberties or can connect to another living group. Otherwise, it's in danger.
*   **No Eyes**: A group with no eyes is dead unless it can capture surrounding stones to create eyes or connect out.
*   **Seki (Mutual Life)**: You can initially ignore this rare but complex situation.

A penalty can be applied to groups that fail a basic safety check. The weight for this feature (`-1.2`) is high because a group dying is usually catastrophic.

### 3.3. Capturing Stones

This is straightforward. Keep a count of prisoners for each side, as you already do in `environment.py`. Each prisoner is worth 1 point of territory + 1 point for the capture = **2 points** in total value (since it removes an opponent's stone and gives you a point). However, in a linear combination with territory, it's standard to just weight each prisoner as **+1.0** and let the territory count handle the open point.

---

## 4. Implementation Considerations

### 4.1. Integration with Your Search
The evaluation function will be called at the leaf nodes of your search. The search function will then back up the values using the minimax algorithm with alpha-beta pruning.

### 4.2. Speed is Critical
Since this function is called many times during search, it must be fast.
*   **Pre-compute**: Use your `BitBoard` efficiently. Pre-compute adjacency and influence maps where possible.
*   **Incremental Updates**: Instead of recalculating the entire board from scratch for each move, consider updating the evaluation incrementally. This is more complex but significantly faster.
*   **Caching**: Use a transposition table to store evaluations of previously visited positions.

### 4.3. Tuning the Weights
Finding the right weights is an empirical process.
*   **Manual Tuning**: Start with the suggested weights. Play your engine against itself or a simple benchmark. Observe where it makes poor evaluations and adjust weights accordingly.
*   **Automated Tuning**: For more advanced tuning, you could implement a simple genetic algorithm or hill-climbing to optimize the weights against a set of test positions.
*   **Machine Learning**: You could train a linear model on a dataset of 9×9 game positions with known scores. This would yield optimized weights for your features.

---

## 5. Integration with Your Search

The search function will call the evaluation function at leaf nodes and then back up values. Here is a conceptual integration:

```python
def static_eval(position: Position) -> float:
    score = 0.0
    
    # Core Features
    black_territory = estimate_territory(position.bitboard, black=True)
    white_territory = estimate_territory(position.bitboard, black=False)
    score += black_territory - white_territory
    
    score += position.black_prisoners - position.white_prisoners
    
    # Strategic Features
    black_influence = estimate_influence(position.bitboard, black=True)
    white_influence = estimate_influence(position.bitboard, black=False)
    score += 0.3 * (black_influence - white_influence)
    
    # Tactical Features
    for group in get_all_groups(position.bitboard):
        if is_safe(group):
            continue
        if group.color == BLACK:
            score -= 1.2
        else:
            score += 1.2
            
    # ... other features
    
    # Komi
    score -= C.komi  # Komi is a constant (e.g., 6.5)
    
    return score
```
