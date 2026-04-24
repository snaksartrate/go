import random
import numpy as np

# ─── Custom Types ───────────────────────────────────────────────────
# For clarity and static analysis in larger projects.
Pos = int    # Represents a 1D index into the board array.
Loc = int    # Synonymous with Pos, used for "location".
Player = int # 0: Empty, 1: Black, 2: White, 3: Wall

class IllegalMoveError(ValueError):
    """Exception raised for moves that violate Go rules (occupied, suicide, simple ko)."""
    pass

# ─── Board Representation ───────────────────────────────────────────

class Board:
    """
    Lower-level Go board implementation using an 'undo-based' architecture.
    
    KEY DESIGN CHARACTERISTICS:
    1. 1D Array Layout: The board is represented as a single flat NumPy array
       with 'walls' padded around the edges to simplify boundary checks.
    2. Linked-List Groups: Stones in the same group (string) are joined in a 
       doubly-linked circular list. This allows O(stones) iteration through a group
       without global board scans.
    3. Incremental Bookkeeping: Liberty counts and stone counts are updated
       incrementally as stones are added/removed.
    4. Zobrist Hashing: Fast board fingerprinting for ko and superko detection.
    """
    
    # Constants for board contents
    EMPTY = 0
    BLACK = 1
    WHITE = 2
    WALL = 3

    # Zobrist random bitstrings for hashing
    ZOBRIST_STONE = [[],[],[],[]] # [color][loc]
    ZOBRIST_PLA = []              # [color] — toggled on every move

    ZOBRIST_RAND = random.Random()
    ZOBRIST_RAND.seed(123987456)

    PASS_LOC = 0 # Unique index representing a 'pass' move.

    # Pre-generate random bits for all possible board locations.
    for i in range((50+1)*(50+2)+1):
        ZOBRIST_STONE[BLACK].append(ZOBRIST_RAND.getrandbits(64))
        ZOBRIST_STONE[WHITE].append(ZOBRIST_RAND.getrandbits(64))
    for i in range(4):
        ZOBRIST_PLA.append(ZOBRIST_RAND.getrandbits(64))

    def __init__(self, size, copy_other=None):
        """
        Initialize a new Board or create a copy of an existing one.
        
        Args:
            size: int (for square) or (x,y) tuple.
            copy_other: If provided, performs a 'deep copy' of this board's state.
        """
        if isinstance(size, int):
            self.x_size = size
            self.y_size = size
        else:
            self.x_size, self.y_size = size
            
        if not (2 <= self.x_size <= 50 and 2 <= self.y_size <= 50):
             raise ValueError(f"Invalid board size: {size}")

        # The internal array is slightly larger to accommodate 'walls'.
        self.arrsize = (self.x_size + 1) * (self.y_size + 2) + 1
        self.dy = self.x_size + 1
        self.adj = [-self.dy, -1, 1, self.dy]       # North, West, East, South offsets
        self.diag = [-self.dy-1, -self.dy+1, self.dy-1, self.dy+1] # Diagonal offsets

        if copy_other is not None:
            # Efficiently clone an existing board's state.
            self.pla = copy_other.pla
            self.board = np.copy(copy_other.board)
            self.group_head = np.copy(copy_other.group_head)
            self.group_stone_count = np.copy(copy_other.group_stone_count)
            self.group_liberty_count = np.copy(copy_other.group_liberty_count)
            self.group_next = np.copy(copy_other.group_next)
            self.group_prev = np.copy(copy_other.group_prev)
            self.zobrist = copy_other.zobrist
            self.simple_ko_point = copy_other.simple_ko_point
            self.num_captures_made = copy_other.num_captures_made.copy()
            self.num_non_pass_moves_made = copy_other.num_non_pass_moves_made.copy()
        else:
            # Initialize a fresh empty board.
            self.pla = Board.BLACK
            self.board = np.zeros(shape=(self.arrsize), dtype=np.int8)
            self.group_head = np.zeros(shape=(self.arrsize), dtype=np.int16)
            self.group_stone_count = np.zeros(shape=(self.arrsize), dtype=np.int16)
            self.group_liberty_count = np.zeros(shape=(self.arrsize), dtype=np.int16)
            self.group_next = np.zeros(shape=(self.arrsize), dtype=np.int16)
            self.group_prev = np.zeros(shape=(self.arrsize), dtype=np.int16)
            self.zobrist = 0
            self.simple_ko_point = None
            self.num_captures_made = {Board.BLACK: 0, Board.WHITE: 0}
            self.num_non_pass_moves_made = {Board.BLACK: 0, Board.WHITE: 0}

            # Seed 'WALL' values around the play area to prevent out-of-bounds checks in search loops.
            for i in range(-1, self.x_size + 1):
                self.board[self.loc(i, -1)] = Board.WALL
                self.board[self.loc(i, self.y_size)] = Board.WALL
            for i in range(-1, self.y_size + 1):
                self.board[self.loc(-1, i)] = Board.WALL
                self.board[self.loc(self.x_size, i)] = Board.WALL

            # Index 0 is reserved; set metadata to -1 to help catch indexing bugs.
            self.group_head[0] = -1
            self.group_next[0] = -1
            self.group_prev[0] = -1

    # ─── Coordinate Conversion ──────────────────────────────────────

    def copy(self):
        """Create a deep copy of the board."""
        return Board((self.x_size, self.y_size), copy_other=self)

    @staticmethod
    def get_opp(pla):
        """Return the opponent's color (BLACK <-> WHITE)."""
        return 3 - pla

    @staticmethod
    def loc_static(x, y, x_size):
        """Static helper to convert (x,y) to 1D loc without a board instance."""
        return (x + 1) + (x_size + 1) * (y + 1)

    def loc(self, x, y):
        """Convert (x, y) coordinates to internal 1D array index."""
        return (x + 1) + self.dy * (y + 1)

    def loc_x(self, loc):
        """Convert 1D array index back to x coordinate."""
        return (loc % self.dy) - 1

    def loc_y(self, loc):
        """Convert 1D array index back to y coordinate."""
        return (loc // self.dy) - 1

    def is_adjacent(self, loc1, loc2):
        """Check if two 1D locations are Manhattan-adjacent (N, S, E, W)."""
        return loc1 == loc2 + self.adj[0] or loc1 == loc2 + self.adj[1] or loc1 == loc2 + self.adj[2] or loc1 == loc2 + self.adj[3]

    def pos_zobrist(self):
        """Return the Zobrist hash of the current stone arrangement."""
        return self.zobrist

    def sit_zobrist(self):
        """Return the Zobrist hash including 'side to move' (situational)."""
        return self.zobrist ^ Board.ZOBRIST_PLA[self.pla]

    def num_liberties(self, loc):
        """Return the number of liberties for the group at this location."""
        if self.board[loc] == Board.EMPTY or self.board[loc] == Board.WALL:
            return 0
        return self.group_liberty_count[self.group_head[loc]]

    # ─── Move Validation Logic ──────────────────────────────────────────

    def is_simple_eye(self, pla, loc):
        """
        Heuristic to detect a 'one-point eye' for a given player.
        
        Strict eye-filling is usually bad play, so engines often use this to 
        filter pointless moves.
        """
        adj0 = loc + self.adj[0]
        adj1 = loc + self.adj[1]
        adj2 = loc + self.adj[2]
        adj3 = loc + self.adj[3]

        # All adjacent points must be player stones or walls.
        if (self.board[adj0] != pla and self.board[adj0] != Board.WALL) or \
           (self.board[adj1] != pla and self.board[adj1] != Board.WALL) or \
           (self.board[adj2] != pla and self.board[adj2] != Board.WALL) or \
           (self.board[adj3] != pla and self.board[adj3] != Board.WALL):
            return False

        opp = Board.get_opp(pla)
        opp_corners = 0
        diag0 = loc + self.diag[0]
        diag1 = loc + self.diag[1]
        diag2 = loc + self.diag[2]
        diag3 = loc + self.diag[3]
        if self.board[diag0] == opp:
            opp_corners += 1
        if self.board[diag1] == opp:
            opp_corners += 1
        if self.board[diag2] == opp:
            opp_corners += 1
        if self.board[diag3] == opp:
            opp_corners += 1

        # A point is an eye if it has < 2 opponent stones on corners (for center)
        # or 0 opponent stones on corners (for edges/walls).
        if opp_corners >= 2:
            return False
        if opp_corners <= 0:
            return True

        against_wall = (
            self.board[adj0] == Board.WALL or \
            self.board[adj1] == Board.WALL or \
            self.board[adj2] == Board.WALL or \
            self.board[adj3] == Board.WALL
        )

        if against_wall:
            return False
        return True


    def would_be_legal(self, pla, loc):
        """Check if playing 'pla' at 'loc' is legal under non-superko rules."""
        if pla != Board.BLACK and pla != Board.WHITE:
            return False
        if loc == Board.PASS_LOC:
            return True
        if not self.is_on_board(loc):
            return False
        if self.board[loc] != Board.EMPTY:
            return False
        if self.would_be_single_stone_suicide(pla, loc):
            return False
        if loc == self.simple_ko_point:
            return False
        return True

    def would_be_suicide(self, pla, loc):
        """Check if placing a stone at 'loc' would result in its immediate removal."""
        adj0 = loc + self.adj[0]
        adj1 = loc + self.adj[1]
        adj2 = loc + self.adj[2]
        adj3 = loc + self.adj[3]

        opp = Board.get_opp(pla)

        # If any adjacent point is empty or results in an opponent capture, it's NOT suicide.
        if self.board[adj0] == Board.EMPTY or (self.board[adj0] == opp and self.group_liberty_count[self.group_head[adj0]] == 1) or \
           self.board[adj1] == Board.EMPTY or (self.board[adj1] == opp and self.group_liberty_count[self.group_head[adj1]] == 1) or \
           self.board[adj2] == Board.EMPTY or (self.board[adj2] == opp and self.group_liberty_count[self.group_head[adj2]] == 1) or \
           self.board[adj3] == Board.EMPTY or (self.board[adj3] == opp and self.group_liberty_count[self.group_head[adj3]] == 1):
            return False
            
        # If it connects to a friendly group with >1 liberty, it's NOT suicide.
        if self.board[adj0] == pla and self.group_liberty_count[self.group_head[adj0]] > 1 or \
           self.board[adj1] == pla and self.group_liberty_count[self.group_head[adj1]] > 1 or \
           self.board[adj2] == pla and self.group_liberty_count[self.group_head[adj2]] > 1 or \
           self.board[adj3] == pla and self.group_liberty_count[self.group_head[adj3]] > 1:
            return False
        return True

    def would_be_single_stone_suicide(self, pla, loc):
        """Check if a move is suicide and DOES NOT capture any opponent stones."""
        adj0 = loc + self.adj[0]
        adj1 = loc + self.adj[1]
        adj2 = loc + self.adj[2]
        adj3 = loc + self.adj[3]

        opp = Board.get_opp(pla)

        if self.board[adj0] == Board.EMPTY or (self.board[adj0] == opp and self.group_liberty_count[self.group_head[adj0]] == 1) or \
           self.board[adj1] == Board.EMPTY or (self.board[adj1] == opp and self.group_liberty_count[self.group_head[adj1]] == 1) or \
           self.board[adj2] == Board.EMPTY or (self.board[adj2] == opp and self.group_liberty_count[self.group_head[adj2]] == 1) or \
           self.board[adj3] == Board.EMPTY or (self.board[adj3] == opp and self.group_liberty_count[self.group_head[adj3]] == 1):
            return False
            
        # If it connects to ANY existing friendly stone, it's not a 'single stone' suicide.
        if self.board[adj0] == pla or \
           self.board[adj1] == pla or \
           self.board[adj2] == pla or \
           self.board[adj3] == pla:
            return False
        return True

    def get_liberties_after_play(self, pla, loc, maxLibs):
        """
        Count how many liberties a new stone at 'loc' would have.
        
        Optimized to stop counting once 'maxLibs' is reached. Used by the 
        ladder search and other heuristics.
        """
        opp = Board.get_opp(pla)
        libs = []
        capturedGroupHeads = []

        # Step 1: Count immediate empty adjacent points and groups that would be captured.
        for i in range(4):
            adj = loc + self.adj[i]
            if self.board[adj] == Board.EMPTY:
                if adj not in libs:
                    libs.append(adj)
                if len(libs) >= maxLibs:
                    return maxLibs

            elif self.board[adj] == opp and self.num_liberties(adj) == 1:
                # If we capture a group, its former location becomes a liberty for the new stone.
                if adj not in libs:
                    libs.append(adj)
                if len(libs) >= maxLibs:
                    return maxLibs

                head = self.group_head[adj]
                if head not in capturedGroupHeads:
                    capturedGroupHeads.append(head)

        def wouldBeEmpty(possibleLib):
            """Check if a point will be empty after the move is processed."""
            if self.board[possibleLib] == Board.EMPTY:
                return True
            elif self.board[possibleLib] == opp:
                # Opponent groups with 1 liberty will be removed.
                return (self.group_head[possibleLib] in capturedGroupHeads)
            return False

        # Step 2: Iterate through all stones of friendly groups we connect to.
        connectingGroupHeads = []
        for i in range(4):
            adj = loc + self.adj[i]
            if self.board[adj] == pla:
                head = self.group_head[adj]
                if head not in connectingGroupHeads:
                    connectingGroupHeads.append(head)

                    # Iterate through the linked-list of stones in the combined group.
                    cur = adj
                    while True:
                        for k in range(4):
                            possibleLib = cur + self.adj[k]
                            if possibleLib != loc and wouldBeEmpty(possibleLib) and possibleLib not in libs:
                                libs.append(possibleLib)
                                if len(libs) >= maxLibs:
                                    return maxLibs

                        cur = self.group_next[cur]
                        if cur == adj:
                            break

        return len(libs)

    # ─── Display Helpers ────────────────────────────────────────────────

    def to_string(self):
        """Return a basic text representation of the board."""
        def get_piece(x, y):
            loc = self.loc(x, y)
            if self.board[loc] == Board.BLACK:
                return 'X '
            elif self.board[loc] == Board.WHITE:
                return 'O '
            elif (x == 3 or x == self.x_size/2 or x == self.x_size-1-3) and (y == 3 or y == self.y_size/2 or y == self.y_size-1-3):
                return '* ' # Star points (Hoshi)
            else:
                return '. '

        return "\n".join("".join(get_piece(x, y) for x in range(self.x_size)) for y in range(self.y_size))

    def to_liberty_string(self):
        """Return a board maps showing liberty counts for each stone."""
        def get_piece(x, y):
            loc = self.loc(x, y)
            if self.board[loc] == Board.BLACK or self.board[loc] == Board.WHITE:
                libs = self.group_liberty_count[self.group_head[loc]]
                if libs <= 9:
                    return str(libs) + ' '
                else:
                    return '@ '
            elif (x == 3 or x == self.x_size/2 or x == self.x_size-1-3) and (y == 3 or y == self.y_size/2 or y == self.y_size-1-3):
                return '* '
            else:
                return '. '

        return "\n".join("".join(get_piece(x, y) for x in range(self.x_size)) for y in range(self.y_size))

    def set_pla(self, pla):
        """Manually set the current player to move."""
        self.pla = pla

    def is_on_board(self, loc):
        """Check if a 1D location index is within the playable area (not a wall)."""
        return 0 <= loc < self.arrsize and self.board[loc] != Board.WALL

    # ─── Board Mutation & Undo ──────────────────────────────────────────

    def set_stone(self, pla, loc):
        """
        Forcefully set a location to a given color or EMPTY.
        
        This clears the ko point and handles group merging/removal automatically.
        """
        if pla != Board.EMPTY and pla != Board.BLACK and pla != Board.WHITE:
            raise IllegalMoveError("Invalid pla for board.set")
        if not self.is_on_board(loc):
            raise IllegalMoveError("Invalid loc for board.set")

        if self.board[loc] == pla:
            return
        elif self.board[loc] == Board.EMPTY:
            self.add_unsafe(pla, loc)
        elif pla == Board.EMPTY:
            self.remove_single_stone_unsafe(loc)
        else:
            self.remove_single_stone_unsafe(loc)
            self.add_unsafe(pla, loc)

        self.simple_ko_point = None

    def play(self, pla, loc):
        """
        Execute a move with full legality checks (occupied, suicide, ko).
        
        Does NOT check positional superko (handled by environment.Position).
        """
        if pla != Board.BLACK and pla != Board.WHITE:
            raise IllegalMoveError("Invalid pla for board.play")

        if loc != Board.PASS_LOC:
            if not self.is_on_board(loc):
                raise IllegalMoveError("Invalid loc for board.set")
            if self.board[loc] != Board.EMPTY:
                raise IllegalMoveError("Location is nonempty")
            if self.would_be_single_stone_suicide(pla, loc):
                raise IllegalMoveError("Move would be illegal single stone suicide")
            if loc == self.simple_ko_point:
                raise IllegalMoveError("Move would be illegal simple ko recapture")

        self.playUnsafe(pla, loc)

    def playUnsafe(self, pla, loc):
        """Execute a move WITHOUT performing legality checks."""
        if loc == Board.PASS_LOC:
            self.simple_ko_point = None
            self.pla = Board.get_opp(pla)
        else:
            self.add_unsafe(pla, loc)
            self.pla = Board.get_opp(pla)

    def playRecordedUnsafe(self, pla, loc):
        """
        Execute a move and return an opaque record used to undo it.
        
        This is used throughout the search tree to avoid copying the whole board.
        """
        capDirs = []
        opp = Board.get_opp(pla)
        old_simple_ko_point = self.simple_ko_point
        
        # Determine which adjacent opponent groups will be captured.
        for i in range(4):
            adj = loc + self.adj[i]
            if self.board[adj] == opp and self.group_liberty_count[self.group_head[adj]] == 1:
                capDirs.append(i)
                
        old_num_captures_made = self.num_captures_made.copy()
        old_num_non_pass_moves_made = self.num_non_pass_moves_made.copy()

        self.playUnsafe(pla, loc)

        # Suicide check: did the move result in the stone being captured immediately?
        selfCap = False
        if self.board[loc] == Board.EMPTY:
            selfCap = True
            
        return (pla, loc, old_simple_ko_point, capDirs, selfCap, old_num_captures_made, old_num_non_pass_moves_made)

    def undo(self, record):
        """
        Roll back a move created by playRecordedUnsafe().
        
        Restores prisoner counts, group data, board contents, and Zobrist hash.
        """
        (pla, loc, simple_ko_point, capDirs, selfCap, old_num_captures_made, old_num_non_pass_moves_made) = record
        opp = Board.get_opp(pla)

        self.simple_ko_point = simple_ko_point
        self.pla = pla
        self.num_captures_made = old_num_captures_made.copy()
        self.num_non_pass_moves_made = old_num_non_pass_moves_made.copy()

        if loc == Board.PASS_LOC:
            return

        # Restore stones that were captured by this move.
        for capdir in capDirs:
            adj = loc + self.adj[capdir]
            if self.board[adj] == Board.EMPTY:
                self.floodFillStones(opp, adj)

        # Restore the stone itself if it was a suicide move.
        if selfCap:
            self.floodFillStones(pla, loc)

        # Remove the move's stone from the board and revert hash.
        self.zobrist ^= Board.ZOBRIST_STONE[pla][loc]
        self.board[loc] = Board.EMPTY

        # Re-initialize group data at this location for rebuilding.
        head = self.group_head[loc]
        stone_count = self.group_stone_count[head]
        self.group_stone_count[head] = 0
        self.group_liberty_count[head] = 0

        # Increment liberties of surrounding opponent groups (which we had decreased).
        self.changeSurroundingLiberties(loc, Board.get_opp(pla), +1)

        # If the move merged multiple groups, we must rebuild the connected components.
        if stone_count > 1:
            # First, decouple all stones in the chain from their old head.
            cur = loc
            while True:
                self.group_head[cur] = Board.PASS_LOC
                cur = self.group_next[cur]
                if cur == loc:
                    break

            # Re-floodfill each adjacent sector to rebuild independent group data.
            for i in range(4):
                adj = loc + self.adj[i]
                if self.board[adj] == pla and self.group_head[adj] == Board.PASS_LOC:
                    self.rebuildChain(pla, adj)

        self.group_head[loc] = 0
        self.group_next[loc] = 0
        self.group_prev[loc] = 0


    # ─── Group Management (Low Level) ───────────────────────────────────

    def floodFillStones(self, pla, loc):
        """
        Flood-fill a region of empty space with stones of player 'pla'.
        
        This is used to restore captured stones during an undo operation.
        """
        head = loc
        self.group_liberty_count[head] = 0
        self.group_stone_count[head] = 0

        # producess a linear linked list head <-> next <-> ... <-> tail
        front = self.floodFillStonesHelper(head, head, head, pla)

        # Complete the circularity: tail points to front.
        self.group_next[head] = front
        self.group_prev[front] = head

    def floodFillStonesHelper(self, head, tailTarget, loc, pla):
        """
        Recursive helper for floodFillStones.
        
        Builds a linear doubly-linked list of stones and updates the Zobrist hash.
        """
        self.board[loc] = pla
        self.zobrist ^= Board.ZOBRIST_STONE[pla][loc]

        self.group_head[loc] = head
        self.group_stone_count[head] += 1
        self.group_next[loc] = tailTarget
        self.group_prev[tailTarget] = loc

        # Decrement liberties of any surrounding opponent groups.
        self.changeSurroundingLiberties(loc, Board.get_opp(pla), -1)

        # Recurse to all adjacent empty spots to expand the group.
        nextTailTarget = loc
        for i in range(4):
            adj = loc + self.adj[i]
            if self.board[adj] == Board.EMPTY:
                nextTailTarget = self.floodFillStonesHelper(head, nextTailTarget, adj, pla)
        return nextTailTarget

    def rebuildChain(self, pla, loc):
        """
        Re-scans an existing group on the board to rebuild its linked-list metadata.
        
        Used after an undo splits a larger group back into its original parts.
        """
        head = loc
        self.group_liberty_count[head] = 0
        self.group_stone_count[head] = 0

        front = self.rebuildChainHelper(head, head, head, pla)

        self.group_next[head] = front
        self.group_prev[front] = head

    def rebuildChainHelper(self, head, tailTarget, loc, pla):
        """Recursive helper for rebuildChain. Calculates liberties while tracing."""
        # Check all adjacent points for new liberties, avoiding double-counting.
        for dloc in self.adj:
            new_lib = loc + dloc
            if self.board[new_lib] == Board.EMPTY and not self.is_group_adjacent(head, new_lib):
                self.group_liberty_count[head] += 1

        self.group_head[loc] = head
        self.group_stone_count[head] += 1
        self.group_next[loc] = tailTarget
        self.group_prev[tailTarget] = loc

        nextTailTarget = loc
        for i in range(4):
            adj = loc + self.adj[i]
            # Recursively find all stones of this group that haven't been processed yet.
            if self.board[adj] == pla and self.group_head[adj] != head:
                nextTailTarget = self.rebuildChainHelper(head, nextTailTarget, adj, pla)
        return nextTailTarget


    def add_unsafe(self, pla, loc):
        """
        Place a stone at 'loc' and update all group metadata.
        
        This handles capturing opponent stones, potential suicide, and 
        merging with adjacent friendly groups.
        """
        opp = Board.get_opp(pla)

        # Put the stone down and update fingerprint.
        self.board[loc] = pla
        self.zobrist ^= Board.ZOBRIST_STONE[pla][loc]

        # Initialize the group specifically for this single stone.
        self.group_head[loc] = loc
        self.group_stone_count[loc] = 1
        self.group_liberty_count[loc] = self.countImmediateLiberties(loc)
        self.group_next[loc] = loc
        self.group_prev[loc] = loc

        # Subtract one liberty from all adjacent groups (they are now partially blocked).
        adj0 = loc + self.adj[0]
        adj1 = loc + self.adj[1]
        adj2 = loc + self.adj[2]
        adj3 = loc + self.adj[3]
        
        # We must be careful not to subtract multiple liberties from the same group
        # if the new stone borders it on multiple sides.
        if self.board[adj0] == Board.BLACK or self.board[adj0] == Board.WHITE:
            self.group_liberty_count[self.group_head[adj0]] -= 1
        if self.board[adj1] == Board.BLACK or self.board[adj1] == Board.WHITE:
            if self.group_head[adj1] != self.group_head[adj0]:
                self.group_liberty_count[self.group_head[adj1]] -= 1
        if self.board[adj2] == Board.BLACK or self.board[adj2] == Board.WHITE:
            if self.group_head[adj2] != self.group_head[adj0] and \
               self.group_head[adj2] != self.group_head[adj1]:
                self.group_liberty_count[self.group_head[adj2]] -= 1
        if self.board[adj3] == Board.BLACK or self.board[adj3] == Board.WHITE:
            if self.group_head[adj3] != self.group_head[adj0] and \
               self.group_head[adj3] != self.group_head[adj1] and \
               self.group_head[adj3] != self.group_head[adj2]:
                self.group_liberty_count[self.group_head[adj3]] -= 1

        # If adjacent to friendly stones, merge this stone into their group.
        if self.board[adj0] == pla:
            self.merge_unsafe(loc, adj0)
        if self.board[adj1] == pla:
            self.merge_unsafe(loc, adj1)
        if self.board[adj2] == pla:
            self.merge_unsafe(loc, adj2)
        if self.board[adj3] == pla:
            self.merge_unsafe(loc, adj3)

        # Resolve captures: check if any opponent groups now have 0 liberties.
        opp_stones_captured = 0
        caploc = 0
        if self.board[adj0] == opp and self.group_liberty_count[self.group_head[adj0]] == 0:
            opp_stones_captured += self.group_stone_count[self.group_head[adj0]]
            caploc = adj0
            self.remove_unsafe(adj0)
        if self.board[adj1] == opp and self.group_liberty_count[self.group_head[adj1]] == 0:
            opp_stones_captured += self.group_stone_count[self.group_head[adj1]]
            caploc = adj1
            self.remove_unsafe(adj1)
        if self.board[adj2] == opp and self.group_liberty_count[self.group_head[adj2]] == 0:
            opp_stones_captured += self.group_stone_count[self.group_head[adj2]]
            caploc = adj2
            self.remove_unsafe(adj2)
        if self.board[adj3] == opp and self.group_liberty_count[self.group_head[adj3]] == 0:
            opp_stones_captured += self.group_stone_count[self.group_head[adj3]]
            caploc = adj3
            self.remove_unsafe(adj3)

        # Suicide check: if the stone we just played has 0 liberties, it captures itself.
        pla_stones_captured = 0
        if self.group_liberty_count[self.group_head[loc]] == 0:
            pla_stones_captured += self.group_stone_count[self.group_head[loc]]
            self.remove_unsafe(loc)

        self.num_captures_made[pla] += pla_stones_captured
        self.num_captures_made[opp] += opp_stones_captured
        self.num_non_pass_moves_made[pla] += 1

        # Simple Ko Rule: if exactly one stone was captured and the capturing group
        # is also a single stone in atari, that point is forbidden for the next turn.
        if opp_stones_captured == 1 and \
           self.group_stone_count[self.group_head[loc]] == 1 and \
           self.group_liberty_count[self.group_head[loc]] == 1:
            self.simple_ko_point = caploc
        else:
            self.simple_ko_point = None

    def changeSurroundingLiberties(self, loc, pla, delta):
        """Update the liberty counts of all groups of 'pla' bordering 'loc'."""
        adj0 = loc + self.adj[0]
        adj1 = loc + self.adj[1]
        adj2 = loc + self.adj[2]
        adj3 = loc + self.adj[3]
        if self.board[adj0] == pla:
            self.group_liberty_count[self.group_head[adj0]] += delta
        if self.board[adj1] == pla:
            if self.group_head[adj1] != self.group_head[adj0]:
                self.group_liberty_count[self.group_head[adj1]] += delta
        if self.board[adj2] == pla:
            if self.group_head[adj2] != self.group_head[adj0] and \
               self.group_head[adj2] != self.group_head[adj1]:
                self.group_liberty_count[self.group_head[adj2]] += delta
        if self.board[adj3] == pla:
            if self.group_head[adj3] != self.group_head[adj0] and \
               self.group_head[adj3] != self.group_head[adj1] and \
               self.group_head[adj3] != self.group_head[adj2]:
                self.group_liberty_count[self.group_head[adj3]] += delta

    def countImmediateLiberties(self, loc):
        """Manually count empty intersections around a single board location."""
        count = 0
        for i in range(4):
            if self.board[loc + self.adj[i]] == Board.EMPTY:
                count += 1
        return count

    def is_group_adjacent(self, head, loc):
        """Check if any stone in the group 'head' is touching 'loc'."""
        return (
            self.group_head[loc+self.adj[0]] == head or \
            self.group_head[loc+self.adj[1]] == head or \
            self.group_head[loc+self.adj[2]] == head or \
            self.group_head[loc+self.adj[3]] == head
        )

    def merge_unsafe(self, loc0, loc1):
        """
        Merge the groups containing 'loc0' and 'loc1'.
        
        Optimized by merging the smaller group into the larger one.
        """
        if self.group_stone_count[self.group_head[loc0]] >= self.group_stone_count[self.group_head[loc1]]:
            parent = loc0
            child = loc1
        else:
            child = loc0
            parent = loc1

        phead = self.group_head[parent]
        chead = self.group_head[child]
        if phead == chead:
            return # Already in the same group.

        # Calculate new group properties.
        new_stone_count = self.group_stone_count[phead] + self.group_stone_count[chead]
        new_liberties = self.group_liberty_count[phead]
        
        # Traverse the 'child' group stones to reassign their head and count unique liberties.
        loc = child
        while True:
            adj0 = loc + self.adj[0]
            adj1 = loc + self.adj[1]
            adj2 = loc + self.adj[2]
            adj3 = loc + self.adj[3]

            # A point is a new liberty if it's EMPTY and NOT already adjacent to the 'parent' group.
            if self.board[adj0] == Board.EMPTY and not self.is_group_adjacent(phead, adj0):
                new_liberties += 1
            if self.board[adj1] == Board.EMPTY and not self.is_group_adjacent(phead, adj1):
                new_liberties += 1
            if self.board[adj2] == Board.EMPTY and not self.is_group_adjacent(phead, adj2):
                new_liberties += 1
            if self.board[adj3] == Board.EMPTY and not self.is_group_adjacent(phead, adj3):
                new_liberties += 1

            self.group_head[loc] = phead
            loc = self.group_next[loc]
            if loc == child: # Circular list end
                break

        # Reset the old child head.
        self.group_stone_count[chead] = 0
        self.group_liberty_count[chead] = 0

        # Update the new parent head.
        self.group_stone_count[phead] = new_stone_count
        self.group_liberty_count[phead] = new_liberties

        # Splice the two circular linked lists together.
        plast = self.group_prev[phead]
        clast = self.group_prev[chead]
        self.group_next[clast] = phead
        self.group_next[plast] = chead
        self.group_prev[chead] = plast
        self.group_prev[phead] = clast

    def remove_unsafe(self, group):
        """Remove an entire group of stones from the board."""
        head = self.group_head[group]
        pla = self.board[group]
        opp = Board.get_opp(pla)

        # Iterate through every stone in the group.
        loc = group
        while True:
            # When a stone is removed, all adjacent opponent groups gain a liberty.
            adj0 = loc + self.adj[0]
            adj1 = loc + self.adj[1]
            adj2 = loc + self.adj[2]
            adj3 = loc + self.adj[3]
            
            if self.board[adj0] == opp:
                self.group_liberty_count[self.group_head[adj0]] += 1
            if self.board[adj1] == opp:
                if self.group_head[adj1] != self.group_head[adj0]:
                    self.group_liberty_count[self.group_head[adj1]] += 1
            if self.board[adj2] == opp:
                if self.group_head[adj2] != self.group_head[adj0] and \
                   self.group_head[adj2] != self.group_head[adj1]:
                    self.group_liberty_count[self.group_head[adj2]] += 1
            if self.board[adj3] == opp:
                if self.group_head[adj3] != self.group_head[adj0] and \
                   self.group_head[adj3] != self.group_head[adj1] and \
                   self.group_head[adj3] != self.group_head[adj2]:
                    self.group_liberty_count[self.group_head[adj3]] += 1

            next_loc = self.group_next[loc]

            # Reset the board square and group info.
            self.board[loc] = Board.EMPTY
            self.zobrist ^= Board.ZOBRIST_STONE[pla][loc] # Revert hash
            self.group_head[loc] = 0
            self.group_next[loc] = 0
            self.group_prev[loc] = 0

            loc = next_loc
            if loc == group:
                break

        self.group_stone_count[head] = 0
        self.group_liberty_count[head] = 0

    def remove_single_stone_unsafe(self, rloc):
        """
        Remove exactly one stone at 'rloc'.
        
        If this stone was part of a larger group, it temporarily removes the whole 
        group and then re-adds all stones EXCEPT for 'rloc'.
        """
        pla = self.board[rloc]

        stones = []
        loc = rloc
        while True:
            stones.append(loc)
            loc = self.group_next[loc]
            if loc == rloc:
                break

        self.remove_unsafe(rloc)

        for loc in stones:
            if loc != rloc:
                self.add_unsafe(pla, loc)

    # ─── Heuristic Search Helpers ─────────────────────────────────────

    def findLiberties(self, loc, buf):
        """Append all empty intersections adjacent to group at 'loc' into 'buf'."""
        cur = loc
        while True:
            for i in range(4):
                lib = cur + self.adj[i]
                if self.board[lib] == Board.EMPTY:
                    if lib not in buf:
                        buf.append(lib)
            cur = self.group_next[cur]
            if cur == loc:
                break

    def findLibertyGainingCaptures(self, loc, buf):
        """
        Find all opponent stones adjacent to group 'loc' that are in atari.
        
        Capturing these would gain liberties for the group at 'loc'.
        """
        pla = self.board[loc]
        opp = Board.get_opp(pla)
        chainHeadsChecked = []

        cur = loc
        while True:
            for i in range(4):
                adj = cur + self.adj[i]
                if self.board[adj] == opp:
                    head = self.group_head[adj]
                    if self.group_liberty_count[head] == 1:
                        if head not in chainHeadsChecked:
                            self.findLiberties(adj, buf)
                            chainHeadsChecked.append(head)
            cur = self.group_next[cur]
            if cur == loc:
                break

    def hasLibertyGainingCaptures(self, loc):
        """Check if group at 'loc' can gain liberties by capturing an adjacent opponent."""
        pla = self.board[loc]
        opp = Board.get_opp(pla)

        cur = loc
        while True:
            for i in range(4):
                adj = cur + self.adj[i]
                if self.board[adj] == opp:
                    head = self.group_head[adj]
                    if self.group_liberty_count[head] == 1:
                        return True
            cur = self.group_next[cur]
            if cur == loc:
                break
        return False

    def wouldBeKoCapture(self, loc, pla):
        """Check if playing 'pla' at 'loc' would result in a simple ko-style capture."""
        if self.board[loc] != Board.EMPTY:
            return False
        opp = Board.get_opp(pla)
        oppCapturableLoc = None
        for i in range(4):
            adj = loc + self.adj[i]
            if self.board[adj] != Board.WALL and self.board[adj] != opp:
                return False
            if self.board[adj] == opp and self.group_liberty_count[self.group_head[adj]] == 1:
                if oppCapturableLoc is not None:
                    return False
                oppCapturableLoc = adj

        if oppCapturableLoc is None:
            return False

        if self.group_stone_count[self.group_head[oppCapturableLoc]] != 1:
            return False
        return True

    def countHeuristicConnectionLiberties(self, loc, pla):
        """Estimate potential liberties gained by connecting to adjacent friendly groups."""
        count = 0.0
        for i in range(4):
            adj = loc + self.adj[i]
            if self.board[adj] == pla:
                count += max(0.0, self.group_liberty_count[self.group_head[adj]] - 1.5)
        return count

    # ─── Ladder Search (Tactical) ───────────────────────────────────────

    def searchIsLadderCapturedAttackerFirst2Libs(self, loc):
        """
        Special case for ladder search: defender has exactly 2 liberties.
        
        Returns which of the 2 liberties (if any) allows the attacker to 
        successfully capture the group in a ladder.
        """
        if not self.is_on_board(loc):
            return []
        if self.board[loc] != Board.BLACK and self.board[loc] != Board.WHITE:
            return []
        if self.group_liberty_count[self.group_head[loc]] != 2:
            return []

        pla = self.board[loc]
        opp = Board.get_opp(pla)

        moves = []
        self.findLiberties(loc, moves)
        assert(len(moves) == 2)

        move0 = moves[0]
        move1 = moves[1]
        move0Works = False
        move1Works = False

        if self.would_be_legal(opp, move0):
            record = self.playRecordedUnsafe(opp, move0)
            move0Works = self.searchIsLadderCaptured(loc, True)
            self.undo(record)
        if self.would_be_legal(opp, move1):
            record = self.playRecordedUnsafe(opp, move1)
            move1Works = self.searchIsLadderCaptured(loc, True)
            self.undo(record)

        workingMoves = []
        if move0Works:
            workingMoves.append(move0)
        if move1Works:
            workingMoves.append(move1)

        return workingMoves


    def searchIsLadderCaptured(self, loc, defenderFirst):
        """
        Perform a tactical search to determine if a group is ladder-captured.
        
        This is a mini-search within the search that only considers moves
        at the group's liberties and captures that gain liberties. It uses
        a manual stack to avoid Python's recursion limit and for performance.
        """
        if not self.is_on_board(loc):
            return False
        if self.board[loc] != Board.BLACK and self.board[loc] != Board.WHITE:
            return False

        # Termination: if the group already has >2 libs (or >1 if it's our turn),
        # the ladder has failed for the attacker.
        if self.group_liberty_count[self.group_head[loc]] > 2 or (defenderFirst and self.group_liberty_count[self.group_head[loc]] > 1):
            return False

        pla = self.board[loc]
        opp = Board.get_opp(pla)

        arrSize = self.x_size * self.y_size * 2
        
        # Search state storage
        moveLists = [[] for i in range(arrSize)]
        moveListCur = [0 for i in range(arrSize)]
        records = [None for i in range(arrSize)]
        stackIdx = 0

        moveLists[0] = []
        moveListCur[0] = -1

        returnValue = False
        returnedFromDeeper = False

        saved_simple_ko_point = self.simple_ko_point
        if defenderFirst:
            self.simple_ko_point = None

        while True:
            if stackIdx <= -1:
                assert(stackIdx == -1)
                self.simple_ko_point = saved_simple_ko_point
                return returnValue

            isDefender = (defenderFirst and (stackIdx % 2) == 0) or (not defenderFirst and (stackIdx % 2) == 1)

            # --- LEVEL ENTRY ---
            if moveListCur[stackIdx] == -1:
                libs = self.group_liberty_count[self.group_head[loc]]

                # Ladder Base Cases:
                # 1. Attacker to move and defender in atari (1 lib) -> Attacker wins.
                if not isDefender and libs <= 1:
                    returnValue = True
                    returnedFromDeeper = True
                    stackIdx -= 1
                    continue

                # 2. Attacker to move and defender has 3 libs -> Defender escapes.
                if not isDefender and libs >= 3:
                    returnValue = False
                    returnedFromDeeper = True
                    stackIdx -= 1
                    continue

                # 3. Defender to move and has 2+ libs -> Defender escapes.
                if isDefender and libs >= 2:
                    returnValue = False
                    returnedFromDeeper = True
                    stackIdx -= 1
                    continue

                # 4. Defender to move and attacker left a ko point -> Assume defender escapes (avoid ko-bound ladders).
                if isDefender and self.simple_ko_point is not None:
                    returnValue = False
                    returnedFromDeeper = True
                    stackIdx -= 1
                    continue

                # Generate moves for the current side.
                if isDefender:
                    moveLists[stackIdx] = []
                    self.findLibertyGainingCaptures(loc, moveLists[stackIdx])
                    self.findLiberties(loc, moveLists[stackIdx])
                else:
                    moveLists[stackIdx] = []
                    self.findLiberties(loc, moveLists[stackIdx])
                    assert(len(moveLists[stackIdx]) == 2)

                    move0 = moveLists[stackIdx][0]
                    move1 = moveLists[stackIdx][1]
                    libs0 = self.countImmediateLiberties(move0)
                    libs1 = self.countImmediateLiberties(move1)

                    # Attacker check: is this a double-ko death trap?
                    if libs0 == 0 and libs1 == 0 and self.wouldBeKoCapture(move0, opp) and self.wouldBeKoCapture(move1, opp):
                        if self.get_liberties_after_play(pla, move0, 3) <= 2 and self.get_liberties_after_play(pla, move1, 3) <= 2:
                            if self.hasLibertyGainingCaptures(loc):
                                returnValue = True
                                returnedFromDeeper = True
                                stackIdx -= 1
                                continue

                    # Automatic failure if both escape directions grant >= 3 liberties.
                    if not self.is_adjacent(move0, move1):
                        if libs0 >= 3 and libs1 >= 3:
                            returnValue = False
                            returnedFromDeeper = True
                            stackIdx -= 1
                            continue
                        elif libs0 >= 3:
                            moveLists[stackIdx] = [move0]
                        elif libs1 >= 3:
                            moveLists[stackIdx] = [move1]

                    # Heuristic Move Ordering: search the most promising escape route first.
                    if len(moveLists[stackIdx]) > 1:
                        libs0 += self.countHeuristicConnectionLiberties(move0, pla)
                        libs1 += self.countHeuristicConnectionLiberties(move1, pla)
                        if libs1 > libs0:
                            moveLists[stackIdx][0] = move1
                            moveLists[stackIdx][1] = move0

                moveListCur[stackIdx] = 0

            # --- RETURN FROM LEVEL ---
            else:
                assert(moveListCur[stackIdx] >= 0)
                if returnedFromDeeper:
                    self.undo(records[stackIdx])

                # Pruning: stop early if we found a winning path for the current side.
                if isDefender and not returnValue:
                    returnedFromDeeper = True
                    stackIdx -= 1
                    continue
                if not isDefender and returnValue:
                    returnedFromDeeper = True
                    stackIdx -= 1
                    continue

                moveListCur[stackIdx] += 1

            # No more moves at this level? Side whose turn it was loses.
            if moveListCur[stackIdx] >= len(moveLists[stackIdx]):
                returnValue = isDefender
                returnedFromDeeper = True
                stackIdx -= 1
                continue

            # --- SEARCH NEXT NODE ---
            move = moveLists[stackIdx][moveListCur[stackIdx]]
            side = (pla if isDefender else opp)

            if not self.would_be_legal(side, move):
                returnValue = isDefender
                returnedFromDeeper = False
                continue

            records[stackIdx] = self.playRecordedUnsafe(side, move)
            stackIdx += 1
            moveListCur[stackIdx] = -1
            moveLists[stackIdx] = []


    # ─── Area Scoring & Life/Death ─────────────────────────────────────

    def calculateArea(self, result, nonPassAliveStones, safeBigTerritories, unsafeBigTerritories, isMultiStoneSuicideLegal):
        """
        Populate 'result' array with the area owner of each intersection.
        
        This uses Benson's Algorithm and flood-fills to determine territory 
        and life/death.
        """
        for i in range(self.arrsize):
            result[i] = Board.EMPTY
            
        self.calculateAreaForPla(Board.BLACK, safeBigTerritories, unsafeBigTerritories, isMultiStoneSuicideLegal, result)
        self.calculateAreaForPla(Board.WHITE, safeBigTerritories, unsafeBigTerritories, isMultiStoneSuicideLegal, result)

        if nonPassAliveStones:
            for y in range(self.y_size):
                for x in range(self.x_size):
                    loc = self.loc(x, y)
                    if result[loc] == Board.EMPTY:
                        result[loc] = self.board[loc]

    def calculateNonDameTouchingArea(self, result, keepTerritories, keepStones, isMultiStoneSuicideLegal):
        """
        Determine area but filter out 'dame' (neutral points) that touch both sides.
        """
        basicArea = [Board.EMPTY for i in range(self.arrsize)]
        for i in range(self.arrsize):
            result[i] = Board.EMPTY
        self.calculateAreaForPla(Board.BLACK, True, True, isMultiStoneSuicideLegal, basicArea)
        self.calculateAreaForPla(Board.WHITE, True, True, isMultiStoneSuicideLegal, basicArea)

        for y in range(self.y_size):
            for x in range(self.x_size):
                loc = self.loc(x, y)
                if basicArea[loc] == Board.EMPTY:
                    basicArea[loc] = self.board[loc]

        self.calculateNonDameTouchingAreaHelper(basicArea, result)

        if keepTerritories:
            for y in range(self.y_size):
                for x in range(self.x_size):
                    loc = self.loc(x, y)
                    if basicArea[loc] != Board.EMPTY and basicArea[loc] != self.board[loc]:
                        result[loc] = basicArea[loc]

        if keepStones:
            for y in range(self.y_size):
                for x in range(self.x_size):
                    loc = self.loc(x, y)
                    if basicArea[loc] != Board.EMPTY and basicArea[loc] == self.board[loc]:
                        result[loc] = basicArea[loc]

    def calculateAreaForPla(self, pla, safeBigTerritories, unsafeBigTerritories, isMultiStoneSuicideLegal, result):
        """
        Core implementation of Benson's Algorithm for a specific player.
        
        Identifies 'pass-alive' groups that cannot be captured regardless of moves.
        Iteratively 'kills' groups that don't have at least two vital liberties 
        (eyes) until only safe groups remain.
        """
        opp = self.get_opp(pla)

        regionHeadByLoc = [Board.PASS_LOC for i in range(self.arrsize)]
        nextEmptyOrOpp = [Board.PASS_LOC for i in range(self.arrsize)]
        bordersNonPassAlivePlaByHead = [False for i in range(self.arrsize)]

        maxRegions = (self.x_size * self.y_size + 1)//2 + 1
        vitalForPlaHeadsListsMaxLen = maxRegions * 4
        vitalForPlaHeadsLists = [-1 for i in range(vitalForPlaHeadsListsMaxLen)]
        vitalForPlaHeadsListsTotal = 0

        numRegions = 0
        regionHeads = [-1 for i in range(maxRegions)]
        vitalStart = [-1 for i in range(maxRegions)]
        vitalLen = [-1 for i in range(maxRegions)]
        numInternalSpacesMax2 = [-1 for i in range(maxRegions)]
        containsOpp = [False for i in range(maxRegions)]

        def isAdjacentToPlaHead(loc, plaHead):
            for i in range(4):
                adj = loc + self.adj[i]
                if self.board[adj] == pla and self.group_head[adj] == plaHead:
                    return True
            return False

        def buildRegion(head, tailTarget, loc, regionIdx):
            """Identify a contiguous region of non-player intersections."""
            if regionHeadByLoc[loc] != Board.PASS_LOC:
                return tailTarget
            regionHeadByLoc[loc] = head

            if isMultiStoneSuicideLegal or self.board[loc] == Board.EMPTY:
                vStart = vitalStart[regionIdx]
                oldVLen = vitalLen[regionIdx]
                newVLen = 0
                for i in range(oldVLen):
                    if isAdjacentToPlaHead(loc, vitalForPlaHeadsLists[vStart+i]):
                        vitalForPlaHeadsLists[vStart+newVLen] = vitalForPlaHeadsLists[vStart+i]
                        newVLen += 1
                vitalLen[regionIdx] = newVLen

            if numInternalSpacesMax2[regionIdx] < 2:
                isInternal = True
                for i in range(4):
                    adj = loc + self.adj[i]
                    if self.board[adj] == pla:
                        isInternal = False
                        break
                if isInternal:
                    numInternalSpacesMax2[regionIdx] += 1

            if self.board[loc] == opp:
                containsOpp[regionIdx] = True

            nextEmptyOrOpp[loc] = tailTarget
            nextTailTarget = loc
            for i in range(4):
                adj = loc + self.adj[i]
                if self.board[adj] == Board.EMPTY or self.board[adj] == opp:
                    nextTailTarget = buildRegion(head, nextTailTarget, adj, regionIdx)

            return nextTailTarget

        atLeastOnePla = False
        for y in range(self.y_size):
            for x in range(self.x_size):
                loc = self.loc(x, y)
                if regionHeadByLoc[loc] != Board.PASS_LOC:
                    continue
                if self.board[loc] != Board.EMPTY:
                    atLeastOnePla |= (self.board[loc] == pla)
                    continue

                regionIdx = numRegions
                numRegions += 1
                head = loc
                regionHeads[regionIdx] = head
                vitalStart[regionIdx] = vitalForPlaHeadsListsTotal
                vitalLen[regionIdx] = 0
                numInternalSpacesMax2[regionIdx] = 0
                containsOpp[regionIdx] = False

                vStart = vitalStart[regionIdx]
                initialVLen = 0
                for i in range(4):
                    adj = loc + self.adj[i]
                    if self.board[adj] == pla:
                        plaHead = self.group_head[adj]
                        alreadyPresent = False
                        for j in range(initialVLen):
                            if vitalForPlaHeadsLists[vStart+j] == plaHead:
                                alreadyPresent = True
                                break
                        if not alreadyPresent:
                            vitalForPlaHeadsLists[vStart+initialVLen] = plaHead
                            initialVLen += 1
                vitalLen[regionIdx] = initialVLen

                tailTarget = buildRegion(head, head, loc, regionIdx)
                nextEmptyOrOpp[head] = tailTarget
                vitalForPlaHeadsListsTotal += vitalLen[regionIdx]

        allPlaHeads = []
        for y in range(self.y_size):
            for x in range(self.x_size):
                loc = self.loc(x, y)
                if self.board[loc] == pla:
                    allPlaHeads.append(self.group_head[loc])
        allPlaHeads = list(set(allPlaHeads))
        numPlaHeads = len(allPlaHeads)

        plaHasBeenKilled = [False for i in range(numPlaHeads)]
        vitalCountByPlaHead = [0 for i in range(self.arrsize)]
        
        # --- Benson Iteration ---
        while True:
            for i in range(numPlaHeads):
                vitalCountByPlaHead[allPlaHeads[i]] = 0

            for i in range(numRegions):
                head = regionHeads[i]
                if bordersNonPassAlivePlaByHead[head]:
                    continue
                vStart = vitalStart[i]
                vLen = vitalLen[i]
                for j in range(vLen):
                    plaHead = vitalForPlaHeadsLists[vStart+j]
                    vitalCountByPlaHead[plaHead] += 1

            killedAnything = False
            for i in range(numPlaHeads):
                if plaHasBeenKilled[i]:
                    continue
                plaHead = allPlaHeads[i]
                if vitalCountByPlaHead[plaHead] < 2:
                    plaHasBeenKilled[i] = True
                    killedAnything = True
                    cur = plaHead
                    while True:
                        for j in range(4):
                            adj = cur + self.adj[j]
                            if self.board[adj] == Board.EMPTY or self.board[adj] == opp:
                                bordersNonPassAlivePlaByHead[regionHeadByLoc[adj]] = True
                        cur = self.group_next[cur]
                        if cur == plaHead:
                            break
            if not killedAnything:
                break

        # Record results
        for i in range(numPlaHeads):
            if not plaHasBeenKilled[i]:
                plaHead = allPlaHeads[i]
                cur = plaHead
                while True:
                    result[cur] = pla
                    cur = self.group_next[cur]
                    if cur == plaHead:
                        break

        for i in range(numRegions):
            head = regionHeads[i]
            shouldMark = numInternalSpacesMax2[i] <= 1 and atLeastOnePla and not bordersNonPassAlivePlaByHead[head]
            shouldMark = shouldMark or (safeBigTerritories and atLeastOnePla and not containsOpp[i] and not bordersNonPassAlivePlaByHead[head])
            shouldMark = shouldMark or (unsafeBigTerritories and atLeastOnePla and not containsOpp[i])

            if shouldMark:
                cur = head
                while True:
                    result[cur] = pla
                    cur = nextEmptyOrOpp[cur]
                    if cur == head:
                        break

    def calculateNonDameTouchingAreaHelper(self, basicArea, result):
        """Internal floodfill helper to identify areas not touching dame."""
        queue = [Board.PASS_LOC for i in range(self.arrsize)]
        isDameTouching = [False for i in range(self.arrsize)]
        queueHead = 0
        queueTail = 0

        ADJ = self.adj
        for y in range(self.y_size):
            for x in range(self.x_size):
                loc = self.loc(x, y)
                if basicArea[loc] != Board.EMPTY and not isDameTouching[loc]:
                    if any(self.board[loc+d] == Board.EMPTY and basicArea[loc+d] == Board.EMPTY for d in ADJ):
                        pla = basicArea[loc]
                        isDameTouching[loc] = True
                        queue[queueTail] = loc
                        queueTail += 1
                        while queueHead != queueTail:
                            nextLoc = queue[queueHead]
                            queueHead += 1
                            for d in ADJ:
                                adj = nextLoc + d
                                if basicArea[adj] == pla and not isDameTouching[adj]:
                                    isDameTouching[adj] = True
                                    queue[queueTail] = adj
                                    queueTail += 1

        queueHead = 0
        queueTail = 0
        for y in range(self.y_size):
            for x in range(self.x_size):
                loc = self.loc(x, y)
                if basicArea[loc] != Board.EMPTY and not isDameTouching[loc] and result[loc] != basicArea[loc]:
                    pla = basicArea[loc]
                    result[loc] = basicArea[loc]
                    queue[queueTail] = loc
                    queueTail += 1
                    while queueHead != queueTail:
                        nextLoc = queue[queueHead]
                        queueHead += 1
                        for d in ADJ:
                            adj = nextLoc + d
                            if basicArea[adj] == pla and result[adj] != basicArea[adj]:
                                result[adj] = basicArea[adj]
                                queue[queueTail] = adj
                                queueTail += 1

    # ─── Miscellaneous Utilities ────────────────────────────────────────

    def to_sgfpos_str(self):
        """Return a compact string representation for debug/storage."""
        out = []
        for y in range(self.y_size):
            row = []
            for x in range(self.x_size):
                v = self.board[self.loc(x, y)]
                row.append("X" if v == 1 else ("O" if v == 2 else "."))
            out.append("".join(row))
        return "/".join(out)

    def num_stones(self):
        """Return the total number of stones on the board."""
        return int(np.sum((self.board == Board.BLACK) | (self.board == Board.WHITE)))

    def pla_to_char(self, pla):
        """Convert player constant to human-readable character."""
        return "EBW#"[pla]

    def loc_to_str(self, loc):
        """Convert a 1D loc to GTP-style coordinate (e.g. 'E5')."""
        colstr = 'ABCDEFGHJKLMNOPQRST' # Note: 'I' is skipped in Go
        if loc == Board.PASS_LOC:
            return 'pass'
        return '%c%d' % (colstr[self.loc_x(loc)], self.y_size - self.loc_y(loc))
