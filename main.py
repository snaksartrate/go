"""
Go 9x9  –  Player vs Player  with Time Control
===============================================
Layers
------
  GoLogic        – pure rules engine (no Qt dependency)
                   captures · Ko · pass · territory scoring
  TimeControl    – tracks per-player countdown, emits timeout signal
  ClockWidget    – single player's clock face (drawn with QPainter)
  GoBoardWidget  – Qt canvas: grid, stones, last-move marker, territory overlay
  ScoreOverlay   – end-of-game result panel (child of the board widget)
  GoWindow       – main window: clocks, labels, Pass / New-Game buttons
"""

import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush,
    QRadialGradient, QLinearGradient, QFont,
)
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

BOARD_SIZE    = 9
CELL          = 56
MARGIN        = 48
STONE_RADIUS  = 23
SNAP_RADIUS   = CELL // 2
KOMI          = 6.5

DEFAULT_TIME  = 5 * 60   # 5 minutes per player, in seconds
WARNING_SECS  = 30       # clock turns red below this threshold

NEIGHBORS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
HOSHI     = [(2, 2), (6, 2), (4, 4), (2, 6), (6, 6)]

# ── palette ───────────────────────────────────────────────────────────────────
C_BG_TOP      = QColor("#d4a84b")
C_BG_BOT      = QColor("#b8892f")
C_LINE        = QColor("#7a5c1e")
C_HOSHI       = QColor("#5a3e10")

C_BLACK_HI    = QColor("#6b6b6b")
C_BLACK_BASE  = QColor("#1a1a1a")
C_BLACK_SHAD  = QColor("#000000")

C_WHITE_HI    = QColor("#ffffff")
C_WHITE_BASE  = QColor("#e8e8e8")
C_WHITE_SHAD  = QColor("#aaaaaa")

C_LAST_B      = QColor("#7ecfff")
C_LAST_W      = QColor("#e05050")

C_TERR_B      = QColor(30,  30,  30,  110)
C_TERR_W      = QColor(230, 230, 230, 110)

# clock widget colours
C_CLOCK_ACTIVE_BG   = QColor("#2e1a04")
C_CLOCK_INACTIVE_BG = QColor("#1a0f02")
C_CLOCK_BORDER_ACT  = QColor("#c8a84a")
C_CLOCK_BORDER_INACT= QColor("#4a3810")
C_CLOCK_TIME_NORMAL = QColor("#e8c87a")
C_CLOCK_TIME_WARN   = QColor("#ff4444")
C_CLOCK_LABEL_ACT   = QColor("#c8a84a")
C_CLOCK_LABEL_INACT = QColor("#5a4820")


# ═══════════════════════════════════════════════════════════════════════════════
# Pixel ↔ Grid helpers
# ═══════════════════════════════════════════════════════════════════════════════

def grid_to_pixel(col: int, row: int) -> QPoint:
    return QPoint(MARGIN + col * CELL, MARGIN + row * CELL)


def pixel_to_grid(px: int, py: int):
    col = round((px - MARGIN) / CELL)
    row = round((py - MARGIN) / CELL)
    if not (0 <= col < BOARD_SIZE and 0 <= row < BOARD_SIZE):
        return None
    cx = grid_to_pixel(col, row).x()
    cy = grid_to_pixel(col, row).y()
    if (px - cx) ** 2 + (py - cy) ** 2 <= SNAP_RADIUS ** 2:
        return col, row
    return None


def board_to_tuple(board: list) -> tuple:
    return tuple(cell for row in board for cell in row)


def fmt_time(secs: int) -> str:
    """Format seconds as  M:SS"""
    secs = max(0, secs)
    return f"{secs // 60}:{secs % 60:02d}"


# ═══════════════════════════════════════════════════════════════════════════════
# GoLogic  –  pure rules engine  (no Qt dependency)
# ═══════════════════════════════════════════════════════════════════════════════

