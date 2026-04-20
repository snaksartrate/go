# Go Engine Optimization Report
## Target: Depths 10 → 16 → 20 on 9×9

> **Feed this document to VS Code Copilot.**  
> Each section names the file, the exact problem, and the exact fix to implement.  
> Sections are ordered by expected speedup (highest first).

---



---

## ⚠️ URGENT BUG — Ko Rule Violation Causes Infinite Search Cycles (`environment.py`)

> **Fix this first, before any other optimization.**  
> This bug causes the engine to search at depths of 200+ by allowing illegal position cycles.

### Root Cause

In `environment.py`, `Position.push()` saves a `saved` tuple that is restored by `pop()`.
The tuple correctly saves `black_to_play`, prisoners, and `pass_count` — but it **does not save
`board.simple_ko_point`**.

`board.playUnsafe(PASS)` always sets `simple_ko_point = None`:

```python
# board.py — playUnsafe
def playUnsafe(self, pla, loc):
    if loc == Board.PASS_LOC:
        self.simple_ko_point = None   # ← always destroyed
        self.pla = Board.get_opp(pla)
```

For **non-pass** moves, `board.undo(record)` correctly restores `simple_ko_point` from the undo
record. But for **pass** moves, `record = None` and `board.undo` is never called. `pop()` falls
into the `else` branch, which only restores `board.pla` — **the ko restriction is silently lost**.

### Effect

Every time the search tries a pass move (null-move pruning or as a candidate) and then undoes it,
`simple_ko_point` is left as `None`. The engine then sees the ko capture as a legal move, plays
it, and the position cycles back — which the engine sees as a legal move, plays it, cycles back
again — creating a loop that runs until the search depth limit is hit. Because there is no
superko detection in the search (by design), this depth can reach 200+.

### The Fix (2 lines in `environment.py`)

**In `push()`**, add `self.board.simple_ko_point` to the saved tuple:

```python
# BEFORE
saved = (
    self.black_to_play,
    self.black_prisoners,
    self.white_prisoners,
    self.pass_count,
)

# AFTER
saved = (
    self.black_to_play,
    self.black_prisoners,
    self.white_prisoners,
    self.pass_count,
    self.board.simple_ko_point,   # ← ADD THIS
)
```

**In `pop()`**, unpack and restore it in the pass branch:

```python
# BEFORE
(
    self.black_to_play,
    self.black_prisoners,
    self.white_prisoners,
    self.pass_count,
) = saved

if record is not None:
    self.board.undo(record)
else:
    self.board.pla = self.current_player
    # simple_ko_point was NOT restored here — BUG

# AFTER
(
    self.black_to_play,
    self.black_prisoners,
    self.white_prisoners,
    self.pass_count,
    saved_ko_point,               # ← ADD THIS
) = saved

if record is not None:
    self.board.undo(record)       # undo() already restores ko from record
else:
    self.board.pla = self.current_player
    self.board.simple_ko_point = saved_ko_point   # ← ADD THIS
```

The fixed `environment.py` is included alongside this report.

## 0. Summary of Bottlenecks

| Priority | File | Issue | Expected Gain |
|---|---|---|---|
| 🚨 BUG | `environment.py` | Ko restriction lost on every pass undo — creates 200-ply cycles | Correctness |
| 🔴 CRITICAL | `eval.py` | No transposition table | 10–100× at depth 10+ |
| 🔴 CRITICAL | `eval.py` | `static_eval` called at every leaf — O(n²) flood-fill + influence map | 3–5× |
| 🔴 CRITICAL | `eval.py` | No PVS / zero-window search | 2–3× |
| 🟠 HIGH | `eval.py` | No LMR (Late Move Reductions) | 2–4× at depth 12+ |
| 🟠 HIGH | `eval.py` | `_has_group_in_atari` does full board scan every node | 1.5–2× |
| 🟠 HIGH | `eval.py` | History table wiped between iterative-deepening iterations | 20–30% |
| 🟡 MEDIUM | `eval.py` | No futility pruning near leaves | 1.3–1.5× |
| 🟡 MEDIUM | `eval.py` | No quiescence search for captures | Quality + speed |
| 🟡 MEDIUM | `moves.py` | Move scoring doesn't use history for ordering | 10–20% |
| 🟡 MEDIUM | `eval.py` | Aspiration window too narrow (±1.5) — causes excess re-searches | 10–15% |
| 🟢 LOW | `eval.py` | History table indexing bug (wrong size formula) | minor |
| 🟢 LOW | `environment.py` | `push` copies `num_captures_made` dict on every move | minor |

