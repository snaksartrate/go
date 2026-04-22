import sys
import numpy as np

import constants as C
from board import Board
from environment import Position
from moves import move_gen
from eval import get_best_move, static_eval

# Cache board size locally for convenience.
board_size = C.board_size

# ─── Display Helpers ────────────────────────────────────────────────

def display_board(position: Position):
    """Pretty-print the board state to the console."""
    board = position.board
    # Map internal color constants to human-readable characters.
    symbols = {Board.EMPTY: '.', Board.WHITE: 'W', Board.BLACK: 'B'}
    
    # Column headers (A–J, skipping I)
    col_labels = [''] + C.for_display_coords_x[:board_size]
    print(f"\n   {'  '.join(col_labels)}")
    print(f"   +{'---' * board_size}+")
    
    for r in range(board_size):
        # r=0 is the top row, label should be '9'
        row_label = C.for_display_coords_y[r].rjust(2)
        row_chars = []
        for c in range(board_size):
            # board.loc(col, row) converts (x, y) to the internal array index.
            loc = board.loc(c, r)
            val = board.board[loc]
            row_chars.append(symbols.get(val, '?'))
        print(f"{row_label} | {'  '.join(row_chars)} |")
    
    print(f"   +{'---' * board_size}+")
    
    # Print game status below the board.
    turn = "Black" if position.black_to_play else "White"
    # Note: black_prisoners in new engine = stones Black captured FROM White
    print(f"   Turn: {turn}  |  Black dead: {position.black_prisoners}  |  White dead: {position.white_prisoners}")
    # Show the current heuristic evaluation (positive = Black is ahead).
    print(f"   Eval: {static_eval(position):+.2f} (positive = Black ahead)")


def format_move(move: int) -> str:
    """Convert an engine loc to human-readable notation like 'E5'."""
    if move == Board.PASS_LOC:
        return "PASS"
    
    # Create a temporary board to access the loc_x / loc_y helpers.
    # This avoids keeping a global board just for coordinate conversion.
    temp_board = Board(board_size)
    x = temp_board.loc_x(move)
    y = temp_board.loc_y(move)
    
    # Sanity check — if the loc is out of range, report an error.
    if x < 0 or x >= board_size or y < 0 or y >= board_size:
        return f"ERR({move})"
        
    return f"{C.for_display_coords_x[x]}{C.for_display_coords_y[y]}"


def parse_move(text: str) -> int | None:
    """Parse human input like 'E5' or 'pass' into a KataGo loc."""
    text = text.strip().upper()
    if text == "PASS":
        return Board.PASS_LOC
    # A valid move must be at least 2 characters (one column + one or more row digits).
    if len(text) < 2:
        return None
    
    col_char = text[0]       # e.g. 'E'
    row_str = text[1:]       # e.g. '5'
    
    # Validate column letter against the known labels (A–J, no I).
    if col_char not in C.for_display_coords_x:
        return None
    col = C.for_display_coords_x.index(col_char)
    
    # Validate row number against known labels ('9' down to '1').
    if row_str not in C.for_display_coords_y:
        return None
    row = C.for_display_coords_y.index(row_str)
    
    # Convert (col, row) display coordinates to the engine's internal loc integer.
    temp_board = Board(board_size)
    return temp_board.loc(col, row)


# ─── Core Engine Interface ──────────────────────────────────────────

def engine_move(position: Position, depth: int = 5) -> None:
    """
    Given a position, compute the best move and push it.
    """
    # Ask the search algorithm (iterative deepening + alpha-beta) for the best move.
    best_move = get_best_move(position, search_depth=depth)
    print(f"   Engine plays: {format_move(best_move)}")
    # Apply the chosen move to the live position.
    position.push(best_move)


# ─── Game Modes ─────────────────────────────────────────────────────

def self_play(depth: int = 5, max_moves: int = 200):
    """
    Engine plays against itself. 
    """
    print(f"\n=== Self-Play Mode (depth={depth}, board={board_size}x{board_size}) ===")
    
    position = Position()
    move_number = 0
    
    display_board(position)
    
    while move_number < max_moves:
        move_number += 1
        turn = "Black" if position.black_to_play else "White"
        print(f"\n-- Move {move_number} ({turn}) --")
        
        engine_move(position, depth)
        display_board(position)
        
        # In Go, the game ends when both players pass on consecutive turns.
        if position.pass_count >= 2:
            print("\n══════════════════════════════")
            print("  GAME OVER — Both players passed.")
            from eval import final_score
            b_score, w_score = final_score(position)
            print(f"  Final Score: Black {b_score:.1f}, White {w_score:.1f}")
            if b_score > w_score:
                print(f"  Result: Black wins by {b_score - w_score:.1f}")
            elif w_score > b_score:
                print(f"  Result: White wins by {w_score - b_score:.1f}")
            else:
                print("  Result: Draw")
            print("══════════════════════════════")
            return position
            
    print(f"\n  Game stopped after {max_moves} moves.")
    return position


