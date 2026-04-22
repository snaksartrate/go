# environment.py — Game state wrapper around KataGo's Board
#
# KEY DESIGN IDEA: There is only ONE Board object for the entire search.
# Instead of creating a new copy of the board for every move (expensive),
# the engine modifies the same board forward with push() and rewinds it
# backward with pop(). This "undo-based" approach is much faster.
#
# Position is a MUTABLE CURSOR, not a snapshot. There is ONE Board instance
# for the entire search tree. The search mutates it forward with push() and
# backward with pop(). All bookkeeping (turn, prisoners, pass count, superko
# history) lives inside push/pop so the search never scatters state updates.
#
# Superko rule: In Go, a position may not be repeated. This is tracked by
# storing a Zobrist hash (a compact fingerprint) of every board position that
# has appeared. If a move would recreate an already-seen position, it is illegal.
# ko_history tracks every board position (pos_zobrist hash) that has
# occurred in the game or the current search line. A non-pass move whose
# resulting position is already in ko_history is a superko violation.

from board import Board
from constants import board_size


def _count_atari_groups(board: Board) -> dict:
    """Count groups in atari (exactly 1 liberty) for each player.
    
    Returns dict[Board.BLACK] = count, dict[Board.WHITE] = count.
    """
    # We walk every intersection on the board. When we encounter a stone,
    # we look up its group's head. We use 'seen' to avoid counting the same
    # group twice (multiple stones share the same head).
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
                    # A group with exactly 1 liberty is "in atari" — one move away from capture.
                    if board.group_liberty_count[head] == 1:
                        counts[val] += 1
    return counts


