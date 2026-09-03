import os
import chess
import chess.engine


class ChessGame:
    """
    Stockfish-backed chess game.

    Difficulty is controlled through the depth supplied by main.py:
        Easy   = 5
        Medium = 10
        Hard   = 20
    """

    def __init__(self, player_color, depth=10):
        self.player_color = player_color
        self.depth = int(depth)
        self.board = chess.Board()

        stockfish_path = os.getenv("STOCKFISH_PATH")

        if not stockfish_path:
            candidates = [
                os.path.join(os.getcwd(), "stockfish.exe"),
                os.path.join(os.path.dirname(__file__), "stockfish.exe"),
                r"C:\Program Files\Stockfish\stockfish.exe",
                r"C:\Program Files (x86)\Stockfish\stockfish.exe",
            ]

            for path in candidates:
                if os.path.isfile(path):
                    stockfish_path = path
                    break

        if not stockfish_path:
            raise FileNotFoundError(
                "Stockfish executable not found. "
                "Put stockfish.exe in the bot folder or set "
                "STOCKFISH_PATH in your .env file."
            )

        self.engine = chess.engine.SimpleEngine.popen_uci(
            stockfish_path
        )

    def make_player_move(self, move_text):
        try:
            move = self.board.parse_san(move_text)
        except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            return False, None

        # Make sure the submitted move belongs to the human.
        if self.board.turn != self.player_color:
            return False, None

        move_san = self.board.san(move)
        self.board.push(move)

        return True, move_san

    def make_bot_move(self):
        if self.board.is_game_over():
            return None

        if self.board.turn == self.player_color:
            raise RuntimeError("It is currently the player's turn.")

        result = self.engine.play(
            self.board,
            chess.engine.Limit(depth=self.depth)
        )

        move = result.move
        move_san = self.board.san(move)
        self.board.push(move)

        return move_san

    def is_game_over(self):
        return self.board.is_game_over(claim_draw=True)

    def close(self):
        if getattr(self, "engine", None) is not None:
            try:
                self.engine.quit()
            except Exception:
                pass
            self.engine = None

        