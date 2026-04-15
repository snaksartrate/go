import sys
import numpy as np

import constants as C
from environment import Position, BitBoard
from moves import make_a_move, move_gen
from eval import get_best_move, static_eval

board_size = C.board_size
PASS_MOVE = np.uint16(board_size * board_size)


# ─── Display Helpers ────────────────────────────────────────────────

def display_board(position: Position):
    """Pretty-print the board state to the console."""
    board = position.bitboard
    symbols = {0: '.', 1: 'W', 2: 'B'}
    
    # Column headers
    col_labels = C.for_display_coords_x[:board_size]
    print(f"\n    {' '.join(col_labels)}")
    print(f"   +{'--' * board_size}+")
    
    for r in range(board_size):
        row_label = C.for_display_coords_y[r].rjust(2)
        row_chars = []
        for c in range(board_size):
            idx = r * board_size + c
            val = board.get(idx)
            row_chars.append(symbols[val])
        print(f"{row_label} | {' '.join(row_chars)} |")
    
    print(f"   +{'--' * board_size}+")
    
    # Status line
    turn = "Black" if position.black_to_play else "White"
    print(f"   Turn: {turn}  |  Black captures: {position.black_prisoners}  |  White captures: {position.white_prisoners}")
    print(f"   Eval: {static_eval(position):+.2f} (positive = Black ahead)")


def format_move(move: np.uint16) -> str:
    """Convert an engine move (uint16) to human-readable notation like 'E5'."""
    idx = int(move & 0x1FF)
    if idx == board_size * board_size:
        return "PASS"
    row = idx // board_size
    col = idx % board_size
    return f"{C.for_display_coords_x[col]}{C.for_display_coords_y[row]}"


def parse_move(text: str) -> np.uint16 | None:
    """Parse human input like 'E5' or 'pass' into a uint16 move index."""
    text = text.strip().upper()
    if text == "PASS":
        return PASS_MOVE
    if len(text) < 2:
        return None
    
    col_char = text[0]
    row_str = text[1:]
    
    if col_char not in C.for_display_coords_x:
        return None
    col = C.for_display_coords_x.index(col_char)
    
    if row_str not in C.for_display_coords_y:
        return None
    row = C.for_display_coords_y.index(row_str)
    
    idx = row * board_size + col
    return np.uint16(idx)


# ─── Core Engine Interface ──────────────────────────────────────────

def engine_move(position: Position, depth: int = 3) -> Position:
    """
    Given a position, compute the best move and return the resulting position.
    This is the function the GUI will call.
    """
    best_move = get_best_move(position, search_depth=depth)
    print(f"   Engine plays: {format_move(best_move)}")
    return make_a_move(position, best_move)


# ─── Game Modes ─────────────────────────────────────────────────────
# --- Game Modes -----------------------------------------------------

def self_play(depth: int = 3, max_moves: int = 200):
    """
    Engine plays against itself. 
    Useful for testing and watching the engine's behaviour.
    """
    print(f"\n=== Self-Play Mode (depth={depth}, board={board_size}x{board_size}) ===")
    
    position = Position(BitBoard(), True, None, move=None)
    move_number = 0
    consecutive_passes = 0
    
    display_board(position)
    
    while move_number < max_moves:
        move_number += 1
        turn = "Black" if position.black_to_play else "White"
        print(f"\n-- Move {move_number} ({turn}) --")
        
        position = engine_move(position, depth)
        display_board(position)
        
        # Check for game end (two consecutive passes)
        last_move_idx = int(position.previous_move & 0x1FF) if position.previous_move is not None else -1
        if last_move_idx == board_size * board_size:
            consecutive_passes += 1
            if consecutive_passes >= 2:
                print("\n══════════════════════════════")
                print("  GAME OVER — Both players passed.")
                final_score = static_eval(position)
                if final_score > 0:
                    print(f"  Result: Black wins by {final_score:.1f}")
                elif final_score < 0:
                    print(f"  Result: White wins by {-final_score:.1f}")
                else:
                    print("  Result: Draw")
                print("══════════════════════════════")
                return position
        else:
            consecutive_passes = 0
    
    print(f"\n  Game stopped after {max_moves} moves.")
    return position


