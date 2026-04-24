# Go Engine v0.2

A high-performance Go engine implemented in Python, featuring a sophisticated board representation and an optimized search architecture.

## 🚀 Key Features

- **Undo-Based Architecture**: Instead of copying the board for every move, the engine modifies a single `Board` instance forward and backward. This significantly reduces memory allocations and improves search speed.
- **Efficient Group Tracking**: Stones are organized into groups using circular doubly-linked lists. Liberty counts, stone counts, and group heads are updated incrementally.
- **Positional Superko**: Full enforcement of the positional superko rule using 64-bit Zobrist hashes to detect repeated board states.
- **Tactical Ladder Search**: A dedicated, non-recursive mini-search identifies ladder-captured groups, allowing the main search to prune branches and evaluate captures accurately.
- **Benson's Algorithm**: Implements Benson's algorithm to identify "pass-alive" groups—stones that cannot be captured even if the opponent plays an infinite number of moves.
- **Alpha-Beta Search**: Features iterative deepening, transposition tables (TT), and move ordering heuristics for efficient tree exploration.

## 📁 Engine Architecture

The `engine/` directory contains the core logic of the Go engine:

| File | Description |
| :--- | :--- |
| [`board.py`](engine/board.py) | Low-level board state, group management, and Benson's algorithm. |
| [`environment.py`](engine/environment.py) | `Position` wrapper that tracks turn history, prisoners, and superko. |
| [`eval.py`](engine/eval.py) | Search algorithms (Iterative Deepening + Alpha-Beta) and static evaluation. |
| [`moves.py`](engine/moves.py) | Move generation logic and basic legality filtering. |
| [`main.py`](engine/main.py) | CLI entry point for human-vs-engine play and self-play simulations. |
| [`constants.py`](engine/constants.py) | Global configuration (board size, komi, coordinate labels). |
| [`tables.py`](engine/tables.py) | Pre-computed bitboards and lookup tables. |
| [`tt.py`](engine/tt.py) | Transposition Table implementation for caching search results. |
| [`opening.py`](engine/opening.py) | Basic opening book and joseki logic. |
| [`utility_functions.py`](engine/utility_functions.py) | General-purpose helper functions for coordinate conversion and math. |

## 🕹️ Getting Started

### Prerequisites
- Python 3.10+
- NumPy

### Running the Engine
Launch the interactive CLI to play against the engine or watch it play itself:

```bash
python engine/main.py
```

### Command Line Options
- `--self-play`: Run an engine-vs-engine game.
- `--play-black`: Start a game where you play Black.
- `--play-white`: Start a game where you play White.
- `--depth=N`: Set the search depth (default: 5).

## 🛠️ Implementation Details

### Board Representation
The board is stored as a 1D NumPy array with a "wall" border. This eliminates the need for boundary checks inside tight loops.

### Incremental Updates
Every move update (`add_unsafe`) and removal (`remove_unsafe`) incrementally adjusts:
1. **Liberties**: Borne by the group's head stone.
2. **Stone Count**: Number of stones in the chain.
3. **Zobrist Hash**: XORing bitstrings for every added/removed stone.

### Life & Death
Scoring is determined using Area Scoring. The engine identifies alive stones through Benson's Algorithm, which iteratively eliminates groups that don't satisfy the two-eye requirement.