class GoLogic:
    """
    Board:  board[row][col]  →  None | 'B' | 'W'

    Public API
    ----------
    try_place(col, row)  -> bool
    pass_turn()          -> bool
    end_by_timeout(loser)-> None   force-end the game, score by captures only
    is_occupied(c, r)    -> bool
    stones_dict()        -> {(col,row): colour}
    """

    def __init__(self, size: int = BOARD_SIZE):
        self.size               = size
        self.board: list        = [[None] * size for _ in range(size)]
        self.current_player     = "B"
        self.captures: dict     = {"B": 0, "W": 0}
        self.ko_state           = None
        self.consecutive_passes = 0
        self.game_over          = False
        self.last_move          = None
        self.territory: dict    = {}
        self.final_score        = None

    # ── internals ─────────────────────────────────────────────────────────────

    def in_bounds(self, c, r):
        return 0 <= c < self.size and 0 <= r < self.size

    def _nbrs(self, c, r):
        for dc, dr in NEIGHBORS:
            nc, nr = c + dc, r + dr
            if self.in_bounds(nc, nr):
                yield nc, nr

    def _group(self, c, r):
        colour = self.board[r][c]
        if colour is None:
            return set()
        seen, q = set(), [(c, r)]
        while q:
            cc, rr = q.pop()
            if (cc, rr) in seen:
                continue
            seen.add((cc, rr))
            for nc, nr in self._nbrs(cc, rr):
                if (nc, nr) not in seen and self.board[nr][nc] == colour:
                    q.append((nc, nr))
        return seen

    def _liberties(self, group):
        libs = set()
        for c, r in group:
            for nc, nr in self._nbrs(c, r):
                if self.board[nr][nc] is None:
                    libs.add((nc, nr))
        return libs

    def _snapshot(self):
        return board_to_tuple(self.board)

    def _remove_dead(self, c, r, colour):
        removed, checked = [], set()
        for nc, nr in self._nbrs(c, r):
            if self.board[nr][nc] != colour or (nc, nr) in checked:
                continue
            grp = self._group(nc, nr)
            checked |= grp
            if not self._liberties(grp):
                for gc, gr in grp:
                    self.board[gr][gc] = None
                removed.extend(grp)
        return removed

    # ── public API ────────────────────────────────────────────────────────────

    def is_occupied(self, c, r):
        return self.board[r][c] is not None

    def try_place(self, col, row):
        if self.game_over or self.is_occupied(col, row):
            return False
        player   = self.current_player
        opponent = "W" if player == "B" else "B"
        pre      = self._snapshot()

        self.board[row][col] = player
        captured = self._remove_dead(col, row, opponent)

        grp = self._group(col, row)
        if not self._liberties(grp):                    # suicide
            self.board[row][col] = None
            for gc, gr in captured:
                self.board[gr][gc] = opponent
            return False

        if self._snapshot() == self.ko_state:           # Ko
            self.board[row][col] = None
            for gc, gr in captured:
                self.board[gr][gc] = opponent
            return False

        self.captures[player]  += len(captured)
        self.ko_state           = pre if len(captured) == 1 else None
        self.consecutive_passes = 0
        self.last_move          = (col, row)
        self.current_player     = opponent
        return True

    def pass_turn(self):
        if self.game_over:
            return False
        self.consecutive_passes += 1
        self.ko_state  = None
        self.last_move = None
        if self.consecutive_passes >= 2:
            self.game_over = True
            self._compute_score()
        else:
            self.current_player = "W" if self.current_player == "B" else "B"
        return True

    def end_by_timeout(self, loser: str):
        """Force game end; winner is the opponent of *loser*."""
        if self.game_over:
            return
        self.game_over = True
        winner_name = "White" if loser == "B" else "Black"
        # Score by captures only (no territory count mid-game)
        sb = self.captures["B"]
        sw = self.captures["W"] + KOMI
        self.territory  = {}
        self.final_score = dict(
            terr_b=0, terr_w=0,
            cap_b=self.captures["B"], cap_w=self.captures["W"],
            score_b=sb, score_w=sw,
            winner=winner_name,
            timeout=True,
            loser_name="Black" if loser == "B" else "White",
        )

    # ── scoring (double-pass) ─────────────────────────────────────────────────

    def _compute_score(self):
        self.territory = self._flood_territory()
        tb = sum(1 for v in self.territory.values() if v == "B")
        tw = sum(1 for v in self.territory.values() if v == "W")
        sb = tb + self.captures["B"]
        sw = tw + self.captures["W"] + KOMI
        self.final_score = dict(
            terr_b=tb, terr_w=tw,
            cap_b=self.captures["B"], cap_w=self.captures["W"],
            score_b=sb, score_w=sw,
            winner="Black" if sb > sw else ("White" if sw > sb else "Draw"),
            timeout=False,
        )

    def _flood_territory(self):
        visited, territory = set(), {}
        for sr in range(self.size):
            for sc in range(self.size):
                if self.board[sr][sc] is not None or (sc, sr) in visited:
                    continue
                region, borders, seen, q = [], set(), set(), [(sc, sr)]
                while q:
                    c, r = q.pop()
                    if (c, r) in seen:
                        continue
                    seen.add((c, r)); region.append((c, r))
                    for nc, nr in self._nbrs(c, r):
                        cell = self.board[nr][nc]
                        if cell is None:
                            if (nc, nr) not in seen:
                                q.append((nc, nr))
                        else:
                            borders.add(cell)
                visited |= set(region)
                if len(borders) == 1:
                    owner = next(iter(borders))
                    for pos in region:
                        territory[pos] = owner
        return territory

    def stones_dict(self):
        out = {}
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] is not None:
                    out[(c, r)] = self.board[r][c]
        return out