def human_vs_engine(human_is_black: bool = True, depth: int = 3):
    """
    Interactive mode: human plays one colour, engine plays the other.
    Enter moves as coordinates like 'E5', or type 'pass'.
    Type 'quit' or 'exit' to stop.
    """
    human_colour = "Black" if human_is_black else "White"
    engine_colour = "White" if human_is_black else "Black"
    print(f"=== Human vs Engine (You: {human_colour}, Engine: {engine_colour}, depth={depth}) ===")
    print(f"    Board: {board_size}x{board_size} | Komi: {C.komi}")
    print(f"    Enter moves as coordinates (e.g. E5), 'pass', 'undo', or 'quit'.\n")
    
    position = Position(BitBoard(), True, None, move=None)
    move_number = 0
    consecutive_passes = 0
    
    display_board(position)
    
    while True:
        is_human_turn = (position.black_to_play == human_is_black)
        turn = "Black" if position.black_to_play else "White"
        move_number += 1
        
        if is_human_turn:
            # Human's turn
            while True:
                try:
                    user_input = input(f"\n  [{turn}] Your move: ").strip()
                except EOFError:
                    print("\n  Goodbye!")
                    return position
                
                if user_input.lower() in ('quit', 'exit', 'q'):
                    print("  Game ended by player.")
                    return position
                
                if user_input.lower() == 'undo':
                    # Undo both the engine's last move and the player's last move
                    if position.parent and position.parent.parent:
                        position = position.parent.parent
                        move_number -= 2
                        consecutive_passes = 0
                        print("  Undid last two moves.")
                        display_board(position)
                    else:
                        print("  Nothing to undo.")
                    continue
                
                move = parse_move(user_input)
                if move is None:
                    print(f"  Invalid input. Use format like 'E5' or 'pass'.")
                    continue
                
                # Validate move is legal
                move_idx = int(move & 0x1FF)
                if move_idx != board_size * board_size:
                    legal_moves = move_gen(position)
                    legal_indices = [int(m & 0x1FF) for m in legal_moves]
                    if move_idx not in legal_indices:
                        print(f"  Illegal move. Try again.")
                        continue
                
                position = make_a_move(position, move)
                print(f"   You play: {format_move(move)}")
                display_board(position)
                break
        else:
            # Engine's turn
            print(f"\n── Move {move_number} ({turn} — Engine thinking...) ──")
            position = engine_move(position, depth)
            display_board(position)
        
        # Check for game end
        last_move_idx = int(position.previous_move & 0x1FF) if position.previous_move is not None else -1
        if last_move_idx == board_size * board_size:
            consecutive_passes += 1
            if consecutive_passes >= 2:
                print("\n══════════════════════════════")
                print("  GAME OVER — Both players passed.")
                final_score = static_eval(position)
                if final_score > 0:
                    print(f"  Result: Black wins by {final_score:.1f}")
                elif final_score < 0:
                    print(f"  Result: White wins by {-final_score:.1f}")
                else:
                    print("  Result: Draw")
                print("══════════════════════════════")
                return position
        else:
            consecutive_passes = 0


# ─── Entry Point ────────────────────────────────────────────────────

def main():
    print(f"\n  +==================================+")
    print(f"  |        Go Engine v0.1            |")
    print(f"  |   {board_size}x{board_size} board  |  komi {C.komi}      |")
    print(f"  +==================================+\n")
    
    # Parse command-line arguments for mode selection
    mode = "menu"
    depth = 3
    
    for arg in sys.argv[1:]:
        if arg.startswith("--depth="):
            depth = int(arg.split("=")[1])
        elif arg == "--self-play":
            mode = "self"
        elif arg == "--play-black":
            mode = "play-black"
        elif arg == "--play-white":
            mode = "play-white"
    
    if mode == "self":
        self_play(depth=depth)
    elif mode == "play-black":
        human_vs_engine(human_is_black=True, depth=depth)
    elif mode == "play-white":
        human_vs_engine(human_is_black=False, depth=depth)
    else:
        # Interactive menu
        print("  Select mode:")
        print("    1) Self-play (engine vs engine)")
        print("    2) Play as Black (vs engine)")
        print("    3) Play as White (vs engine)")
        print()
        
        try:
            choice = input("  Choice [1/2/3]: ").strip()
        except EOFError:
            return
        
        depth_input = input(f"  Search depth [{depth}]: ").strip()
        if depth_input.isdigit():
            depth = int(depth_input)
        
        if choice == "1":
            self_play(depth=depth)
        elif choice == "2":
            human_vs_engine(human_is_black=True, depth=depth)
        elif choice == "3":
            human_vs_engine(human_is_black=False, depth=depth)
        else:
            print("  Invalid choice.")


if __name__ == "__main__":
    main()
