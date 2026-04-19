import sys
import numpy as np

import constants as C
from board import Board
from environment import Position
from moves import move_gen
from eval import get_best_move, static_eval

board_size = C.board_size

# ─── Display Helpers ────────────────────────────────────────────────

def display_board(position: Position):
    """Pretty-print the board state to the console."""
    board = position.board
    symbols = {Board.EMPTY: '.', Board.WHITE: 'W', Board.BLACK: 'B'}
    
    # Column headers
    col_labels = [''] + C.for_display_coords_x[:board_size]
    print(f"\n   {'  '.join(col_labels)}")
    print(f"   +{'---' * board_size}+")
    
    for r in range(board_size):
        # r=0 is the top row, label should be '9'
        row_label = C.for_display_coords_y[r].rjust(2)
        row_chars = []
        for c in range(board_size):
            loc = board.loc(c, r)
            val = board.board[loc]
            row_chars.append(symbols.get(val, '?'))
        print(f"{row_label} | {'  '.join(row_chars)} |")
    
    print(f"   +{'---' * board_size}+")
    
    # Status line
    turn = "Black" if position.black_to_play else "White"
    # Note: black_prisoners in new engine = stones Black captured FROM White
    print(f"   Turn: {turn}  |  Black caps: {position.black_prisoners}  |  White caps: {position.white_prisoners}")
    print(f"   Eval: {static_eval(position):+.2f} (positive = Black ahead)")


def format_move(move: int) -> str:
    """Convert an engine loc to human-readable notation like 'E5'."""
    if move == Board.PASS_LOC:
        return "PASS"
    
    # We use a dummy board to get the mapping
    temp_board = Board(board_size)
    x = temp_board.loc_x(move)
    y = temp_board.loc_y(move)
    
    if x < 0 or x >= board_size or y < 0 or y >= board_size:
        return f"ERR({move})"
        
    return f"{C.for_display_coords_x[x]}{C.for_display_coords_y[y]}"


def parse_move(text: str) -> int | None:
    """Parse human input like 'E5' or 'pass' into a KataGo loc."""
    text = text.strip().upper()
    if text == "PASS":
        return Board.PASS_LOC
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
    
    temp_board = Board(board_size)
    return temp_board.loc(col, row)


# ─── Core Engine Interface ──────────────────────────────────────────

def engine_move(position: Position, depth: int = 5) -> None:
    """
    Given a position, compute the best move and push it.
    """
    best_move = get_best_move(position, search_depth=depth)
    print(f"   Engine plays: {format_move(best_move)}")
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
        
        # Check for game end
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
        # Engine starts if human is White
        move_number += 1
        print(f"\n── Move {move_number} (Black — Engine thinking...) ──")
        engine_move(position, depth)
        
    display_board(position)
    
    while True:
        is_human_turn = (position.black_to_play == human_is_black)
        turn = "Black" if position.black_to_play else "White"
        
        if is_human_turn:
            move_number += 1
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
                
                # Legality check
                if not position.board.would_be_legal(position.current_player, move):
                    print(f"  Illegal move. Try again.")
                    continue
                
                position.push(move)
                print(f"   You play: {format_move(move)}")
                display_board(position)
                break
        else:
            # Engine's turn
            move_number += 1
            print(f"\n── Move {move_number} ({turn} — Engine thinking...) ──")
            engine_move(position, depth)
            display_board(position)
        
        # Check for game end
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
    
    mode = "menu"
    depth = 5
    
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
