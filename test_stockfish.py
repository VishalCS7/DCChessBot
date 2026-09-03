from chess_game import ChessGame

game = ChessGame()

print("Chess game started!")
print("Enter moves like: e4, Nf3, Bb5, O-O")
print()

while not game.is_game_over():

    user_move = input("Your move: ").strip()

    success, move_san = game.make_player_move(user_move)

    if not success:
        print("❌ Invalid or illegal move!")
        continue

    print("You played:", move_san)

    if game.is_game_over():
        break

    bot_move = game.make_bot_move()

    print("Stockfish plays:", bot_move)
    print()

game.close()

print("Game over!")