class Position:
    """Thin mutable wrapper around a KataGo Board.

    Architecture:
        - self.board is a SHARED, MUTABLE Board instance.
        - push(pla, loc) plays a move and saves an undo record.
        - pop() undoes the last move and restores all state.
        - move_history is a stack of (loc, record, old_state) tuples.
    """

    # __slots__ tells Python exactly which attributes this class has.
    # This saves memory and makes attribute access slightly faster.
    __slots__ = (
        'board',
        'black_to_play',
        'black_prisoners',
        'white_prisoners',
        'move_history',
        'pass_count',
        'atari_count',   # Track how many groups are in atari for each player
        'ko_history',    # set of pos_zobrist hashes for positional superko
    )

    def __init__(self, board: Board = None, black_to_play: bool = True):
        # If no board is provided, start a fresh empty 9×9 board.
        self.board = board if board is not None else Board(board_size)
        self.black_to_play = black_to_play
        self.black_prisoners = 0  # stones Black has captured
        self.white_prisoners = 0  # stones White has captured
        self.move_history = []    # stack of (loc, record, saved, ko_hash_added)
        self.pass_count = 0       # consecutive passes (for game-end detection)
        self.atari_count = {Board.BLACK: 0, Board.WHITE: 0}  # groups in atari
        self.ko_history = set()   # positional superko history
        # Add the starting (empty) board position to the history so no move can recreate it.
        self.ko_history.add(self.board.pos_zobrist())  # initial empty board

    @property
    def current_player(self) -> int:
        """Return Board.BLACK or Board.WHITE for the side to move."""
        return Board.BLACK if self.black_to_play else Board.WHITE

    @property
    def opponent(self) -> int:
        """Return Board.BLACK or Board.WHITE for the side NOT to move."""
        return Board.WHITE if self.black_to_play else Board.BLACK

    def push(self, loc: int) -> None:
        """Play a move and push an undo record onto the history stack.

        Args:
            loc: Board location (use Board.PASS_LOC for pass,
                 or board.loc(x, y) for a board intersection).

        Updates black_to_play, prisoners, pass_count, atari_count, and
        ko_history (superko tracking).

        After calling push(), use is_superko_repeat() to check whether the
        move created a repeated board position (positional superko violation).
        """
        pla = self.current_player

        # Save state that needs to be restored on pop.
        # simple_ko_point MUST be saved here: board.playUnsafe(PASS) sets it
        # to None, and pass moves have no undo record to restore it from.
        # Without this, every undone pass silently destroys the ko restriction,
        # allowing illegal ko recaptures and creating search cycles 100+ deep.
        saved = (
            self.black_to_play,
            self.black_prisoners,
            self.white_prisoners,
            self.pass_count,
            self.board.simple_ko_point,   # ← ko fix
            self.atari_count.copy(),       # ← atari count fix
        )

        if loc == Board.PASS_LOC:
            # Pass: no board mutation, just toggle turn and bump pass count.
            # Two consecutive passes ends the game in Go.
            self.board.playUnsafe(pla, Board.PASS_LOC)
            record = None
            self.pass_count += 1
            ko_hash_added = None  # passes are exempt from superko
        else:
            # Non-pass: play the stone on the board and get back an undo record.
            # playRecordedUnsafe returns everything needed to reverse the move.
            record = self.board.playRecordedUnsafe(pla, loc)
            self.pass_count = 0

            # Update prisoner counts from the board's capture tracking.
            # Board.num_captures_made[pla] = stones of pla's OWN color captured (suicide)
            # Board.num_captures_made[opp] = stones of opponent captured (by pla's move)
            # In Go convention: "black_prisoners" = stones Black captured FROM White
            opp = Board.get_opp(pla)
            self.black_prisoners = self.board.num_captures_made[Board.BLACK]
            self.white_prisoners = self.board.num_captures_made[Board.WHITE]

            # Superko tracking: compute the new board fingerprint.
            # If the fingerprint is already in ko_history, this move is a superko violation.
            # We record whether WE added it so we know whether to remove it on pop().
            new_hash = self.board.pos_zobrist()
            if new_hash not in self.ko_history:
                self.ko_history.add(new_hash)
                ko_hash_added = new_hash
            else:
                ko_hash_added = None  # hash was already present → superko

        # Recount atari groups after the move. O(groups) is fast enough for 9×9.
        self.atari_count = _count_atari_groups(self.board)

        # Flip whose turn it is.
        self.black_to_play = not self.black_to_play
        # Push the full context onto the history stack so pop() can reverse everything.
        self.move_history.append((loc, record, saved, ko_hash_added))

    def pop(self) -> int:
        """Undo the last move and restore all state.

        Returns:
            The location that was undone.
        """
        loc, record, saved, ko_hash_added = self.move_history.pop()

        # Remove superko hash if we added one during this push.
        # If ko_hash_added is None, the hash was already present before
        # this push (either from game history or an outer search frame),
        # so we must NOT remove it — another frame still needs it.
        if ko_hash_added is not None:
            self.ko_history.discard(ko_hash_added)

        # Unpack and restore all the scalar state we snapshotted in push().
        (
            self.black_to_play,
            self.black_prisoners,
            self.white_prisoners,
            self.pass_count,
            saved_ko_point,              # ← restored here (ko bug fix)
            saved_atari_count,           # ← restored here (atari count fix)
        ) = saved

        if record is not None:
            # Non-pass move: board.undo() uses the record to perfectly reverse
            # all stone placements, captures, and group-data updates.
            self.board.undo(record)
        else:
            # Pass undo: board.playUnsafe(PASS) only changed pla and cleared
            # simple_ko_point.  board.undo() is not available for passes, so
            # we restore both fields manually from the saved snapshot.
            self.board.pla = self.current_player
            self.board.simple_ko_point = saved_ko_point  # ← key fix

        # Restore atari count
        self.atari_count = saved_atari_count

        return loc

    def is_superko_repeat(self) -> bool:
        """Check if the last push() created a repeated board position.

        Call immediately after push() to test for positional superko.
        Returns True if the move is a superko violation.
        Passes never violate superko.
        """
        if not self.move_history:
            return False
        loc, _, _, ko_hash_added = self.move_history[-1]
        if loc == Board.PASS_LOC:
            return False
        # If ko_hash_added is None for a non-pass move, it means the hash was
        # already in the set before we pushed → this is a repeated position.
        return ko_hash_added is None

    def would_violate_superko(self, loc: int) -> bool:
        """Check if playing loc would create a repeated board position.

        Does NOT modify Position state. Tentatively plays the move on the
        board, checks the hash against ko_history, and undoes.
        Only call for moves that are already legal per simple rules.
        Passes never violate superko.
        """
        if loc == Board.PASS_LOC:
            return False
        pla = self.current_player
        # Temporarily play the move to see what board position it produces.
        record = self.board.playRecordedUnsafe(pla, loc)
        new_hash = self.board.pos_zobrist()
        violates = new_hash in self.ko_history
        # Immediately undo the temporary move — Position state is unchanged.
        self.board.undo(record)
        return violates

    def last_move_loc(self) -> int | None:
        """Return the loc of the most recent move, or None if no moves."""
        if not self.move_history:
            return None
        return self.move_history[-1][0]

    def copy(self) -> 'Position':
        """Create a deep copy (for use outside the search, e.g. in main.py)."""
        # We bypass __init__ and manually set every attribute so we don't
        # trigger any default-initialization logic.
        new_pos = Position.__new__(Position)
        new_pos.board = self.board.copy()
        new_pos.black_to_play = self.black_to_play
        new_pos.black_prisoners = self.black_prisoners
        new_pos.white_prisoners = self.white_prisoners
        new_pos.move_history = []  # fresh history for the copy
        new_pos.pass_count = self.pass_count
        new_pos.atari_count = self.atari_count.copy()
        new_pos.ko_history = self.ko_history.copy()
        return new_pos