# ═══════════════════════════════════════════════════════════════════════════════
# TimeControl  –  dual countdown, QTimer-driven
# ═══════════════════════════════════════════════════════════════════════════════

class TimeControl(QObject):
    """
    Manages two independent countdowns (one per player).

    Signals
    -------
    tick(player)      – emitted every second for the active player
    timeout(player)   – emitted when a player's clock reaches zero
    """

    tick    = pyqtSignal(str)   # 'B' or 'W'
    timeout = pyqtSignal(str)   # player who ran out

    def __init__(self, seconds: int = DEFAULT_TIME, parent=None):
        super().__init__(parent)
        self._total   = seconds
        self._secs    = {"B": seconds, "W": seconds}
        self._active  = None          # which player's clock is running
        self._running = False

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    # ── public ────────────────────────────────────────────────────────────────

    def start(self, player: str):
        """Begin (or switch to) *player*'s clock."""
        self._active  = player
        self._running = True
        self._timer.start()

    def switch(self, player: str):
        """Hand the clock to *player* (call after every move / pass)."""
        self._active = player
        if not self._running:
            self._timer.start()
            self._running = True

    def stop(self):
        """Pause both clocks (game over)."""
        self._timer.stop()
        self._running = False

    def reset(self, seconds: int = DEFAULT_TIME):
        """Full reset for a new game."""
        self.stop()
        self._total  = seconds
        self._secs   = {"B": seconds, "W": seconds}
        self._active = None

    def remaining(self, player: str) -> int:
        return self._secs[player]

    def active_player(self) -> str:
        return self._active

    # ── private ───────────────────────────────────────────────────────────────

    def _on_tick(self):
        if self._active is None:
            return
        self._secs[self._active] = max(0, self._secs[self._active] - 1)
        self.tick.emit(self._active)
        if self._secs[self._active] == 0:
            self._timer.stop()
            self._running = False
            self.timeout.emit(self._active)


# ═══════════════════════════════════════════════════════════════════════════════
# ClockWidget  –  single player's clock face
# ═══════════════════════════════════════════════════════════════════════════════

class ClockWidget(QWidget):
    """
    Displays one player's remaining time.
    Highlights when it is that player's turn; turns red when time is low.
    """

    def __init__(self, player: str, label: str, parent=None):
        super().__init__(parent)
        self.player   = player     # 'B' or 'W'
        self.label    = label      # display name e.g. "Black ●"
        self.secs     = DEFAULT_TIME
        self.active   = False
        self.setFixedSize(140, 72)

    def set_time(self, secs: int):
        self.secs = secs
        self.update()

    def set_active(self, active: bool):
        self.active = active
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # background
        bg  = C_CLOCK_ACTIVE_BG if self.active else C_CLOCK_INACTIVE_BG
        bdr = C_CLOCK_BORDER_ACT if self.active else C_CLOCK_BORDER_INACT
        p.setBrush(QBrush(bg))
        p.setPen(QPen(bdr, 1.5))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)

        # player label
        lbl_col = C_CLOCK_LABEL_ACT if self.active else C_CLOCK_LABEL_INACT
        p.setPen(lbl_col)
        p.setFont(QFont("Georgia", 10))
        p.drawText(self.rect().adjusted(0, 6, 0, -36), Qt.AlignHCenter, self.label)

        # time digits
        warn    = self.secs <= WARNING_SECS
        time_col = C_CLOCK_TIME_WARN if (warn and self.active) else C_CLOCK_TIME_NORMAL
        p.setPen(time_col)
        bold = QFont("Georgia", 20, QFont.Bold)
        bold.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        p.setFont(bold)
        p.drawText(self.rect().adjusted(0, 22, 0, -4), Qt.AlignCenter, fmt_time(self.secs))