---

## 1. 🔴 CRITICAL — Transposition Table (`eval.py`)

### Problem
There is **no transposition table (TT)**. In a 9×9 game tree, the same board position is visited
thousands of times at different paths. Without a TT, every redundant subtree is fully re-searched.
This is the single biggest reason depth 10+ is intractable.

### Fix: Add a Zobrist-keyed TT in `eval.py`

Create a new module `tt.py` (or add to `eval.py`) with the following structure:

```python
# tt.py  — Transposition Table

TT_SIZE = 1 << 22          # 4 M entries; tune based on RAM (each entry ~40 bytes → ~160 MB)
TT_MASK = TT_SIZE - 1

TT_EXACT = 0
TT_LOWER = 1               # alpha (fail-low)
TT_UPPER = 2               # beta  (fail-high / cut-node)

# Each slot: [zobrist_key, score, flag, depth, best_move]
# Use a flat list of lists for cache locality.
_tt = [None] * TT_SIZE

def tt_clear():
    global _tt
    _tt = [None] * TT_SIZE

def tt_probe(zobrist: int, depth: int, alpha: float, beta: float):
    """
    Returns (score, best_move) if TT hit with sufficient depth, else (None, None).
    """
    slot = _tt[zobrist & TT_MASK]
    if slot is None or slot[0] != zobrist:
        return None, None
    tt_depth, tt_score, tt_flag, tt_move = slot[1], slot[2], slot[3], slot[4]
    if tt_depth >= depth:
        if tt_flag == TT_EXACT:
            return tt_score, tt_move
        if tt_flag == TT_LOWER and tt_score >= beta:
            return tt_score, tt_move
        if tt_flag == TT_UPPER and tt_score <= alpha:
            return tt_score, tt_move
    # Return best move for move ordering even if score is not usable
    return None, tt_move

def tt_store(zobrist: int, depth: int, score: float, flag: int, best_move: int):
    idx = zobrist & TT_MASK
    existing = _tt[idx]
    # Replacement strategy: always replace if depth >=, otherwise keep deeper
    if existing is None or depth >= existing[1]:
        _tt[idx] = (zobrist, depth, score, flag, best_move)
```

### Integrate in `negamax()` in `eval.py`

At the **top** of `negamax()`, before move generation, add:

```python
from tt import tt_probe, tt_store, tt_clear, TT_EXACT, TT_LOWER, TT_UPPER

def negamax(position, depth, alpha, beta, max_depth):
    board = position.board
    original_alpha = alpha

    # --- TT probe ---
    zobrist = board.sit_zobrist()           # includes player-to-move
    tt_score, tt_move = tt_probe(zobrist, depth, alpha, beta)
    if tt_score is not None:
        return tt_score, tt_move
    # tt_move may still be non-None (best move hint) — use it for ordering below

    # ... rest of function ...

    # --- TT store (at end, before return) ---
    if best_score <= original_alpha:
        flag = TT_UPPER
    elif best_score >= beta:
        flag = TT_LOWER
    else:
        flag = TT_EXACT
    tt_store(zobrist, depth, best_score, flag, best_move)

    return best_score, best_move
```

**Move ordering integration**: When `tt_move` is not None, try it FIRST before killers and generated moves:

```python
# In the move loop, prepend tt_move if it's legal and not already in candidates
if tt_move is not None and tt_move not in killer_set:
    if board.would_be_legal(pla, tt_move):
        candidate_moves.insert(0, tt_move)
```