def human_vs_engine(human_is_black: bool = True, depth: int = 5):
    """
    Interactive mode: human plays one colour, engine plays the other.
    """
    human_colour = "Black" if human_is_black else "White"
    engine_colour = "White" if human_is_black else "Black"
    print(f"=== Human vs Engine (You: {human_colour}, Engine: {engine_colour}, depth={depth}) ===")
    print(f"    Board: {board_size}x{board_size} | Komi: {C.komi}")
    print(f"    Enter moves as coordinates (e.g. E5), 'pass', 'undo', or 'quit'.\n")
    
    position = Position()
    move_number = 0
    
    if not human_is_black:
        # If the human chose White, the engine plays first as Black.
        move_number += 1
        print(f"\n── Move {move_number} (Black — Engine thinking...) ──")
        engine_move(position, depth)
        
    display_board(position)
    
    while True:
        # Determine whether it's the human's turn or the engine's turn.
        is_human_turn = (position.black_to_play == human_is_black)
        turn = "Black" if position.black_to_play else "White"
        
        if is_human_turn:
            move_number += 1
            while True:
                try:
                    user_input = input(f"\n  [{turn}] Your move: ").strip()
                except EOFError:
                    # Handle non-interactive environments (e.g. piped input).
                    print("\n  Goodbye!")
                    return position
                
                if user_input.lower() in ('quit', 'exit', 'q'):
                    print("  Game ended by player.")
                    return position
                
                if user_input.lower() == 'undo':
                    # Undo both the human's last move and the engine's response.
                    if len(position.move_history) >= 2:
                        position.pop() # engine's move
                        position.pop() # player's move
                        move_number -= 2
                        print("  Undid last two moves.")
                        display_board(position)
                    else:
                        print("  Nothing to undo.")
                    continue
                
                move = parse_move(user_input)
                if move is None:
                    print(f"  Invalid input. Use format like 'E5' or 'pass'.")
                    continue
                
                # Legality check (simple rules: occupied, suicide, simple ko)
                if not position.board.would_be_legal(position.current_player, move):
                    print(f"  Illegal move. Try again.")
                    continue
                
                # Superko check (positional: no repeated board positions)
                if position.would_violate_superko(move):
                    print(f"  Illegal move (superko). Try again.")
                    continue
                
                position.push(move)
                print(f"   You play: {format_move(move)}")
                display_board(position)
                break
        else:
            # Engine's turn — let the search find and play the best move.
            move_number += 1
            print(f"\n── Move {move_number} ({turn} — Engine thinking...) ──")
            engine_move(position, depth)
            display_board(position)
        
        # Check for game end after every move.
        if position.pass_count >= 2:
            print("\n══════════════════════════════")
            print("  GAME OVER — Both players passed.")
            from eval import final_score
            b_score, w_score = final_score(position)
            print(f"  Final Score: Black {b_score:.1f}, White {w_score:.1f}")
            if b_score > w_score:
                print(f"  Result: Black wins by {b_score - w_score:.1f}")
            elif w_score > b_score:
                print(f"  Result: White wins by {w_score - b_score:.1f}")
            else:
                print("  Result: Draw")
            print("══════════════════════════════")
            return position


def main():
    print(f"\n  +==================================+")
    print(f"  |        Go Engine v0.2            |")
    print(f"  |   {board_size}x{board_size} board  |  komi {C.komi}      |")
    print(f"  +==================================+\n")
    
    # Default settings — can be overridden by command-line arguments.
    mode = "menu"
    depth = 5
    
    # Parse command-line arguments for non-interactive usage.
    # Example: python main.py --self-play --depth=6
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
        # No command-line mode given — show an interactive menu.
        print("  Select mode:")
        print("    1) Self-play (engine vs engine)")
        print("    2) Play as Black (vs engine)")
        print("    3) Play as White (vs engine)")
        print()
        
        try:
            choice = input("  Choice [1/2/3]: ").strip()
        except EOFError:
            return
        
        # Allow the user to override the default search depth.
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


# Standard Python entry point — only runs when called directly, not when imported.
if __name__ == "__main__":
    main()
