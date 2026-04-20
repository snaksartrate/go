# environment.py — Game state wrapper around KataGo's Board
#
# Position is a MUTABLE CURSOR, not a snapshot. There is ONE Board instance
# for the entire search tree. The search mutates it forward with push() and
# backward with pop(). All bookkeeping (turn, prisoners, pass count) lives
# inside push/pop so the search never scatters state updates.

from board import Board
from constants import board_size


def _count_atari_groups(board: Board) -> dict:
    """Count groups in atari (exactly 1 liberty) for each player.
    
    Returns dict[Board.BLACK] = count, dict[Board.WHITE] = count.
    """
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


class Position:
    """Thin mutable wrapper around a KataGo Board.

    Architecture:
        - self.board is a SHARED, MUTABLE Board instance.
        - push(pla, loc) plays a move and saves an undo record.
        - pop() undoes the last move and restores all state.
        - move_history is a stack of (loc, record, old_state) tuples.
    """

    __slots__ = (
        'board',
        'black_to_play',
        'black_prisoners',
        'white_prisoners',
        'move_history',
        'pass_count',
        'atari_count',  # Track how many groups are in atari for each player
    )

    def __init__(self, board: Board = None, black_to_play: bool = True):
        self.board = board if board is not None else Board(board_size)
        self.black_to_play = black_to_play
        self.black_prisoners = 0  # stones Black has captured
        self.white_prisoners = 0  # stones White has captured
        self.move_history = []    # stack of (loc, record_or_None, saved_state)
        self.pass_count = 0       # consecutive passes (for game-end detection)
        self.atari_count = {Board.BLACK: 0, Board.WHITE: 0}  # groups in atari

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

        Updates black_to_play, prisoners, pass_count, and atari_count.
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
            # Pass: no board mutation, just toggle turn and bump pass count
            self.board.playUnsafe(pla, Board.PASS_LOC)
            record = None
            self.pass_count += 1
        else:
            record = self.board.playRecordedUnsafe(pla, loc)
            self.pass_count = 0

            # Update prisoner counts from the board's capture tracking
            # Board.num_captures_made[pla] = stones of pla's OWN color captured (suicide)
            # Board.num_captures_made[opp] = stones of opponent captured (by pla's move)
            # In Go convention: "black_prisoners" = stones Black captured FROM White
            opp = Board.get_opp(pla)
            self.black_prisoners = self.board.num_captures_made[Board.BLACK]
            self.white_prisoners = self.board.num_captures_made[Board.WHITE]

        # Recount atari groups (only affected groups change, but O(groups) is fast enough)
        self.atari_count = _count_atari_groups(self.board)

        self.black_to_play = not self.black_to_play
        self.move_history.append((loc, record, saved))

    def pop(self) -> int:
        """Undo the last move and restore all state.

        Returns:
            The location that was undone.
        """
        loc, record, saved = self.move_history.pop()

        (
            self.black_to_play,
            self.black_prisoners,
            self.white_prisoners,
            self.pass_count,
            saved_ko_point,              # ← restored here (ko bug fix)
            saved_atari_count,           # ← restored here (atari count fix)
        ) = saved

        if record is not None:
            # Non-pass move: board.undo() restores simple_ko_point from record.
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

    def last_move_loc(self) -> int | None:
        """Return the loc of the most recent move, or None if no moves."""
        if not self.move_history:
            return None
        return self.move_history[-1][0]

    def copy(self) -> 'Position':
        """Create a deep copy (for use outside the search, e.g. in main.py)."""
        new_pos = Position.__new__(Position)
        new_pos.board = self.board.copy()
        new_pos.black_to_play = self.black_to_play
        new_pos.black_prisoners = self.black_prisoners
        new_pos.white_prisoners = self.white_prisoners
        new_pos.move_history = []  # fresh history for the copy
        new_pos.pass_count = self.pass_count
        new_pos.atari_count = self.atari_count.copy()
        return new_pos