# ═══════════════════════════════════════════════════════════════════════════════
# GoBoardWidget  –  Qt canvas
# ═══════════════════════════════════════════════════════════════════════════════

class GoBoardWidget(QWidget):

    def __init__(self, logic: GoLogic, on_move):
        super().__init__()
        self.logic   = logic
        self.on_move = on_move
        board_px = MARGIN * 2 + (BOARD_SIZE - 1) * CELL
        self.setFixedSize(board_px, board_px)
        self.setMouseTracking(True)
        self.hover = None

    def mouseMoveEvent(self, event):
        hit = pixel_to_grid(event.x(), event.y())
        if hit != self.hover:
            self.hover = hit
            self.update()

    def leaveEvent(self, _event):
        self.hover = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.logic.game_over:
            return
        hit = pixel_to_grid(event.x(), event.y())
        if hit and self.logic.try_place(*hit):
            self.on_move()
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._draw_background(p)
        self._draw_grid(p)
        self._draw_hoshi(p)
        if self.logic.game_over:
            self._draw_territory(p)
        self._draw_hover(p)
        self._draw_stones(p)

    def _draw_background(self, p):
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, C_BG_TOP)
        grad.setColorAt(1.0, C_BG_BOT)
        p.fillRect(self.rect(), grad)

    def _draw_grid(self, p):
        p.setPen(QPen(C_LINE, 1.4, Qt.SolidLine))
        last = BOARD_SIZE - 1
        for i in range(BOARD_SIZE):
            p.drawLine(grid_to_pixel(0, i),    grid_to_pixel(last, i))
            p.drawLine(grid_to_pixel(i, 0),    grid_to_pixel(i, last))

    def _draw_hoshi(self, p):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(C_HOSHI))
        for col, row in HOSHI:
            p.drawEllipse(grid_to_pixel(col, row), 4, 4)

    def _draw_territory(self, p):
        sq = CELL // 4
        p.setPen(Qt.NoPen)
        for (col, row), owner in self.logic.territory.items():
            c = grid_to_pixel(col, row)
            p.setBrush(QBrush(C_TERR_B if owner == "B" else C_TERR_W))
            p.drawRect(c.x() - sq, c.y() - sq, sq * 2, sq * 2)

    def _draw_hover(self, p):
        if self.hover is None or self.logic.game_over:
            return
        col, row = self.hover
        if self.logic.is_occupied(col, row):
            return
        color = (QColor(20, 20, 20, 75)
                 if self.logic.current_player == "B"
                 else QColor(240, 240, 240, 95))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawEllipse(grid_to_pixel(col, row), STONE_RADIUS, STONE_RADIUS)

    def _draw_stones(self, p):
        last = self.logic.last_move
        for (col, row), colour in self.logic.stones_dict().items():
            center = grid_to_pixel(col, row)
            self._draw_stone(p, center, colour)
            if (col, row) == last:
                self._draw_last_move_ring(p, center, colour)

    def _draw_stone(self, p, center, player):
        r, cx, cy = STONE_RADIUS, center.x(), center.y()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 70)))
        p.drawEllipse(QPoint(cx + 2, cy + 3), r, r)
        grad = QRadialGradient(cx - r * 0.3, cy - r * 0.35, r * 1.4)
        if player == "B":
            grad.setColorAt(0.0, C_BLACK_HI)
            grad.setColorAt(0.5, C_BLACK_BASE)
            grad.setColorAt(1.0, C_BLACK_SHAD)
        else:
            grad.setColorAt(0.0, C_WHITE_HI)
            grad.setColorAt(0.5, C_WHITE_BASE)
            grad.setColorAt(1.0, C_WHITE_SHAD)
        p.setBrush(QBrush(grad))
        p.drawEllipse(center, r, r)

    def _draw_last_move_ring(self, p, center, player):
        ring_r = STONE_RADIUS // 3
        p.setPen(QPen(C_LAST_B if player == "B" else C_LAST_W, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(center, ring_r, ring_r)


# ═══════════════════════════════════════════════════════════════════════════════
# ScoreOverlay
# ═══════════════════════════════════════════════════════════════════════════════

class ScoreOverlay(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: rgba(15, 8, 2, 218);
                border: 1px solid #c8a84a;
                border-radius: 10px;
            }
            QLabel { background: transparent; border: none; }
        """)
        self.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(6)

        self.winner_label = QLabel()
        self.winner_label.setAlignment(Qt.AlignCenter)
        self.winner_label.setFont(QFont("Georgia", 18, QFont.Bold))
        self.winner_label.setStyleSheet("color: #f0d060;")

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#c8a84a; max-height:1px; border:none;")

        self.detail_label = QLabel()
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setFont(QFont("Georgia", 11))
        self.detail_label.setStyleSheet("color: #ddc880;")

        self.komi_label = QLabel(f"(Komi {KOMI} awarded to White)")
        self.komi_label.setAlignment(Qt.AlignCenter)
        self.komi_label.setFont(QFont("Georgia", 10))
        self.komi_label.setStyleSheet("color: #aa9055;")

        for w in (self.winner_label, sep, self.detail_label, self.komi_label):
            layout.addWidget(w)

    def show_result(self, score: dict):
        sb, sw, winner = score["score_b"], score["score_w"], score["winner"]

        if score.get("timeout"):
            loser = score["loser_name"]
            sym   = "○" if winner == "White" else "●"
            self.winner_label.setText(f"{sym}  {winner} wins!")
            self.detail_label.setText(
                f"{loser} ran out of time.\n"
                f"●  Black captures: {score['cap_b']}\n"
                f"○  White captures: {score['cap_w']}"
            )
            self.komi_label.setText("")
        else:
            if winner == "Draw":
                self.winner_label.setText("Draw!")
            else:
                sym = "●" if winner == "Black" else "○"
                self.winner_label.setText(f"{sym}  {winner} wins  by  {abs(sb - sw):.1f}")
            self.detail_label.setText(
                f"●  Black:  {score['terr_b']} territory  +  {score['cap_b']} captures  =  {sb}\n"
                f"○  White:  {score['terr_w']} territory  +  {score['cap_w']} captures  +  {KOMI} komi  =  {sw}"
            )
            self.komi_label.setText(f"(Komi {KOMI} awarded to White)")

        self.show()
        self.adjustSize()


# ═══════════════════════════════════════════════════════════════════════════════
# GoWindow  –  application shell
# ═══════════════════════════════════════════════════════════════════════════════

class GoWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Go  ·  9×9  —  Player vs Player")
        self.setStyleSheet("background: #1e1008;")

        self.logic = GoLogic()
        self.clock = TimeControl(DEFAULT_TIME, parent=self)
        self.clock.tick.connect(self._on_tick)
        self.clock.timeout.connect(self._on_timeout)

        self._build_ui()
        self._refresh_ui()
        self.setFixedSize(self.sizeHint())
        self._centre_overlay()

        # Black moves first – start their clock
        self.clock.start("B")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(8)

        # ── clocks row ────────────────────────────────────────────────────────
        self.clock_b = ClockWidget("B", "Black  ●")
        self.clock_w = ClockWidget("W", "White  ○")
        self.clock_b.set_active(True)
        self.clock_w.set_active(False)

        clocks_row = QHBoxLayout()
        clocks_row.setSpacing(0)
        clocks_row.addStretch()
        clocks_row.addWidget(self.clock_b)
        clocks_row.addSpacing(20)
        clocks_row.addWidget(self.clock_w)
        clocks_row.addStretch()

        # ── turn / capture labels ─────────────────────────────────────────────
        self.turn_label = QLabel()
        self.turn_label.setAlignment(Qt.AlignCenter)
        self.turn_label.setFont(QFont("Georgia", 13))
        self.turn_label.setStyleSheet("color: #e8c87a; letter-spacing: 2px;")

        self.cap_label = QLabel()
        self.cap_label.setAlignment(Qt.AlignCenter)
        self.cap_label.setFont(QFont("Georgia", 11))
        self.cap_label.setStyleSheet("color: #c8a84a; letter-spacing: 1px;")

        # ── board ─────────────────────────────────────────────────────────────
        self.board_widget  = GoBoardWidget(self.logic, self._on_move)
        self.score_overlay = ScoreOverlay(self.board_widget)

        # ── buttons ───────────────────────────────────────────────────────────
        btn_style = """
            QPushButton {
                background: #3a2508; color: #e8c87a;
                border: 1px solid #c8a84a; border-radius: 5px;
                padding: 5px 22px; font-family: Georgia; font-size: 12px;
            }
            QPushButton:hover    { background: #5a3a10; }
            QPushButton:pressed  { background: #7a5020; }
            QPushButton:disabled { color: #7a6030; border-color: #7a6030; }
        """
        self.pass_btn = QPushButton("Pass")
        self.pass_btn.setStyleSheet(btn_style)
        self.pass_btn.clicked.connect(self._on_pass)

        self.new_btn = QPushButton("New Game")
        self.new_btn.setStyleSheet(btn_style)
        self.new_btn.clicked.connect(self._on_new_game)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.addStretch()
        btn_row.addWidget(self.pass_btn)
        btn_row.addWidget(self.new_btn)
        btn_row.addStretch()

        outer.addLayout(clocks_row)
        outer.addSpacing(2)
        outer.addWidget(self.turn_label)
        outer.addWidget(self.cap_label)
        outer.addWidget(self.board_widget, alignment=Qt.AlignCenter)
        outer.addLayout(btn_row)

        self.setCentralWidget(container)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_move(self):
        """Called after every valid stone placement."""
        self.clock.switch(self.logic.current_player)
        self._sync_clock_faces()
        self._refresh_ui()
        if self.logic.game_over:
            self._end_game()

    def _on_pass(self):
        if self.logic.game_over:
            return
        self.logic.pass_turn()
        self.board_widget.update()
        if not self.logic.game_over:
            self.clock.switch(self.logic.current_player)
            self._sync_clock_faces()
        self._refresh_ui()
        if self.logic.game_over:
            self._end_game()

    def _on_new_game(self):
        self.clock.reset(DEFAULT_TIME)
        self.logic = GoLogic()
        self.board_widget.logic = self.logic
        self.score_overlay.hide()
        self.board_widget.update()
        self.clock_b.set_time(DEFAULT_TIME)
        self.clock_w.set_time(DEFAULT_TIME)
        self.clock_b.set_active(True)
        self.clock_w.set_active(False)
        self._refresh_ui()
        self.clock.start("B")

    # ── clock slots ───────────────────────────────────────────────────────────

    def _on_tick(self, player: str):
        """Fired every second by TimeControl for the active player."""
        secs = self.clock.remaining(player)
        if player == "B":
            self.clock_b.set_time(secs)
        else:
            self.clock_w.set_time(secs)

    def _on_timeout(self, loser: str):
        """A player ran out of time – end the game immediately."""
        self.logic.end_by_timeout(loser)
        self.board_widget.update()
        self._refresh_ui()
        self._end_game()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _sync_clock_faces(self):
        """Highlight the clock of whoever is currently to move."""
        active = self.logic.current_player
        self.clock_b.set_active(active == "B")
        self.clock_w.set_active(active == "W")

    def _refresh_ui(self):
        if self.logic.game_over:
            self.turn_label.setText("Game Over")
            self.pass_btn.setEnabled(False)
            self.clock_b.set_active(False)
            self.clock_w.set_active(False)
        else:
            p   = self.logic.current_player
            sym = "●" if p == "B" else "○"
            nm  = "Black" if p == "B" else "White"
            sfx = "  —  opponent passed" if self.logic.consecutive_passes == 1 else ""
            self.turn_label.setText(f"{sym}  {nm}'s turn{sfx}")
            self.pass_btn.setEnabled(True)

        c = self.logic.captures
        self.cap_label.setText(f"Captures   ●  {c['B']}     ○  {c['W']}")

    def _end_game(self):
        self.clock.stop()
        self.score_overlay.show_result(self.logic.final_score)
        self._centre_overlay()
        self._refresh_ui()

    def _centre_overlay(self):
        bw, ov = self.board_widget, self.score_overlay
        ov.adjustSize()
        ov.move(
            (bw.width()  - ov.width())  // 2,
            (bw.height() - ov.height()) // 2,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Go  9×9")
    win = GoWindow()
    win.show()
    sys.exit(app.exec_())