**Call `tt_clear()` at the start of `get_best_move()`**, not between iterative deepening iterations
(the TT should persist across iterations — that's how ID benefits from it).

---

## 2. 🔴 CRITICAL — Cheap Static Eval (`eval.py`)

### Problem
`static_eval()` is called at **every leaf node** and runs three expensive passes:
1. **BFS flood-fill** over all empty regions — O(board_area) with `visited` list allocation.
2. **Group walk** for eye counting — walks every stone's linked-list.
3. **Influence map** — O(stones × 49) inner loop, uses a dict for accumulation.

At depth 10 on 9×9, there are potentially millions of leaf evaluations. This is the second-largest
bottleneck after the missing TT.

### Fix A: Split eval into "cheap" and "full"

```python
def static_eval_cheap(position: Position) -> float:
    """
    O(groups) eval: prisoners + komi + liberty-based group scores only.
    No flood-fill, no influence map.
    Used at leaves during search.
    """
    board = position.board
    score = position.black_prisoners - position.white_prisoners - komi

    visited_heads = set()
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            val = board.board[loc]
            if val != Board.BLACK and val != Board.WHITE:
                continue
            head = board.group_head[loc]
            if head in visited_heads:
                continue
            visited_heads.add(head)

            sign = 1.0 if val == Board.BLACK else -1.0
            stone_count = board.group_stone_count[head]
            lib_count   = board.group_liberty_count[head]

            # Atari penalty
            if lib_count == 1:
                score -= sign * 4.0 * stone_count
            elif lib_count == 2:
                score -= sign * 0.5 * stone_count
            else:
                score += sign * (0.1 * lib_count + 0.3) * stone_count

    return score
```

```python
def _eval_for_current_player(position: Position) -> float:
    raw = static_eval_cheap(position)   # ← use cheap version in search
    return raw if position.black_to_play else -raw
```

Keep the full `static_eval()` for display in `main.py` (it's only called once per move there).

### Fix B: Precompute influence weights

Replace the inner influence dict with a **precomputed lookup table** in `tables.py`:

```python
# In tables.py — run once at import time
INF_WEIGHTS = {}    # (dx, dy) -> weight  for manhattan dist 1..3
for dy in range(-3, 4):
    for dx in range(-3, 4):
        d = abs(dx) + abs(dy)
        if 1 <= d <= 3:
            INF_WEIGHTS[(dx, dy)] = 1.0 / (1.0 + d)
```

Then in the full `static_eval`, replace the dict accumulation with a plain float array indexed by loc.

---

## 3. 🔴 CRITICAL — Principal Variation Search (PVS) (`eval.py`)

### Problem
Current code uses a plain negamax loop where every move is searched with the full `[alpha, beta]`
window. PVS searches the first (best) move with the full window and all subsequent moves with a
**zero-width window** (-alpha-1, -alpha). If any subsequent move fails high, it re-searches with
the full window. This cuts ~40–60% of nodes at deeper depths because most moves are expected to
fail low.

### Fix: Replace the move loop in `negamax()` with PVS

```python
is_first_move = True
for move in candidate_moves:
    position.push(move)

    if is_first_move:
        score, _ = negamax(position, depth - 1, -beta, -alpha, max_depth)
        score = -score
        is_first_move = False
    else:
        # Zero-window search
        score, _ = negamax(position, depth - 1, -alpha - 1, -alpha, max_depth)
        score = -score
        if alpha < score < beta:
            # Re-search with full window (move is better than expected)
            score, _ = negamax(position, depth - 1, -beta, -score, max_depth)
            score = -score

    position.pop()

    if score > best_score:
        best_score = score
        best_move = move
    if score > alpha:
        alpha = score
    if alpha >= beta:
        if move != Board.PASS_LOC:
            _update_killers(current_depth_idx, move)
            _update_history(pla, move, depth)
        break
```

---

## 4. 🟠 HIGH — Late Move Reductions (LMR) (`eval.py`)

### Problem
No LMR. Late moves in a sorted list are very unlikely to be good. Searching them at full depth
is wasteful. LMR reduces depth for moves that are: (a) not captures, (b) not killers, (c) come
after the first few moves at depth ≥ 3.

### Fix: Add LMR inside the PVS move loop

```python
LMR_MIN_DEPTH = 3
LMR_MIN_MOVE_IDX = 3           # start reducing after 3rd move
LMR_REDUCTION_TABLE = {}       # (depth, move_idx) -> reduction

def _lmr_reduction(depth: int, move_idx: int) -> int:
    """Standard LMR formula: floor(0.75 + ln(depth) * ln(move_idx) / 2.25)"""
    import math
    if depth < LMR_MIN_DEPTH or move_idx < LMR_MIN_MOVE_IDX:
        return 0
    r = int(0.75 + math.log(depth) * math.log(move_idx) / 2.25)
    return max(0, min(r, depth - 1))
```

Inside the PVS loop, for non-first, non-killer, non-capture moves:

```python
for move_idx, move in enumerate(candidate_moves):
    is_capture = move != Board.PASS_LOC and _is_capture_move(board, pla, move)
    is_killer  = move in killer_set
    reduction  = 0 if (is_first_move or is_capture or is_killer) else _lmr_reduction(depth, move_idx)

    position.push(move)

    if is_first_move:
        score, _ = negamax(position, depth - 1, -beta, -alpha, max_depth)
        score = -score
        is_first_move = False
    else:
        # Try with reduction
        score, _ = negamax(position, depth - 1 - reduction, -alpha - 1, -alpha, max_depth)
        score = -score
        # Re-search if promising (LMR or zero-window failed)
        if score > alpha and (reduction > 0 or score < beta):
            score, _ = negamax(position, depth - 1, -beta, -alpha, max_depth)
            score = -score

    position.pop()
    # ... update best, alpha, beta cutoff ...
```

Add a helper:

```python
def _is_capture_move(board: Board, pla: int, loc: int) -> bool:
    """True if this move captures at least one enemy stone (O(4))."""
    opp = Board.get_opp(pla)
    for dloc in board.adj:
        adj = loc + dloc
        if board.board[adj] == opp and board.group_liberty_count[board.group_head[adj]] == 1:
            return True
    return False
```

---

## 5. 🟠 HIGH — Fix `_has_group_in_atari` full-board scan (`eval.py`)

### Problem
`_has_group_in_atari(board, pla)` is called at **every internal node** to guard null-move pruning.
It scans all 81 squares × set lookup. This is O(board_area) every call.

### Fix: Track atari count incrementally in `Position`

Add a field `atari_count: dict` to `Position.__slots__` in `environment.py`:

```python
__slots__ = (
    'board', 'black_to_play', 'black_prisoners', 'white_prisoners',
    'move_history', 'pass_count', 'atari_count',   # ← add this
)
```

In `__init__`:
```python
self.atari_count = {Board.BLACK: 0, Board.WHITE: 0}
```

In `push()`, after the move is played, scan only the 4 adjacent groups that could have changed:

```python
# Recompute atari counts from scratch only for affected groups (O(4) not O(81))
# Simplest correct approach: just re-scan all groups once after push.
# This is still O(groups), not O(board_area).
self.atari_count = _count_atari_groups(self.board)
```

In `saved` tuple, add `self.atari_count.copy()` and restore in `pop()`.

Then in `negamax`:

```python
# Fast O(1) atari check
if (depth > 2 and
        position.pass_count == 0 and
        position.atari_count[pla] == 0):
    # ... null move ...
```

Helper (called only in `push`, not every node):

```python
def _count_atari_groups(board: Board) -> dict:
    counts = {Board.BLACK: 0, Board.WHITE: 0}
    seen = set()
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            val = board.board[loc]
            if val == Board.BLACK or val == Board.WHITE:
                head = board.group_head[loc]
                if head not in seen:
                    seen.add(head)
                    if board.group_liberty_count[head] == 1:
                        counts[val] += 1
    return counts
```

---

## 6. 🟠 HIGH — Persist History Table Across Iterative Deepening (`eval.py`)

### Problem
`_init_search_tables(max_depth)` is called once at the start of `get_best_move()`, which wipes
both the killer table and the **history table**. This is correct for killers (they are
depth-relative) but **wrong for history**. History should accumulate across all iterations of
iterative deepening — that's one of its main benefits.

### Fix

Split initialization:

```python
def _init_killers(max_depth: int):
    global _killers
    _killers = [[None, None] for _ in range(max_depth + 1)]

def _init_history():
    global _history
    arrsize = Board(board_size).arrsize
    _history = {
        Board.BLACK: [0] * arrsize,
        Board.WHITE: [0] * arrsize,
    }

def _age_history():
    """Age (halve) history scores between iterations instead of zeroing."""
    for pla in (Board.BLACK, Board.WHITE):
        h = _history[pla]
        for i in range(len(h)):
            h[i] >>= 1       # integer right-shift: divide by 2
```

In `get_best_move()`:

```python
def get_best_move(position: Position, search_depth: int = 5) -> int:
    _init_history()             # once per root search
    tt_clear()                  # or keep TT across root calls (even better)
    best_move = Board.PASS_LOC
    prev_score = 0.0

    for depth in range(1, search_depth + 1):
        _init_killers(depth)    # fresh killers per depth iteration
        _age_history()          # age, don't zero
        # ... aspiration window + negamax call ...
```

Also fix the **history table size bug**:

```python
# BUG (current):
_history = {
    Board.BLACK: [0] * (board_size + 2) * (board_size + 1) * 2,
    ...
}
# This evaluates as a single integer product, not a constructor call!
# (board_size + 2) * (board_size + 1) * 2  with board_size=9 → 220
# But board.arrsize = (9+1)*(9+2)+1 = 111, so locs are in [0..110].
# 220 >= 111 so it doesn't crash, but it's accident-dependent.

# FIX:
arrsize = (board_size + 1) * (board_size + 2) + 1
_history = {
    Board.BLACK: [0] * arrsize,
    Board.WHITE: [0] * arrsize,
}
```

---

## 7. 🟡 MEDIUM — Futility Pruning (`eval.py`)

### Problem
No futility pruning. At depth 1 (one ply from a leaf), if the static eval is so far below alpha
that no single move can raise it, we can skip that node entirely.

### Fix: Add futility pruning in `negamax`

```python
FUTILITY_MARGIN = [0, 2.0, 4.0, 6.0]   # indexed by depth (0..3)

def negamax(position, depth, alpha, beta, max_depth):
    # ... TT probe, terminal checks ...

    # Futility pruning: only at depth 1..3, not in check (no atari on pla)
    if (1 <= depth <= 3 and
            abs(alpha) < 500 and          # not a mate score
            position.atari_count.get(pla, 1) == 0):
        static = static_eval_cheap(position)
        if (static + FUTILITY_MARGIN[depth]) <= alpha if position.black_to_play else \
           (-static + FUTILITY_MARGIN[depth]) <= alpha:
            return alpha, Board.PASS_LOC
```

---

## 8. 🟡 MEDIUM — Quiescence Search (`eval.py`)

### Problem
At depth 0, positions with pending captures are evaluated as if they're stable. This causes
"horizon effect" errors — the engine misses tactics that resolve one ply beyond the horizon.

### Fix: Add a `quiescence()` function

```python
def quiescence(position: Position, alpha: float, beta: float, qdepth: int = 4) -> float:
    """
    Search only capture moves until quiet, then eval.
    qdepth limits the recursion to avoid blowup.
    """
    stand_pat = _eval_for_current_player(position)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat
    if qdepth <= 0:
        return alpha

    board = position.board
    pla = position.current_player

    # Generate only capture moves (O(81) but filtered tightly)
    for y in range(board.y_size):
        for x in range(board.x_size):
            loc = board.loc(x, y)
            if board.board[loc] != Board.EMPTY:
                continue
            if not _is_capture_move(board, pla, loc):
                continue
            if board.would_be_single_stone_suicide(pla, loc):
                continue
            if loc == board.simple_ko_point:
                continue

            position.push(loc)
            score = -quiescence(position, -beta, -alpha, qdepth - 1)
            position.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

    return alpha
```

In `negamax`, replace the leaf call:

```python
if depth <= 0:
    return quiescence(position, alpha, beta), Board.PASS_LOC
```

---

## 9. 🟡 MEDIUM — History-Based Move Ordering (`moves.py`)

### Problem
`move_gen` sorts by a static tactical score. The history heuristic is computed in `eval.py` but
**never fed back into move ordering** in `moves.py`.

### Fix: Pass history table to `move_gen`

Change signature:

```python
def move_gen(position: Position, killers: list | None = None,
             history: dict | None = None) -> list[int]:
```

In the scoring line:

```python
hist_bonus = 0
if history is not None:
    hist_bonus = history[pla][loc] if loc < len(history[pla]) else 0

scored_moves.append((sc + hist_bonus, loc))
```

In `negamax`, pass history:

```python
from eval import _history   # module-level

candidate_moves = move_gen(position, killers=killers_for_depth, history=_history)
```

---

## 10. 🟡 MEDIUM — Widen Aspiration Window (`eval.py`)

### Problem
The aspiration window of ±1.5 is extremely tight for a Go evaluation whose range is ±50+.
A single good move can shift the score by 5+ points, causing frequent re-searches with the full
window (two full-depth re-searches instead of one).

### Fix: Use a widening retry loop

```python
def get_best_move(position: Position, search_depth: int = 5) -> int:
    _init_history()
    best_move = Board.PASS_LOC
    prev_score = 0.0

    for depth in range(1, search_depth + 1):
        _init_killers(depth)
        _age_history()

        if depth <= 2:
            score, move = negamax(position, depth, -_INF, _INF, max_depth=depth)
        else:
            # Widening aspiration windows
            delta = 3.0
            alpha = prev_score - delta
            beta  = prev_score + delta
            while True:
                score, move = negamax(position, depth, alpha, beta, max_depth=depth)
                if score <= alpha:
                    alpha -= delta * 2
                    delta *= 2
                elif score >= beta:
                    beta  += delta * 2
                    delta *= 2
                else:
                    break   # score inside window

        prev_score = score
        best_move  = move

    return best_move
```

---

## 11. 🟢 LOW — Move Count Based Pruning (MCBP) (`eval.py`)

For very late moves (move_idx > 8 at depth ≤ 2), prune directly without searching:

```python
MAX_MOVES_AT_DEPTH = {1: 6, 2: 12, 3: 20}   # tune empirically

if depth in MAX_MOVES_AT_DEPTH and move_idx >= MAX_MOVES_AT_DEPTH[depth]:
    if not is_capture and not is_killer:
        continue   # skip this move entirely
```

---

## 12. 🟢 LOW — Opening Book (`eval.py` / new `opening.py`)

The **very first few moves** of a 9×9 game are the most expensive (full board, no pruning, high
branching factor). An opening book eliminates the search cost entirely for the first 3–5 plies.

### Fix: Add a minimal opening book

```python
# opening.py
from board import Board

# Key: frozenset of (pla, loc) stones on board
# Value: recommended move loc
# Populate with known-good 9×9 openings (or generate via self-play)

_TENGEN = Board.loc_static(4, 4, 9)   # center

OPENING_BOOK = {
    # Empty board: play tengen
    frozenset(): _TENGEN,
    # After tengen, play 3-3
    frozenset([(Board.BLACK, _TENGEN)]): Board.loc_static(2, 2, 9),
}

def book_lookup(board) -> int | None:
    stones = frozenset(
        (board.board[board.loc(x, y)], board.loc(x, y))
        for y in range(board.y_size)
        for x in range(board.x_size)
        if board.board[board.loc(x, y)] in (Board.BLACK, Board.WHITE)
    )
    return OPENING_BOOK.get(stones)
```

In `get_best_move`:

```python
from opening import book_lookup

def get_best_move(position, search_depth=5):
    book_move = book_lookup(position.board)
    if book_move is not None:
        return book_move
    # ... rest of search ...
```

---

## 13. Implementation Order (Recommended)

Do these in order. Each step independently measurable with a self-play timer.

```
Step 1:  Transposition table (tt.py)                    → biggest gain, required for depth 10+
Step 2:  static_eval_cheap() replacing leaf eval         → 3–5× leaf speed
Step 3:  PVS zero-window search                          → 2–3× tree reduction
Step 4:  Fix history persistence + size bug              → 20–30% ordering improvement
Step 5:  LMR                                             → 2–4× at depth 12+
Step 6:  Atari count in Position + fast null-move guard  → avoids full board scan
Step 7:  Futility pruning                                → 20–30% near leaves
Step 8:  Quiescence search                               → quality improvement + prunes horizon
Step 9:  History-guided move_gen                         → better ordering, more cutoffs
Step 10: Wider aspiration windows                        → fewer re-searches
Step 11: Opening book                                    → eliminates search for move 1–3
Step 12: MCBP                                            → fine-tuning
```

---

## 14. Files to Create / Modify

| File | Action |
|---|---|
| `tt.py` | **Create** — transposition table module |
| `eval.py` | **Modify** — TT probe/store, PVS, LMR, futility, quiescence, history fix, cheap eval |
| `moves.py` | **Modify** — accept and apply `history` dict in scoring |
| `environment.py` | **Modify** — add `atari_count` to Position, maintain in push/pop |
| `opening.py` | **Create** — opening book |
| `tables.py` | **Modify** — add `INF_WEIGHTS` precomputed table |

---

## 15. Quick Benchmark Harness

Add to `main.py` or a new `bench.py`:

```python
import time
from environment import Position
from eval import get_best_move

def benchmark(depth: int, num_moves: int = 3):
    pos = Position()
    for d in [depth]:
        start = time.perf_counter()
        for _ in range(num_moves):
            move = get_best_move(pos, search_depth=d)
            pos.push(move)
        elapsed = time.perf_counter() - start
        print(f"depth={d}  {num_moves} moves  {elapsed:.2f}s  ({elapsed/num_moves:.2f}s/move)")

if __name__ == "__main__":
    for d in [5, 7, 10, 12]:
        benchmark(d)
```

Run before and after each step to confirm improvement.

---

## 16. Expected Depth Capability After Each Milestone

| After steps | Expected max depth (< 5s/move) |
|---|---|
| Baseline (now) | ~6–7 |
| Steps 1–2 (TT + cheap eval) | ~10–12 |
| Steps 1–4 (+ PVS + history fix) | ~13–15 |
| Steps 1–7 (+ LMR + futility) | ~16–18 |
| Steps 1–11 (all) | **18–22** |
