class IllegalMoveError(Exception):
    def __init__(self, move, reason):
        super().__init__(f"Illegal move {move}: {reason}")
        self.move = move
        self.reason = reason