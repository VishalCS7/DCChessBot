import discord
import chess
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

import os
import io
import uuid

from PIL import Image, ImageDraw, ImageFont
from chess_game import ChessGame


# =========================================================
# SETUP
# =========================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

games = {}
player_games = {}

DIFFICULTIES = {
    "easy": {
        "name": "Easy",
        "emoji": "🟢",
        "depth": 5,
        "message": "Don't worry, I'll go easy on you. 😇",
    },
    "medium": {
        "name": "Medium",
        "emoji": "🟡",
        "depth": 10,
        "message": "Alright... I'll give you a fighting chance.",
    },
    "hard": {
        "name": "Hard",
        "emoji": "🔴",
        "depth": 20,
        "message": "Yeah... you're about to get cooked. 💀",
    },
}


# =========================================================
# BOARD IMAGE
# =========================================================

def create_board_image(board, player_color):
    size = 640
    square = size // 8

    light = (220, 239, 247)
    dark = (10, 72, 115)
    highlight = (70, 170, 120)

    image = Image.new("RGB", (size, size), light)
    draw = ImageDraw.Draw(image)

    if player_color == chess.WHITE:
        files = range(8)
        ranks = range(7, -1, -1)
    else:
        files = range(7, -1, -1)
        ranks = range(8)

    for row, rank in enumerate(ranks):
        for col, file_ in enumerate(files):
            x1 = col * square
            y1 = row * square
            x2 = x1 + square
            y2 = y1 + square

            fill = dark if (rank + file_) % 2 == 0 else light
            draw.rectangle([x1, y1, x2, y2], fill=fill)

    if board.move_stack:
        last_move = board.peek()

        for sq in (last_move.from_square, last_move.to_square):
            file_ = chess.square_file(sq)
            rank = chess.square_rank(sq)

            if player_color == chess.WHITE:
                col = file_
                row = 7 - rank
            else:
                col = 7 - file_
                row = rank

            x1 = col * square
            y1 = row * square
            x2 = x1 + square
            y2 = y1 + square
            draw.rectangle([x1, y1, x2, y2], fill=highlight)

    pieces = {
        "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
        "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
    }

    font = None
    for path in (
        r"C:\Windows\Fonts\seguisym.ttf",
        r"C:\Windows\Fonts\segoeuisl.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ):
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, int(square * 0.75))
                break
            except Exception:
                pass

    if font is None:
        font = ImageFont.load_default()

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None:
            continue

        file_ = chess.square_file(sq)
        rank = chess.square_rank(sq)

        if player_color == chess.WHITE:
            col = file_
            row = 7 - rank
        else:
            col = 7 - file_
            row = rank

        x = col * square
        y = row * square
        symbol = pieces[piece.symbol()]

        bbox = draw.textbbox((0, 0), symbol, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        text_x = x + (square - text_width) / 2
        text_y = y + (square - text_height) / 2 - 8

        if piece.color == chess.BLACK:
            draw.text(
                (text_x + 2, text_y + 2),
                symbol,
                font=font,
                fill=(255, 255, 255),
            )
            draw.text(
                (text_x, text_y),
                symbol,
                font=font,
                fill=(20, 20, 20),
            )
        else:
            draw.text(
                (text_x + 2, text_y + 2),
                symbol,
                font=font,
                fill=(20, 20, 20),
            )
            draw.text(
                (text_x, text_y),
                symbol,
                font=font,
                fill=(245, 245, 245),
            )

    try:
        coordinate_font = ImageFont.truetype(
            r"C:\Windows\Fonts\arial.ttf", 16
        )
    except Exception:
        coordinate_font = ImageFont.load_default()

    for col in range(8):
        file_letter = (
            chr(ord("a") + col)
            if player_color == chess.WHITE
            else chr(ord("h") - col)
        )
        draw.text(
            (col * square + 5, size - 22),
            file_letter,
            font=coordinate_font,
            fill=(40, 40, 40),
        )

    for row in range(8):
        rank_number = (
            str(8 - row)
            if player_color == chess.WHITE
            else str(1 + row)
        )
        draw.text(
            (5, row * square + 5),
            rank_number,
            font=coordinate_font,
            fill=(40, 40, 40),
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def make_board_file(board, color):
    return discord.File(
        create_board_image(board, color),
        filename="chessboard.png",
    )


# =========================================================
# AUTOMATIC GAME-OVER CHECKING
# =========================================================

def board_game_over(board):
    return (
        board.is_checkmate()
        or board.is_stalemate()
        or board.is_insufficient_material()
        or board.is_fivefold_repetition()
        or board.is_seventyfive_moves()
        or board.is_repetition()
        or board.is_fifty_moves()
    )


# =========================================================
# HELPERS
# =========================================================

def is_playing(user_id):
    return user_id in player_games


def get_game(user_id):
    game_id = player_games.get(user_id)
    if game_id is None:
        return None, None

    data = games.get(game_id)
    if data is None:
        player_games.pop(user_id, None)
        return None, None

    return game_id, data


def remove_game(game_id):
    data = games.get(game_id)
    if data is None:
        return

    if data["mode"] == "bot":
        try:
            data["game"].close()
        except Exception:
            pass

    for user_id in data["players"]:
        player_games.pop(user_id, None)

    games.pop(game_id, None)


def player_mention(guild, user_id):
    member = guild.get_member(user_id)
    return member.mention if member else f"<@{user_id}>"


def player_name(guild, user_id):
    member = guild.get_member(user_id)
    return member.display_name if member else f"<@{user_id}>"


def get_color_player(data, color):
    for user_id in data["players"]:
        if data["colors"][user_id] == color:
            return user_id
    return None


def result_text(board, data, guild):
    if board.is_checkmate():
        winner_color = chess.WHITE if board.turn == chess.BLACK else chess.BLACK
        winner_id = get_color_player(data, winner_color)
        return f"🏁 **Checkmate! {player_name(guild, winner_id)} wins!**"

    if board.is_stalemate():
        return "🏁 **Draw — Stalemate.**"

    if board.is_insufficient_material():
        return "🏁 **Draw — Insufficient material.**"

    if board.is_fivefold_repetition():
        return "🏁 **Draw — Fivefold repetition.**"

    if board.is_seventyfive_moves():
        return "🏁 **Draw — 75-move rule.**"

    if board.is_repetition():
        return "🏁 **Draw — Threefold repetition.**"

    if board.is_fifty_moves():
        return "🏁 **Draw — 50-move rule.**"

    return "🏁 **Draw.**"


# =========================================================
# DIFFICULTY SELECTION
# =========================================================

class DifficultyView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This game setup isn't for you.",
                ephemeral=True,
            )
            return False
        return True

    async def choose(self, interaction, key):
        difficulty = DIFFICULTIES[key]

        await interaction.response.edit_message(
            content=(
                f"{difficulty['emoji']} **{difficulty['name']}** selected.\n\n"
                f"_{difficulty['message']}_\n\n"
                "♟️ **Now choose your side:**\n\n"
                "⚪ White — You move first\n"
                "⚫ Black — Pixar moves first"
            ),
            view=ChessSideView(self.user, difficulty),
        )

    @discord.ui.button(
        label="Easy",
        emoji="🟢",
        style=discord.ButtonStyle.success,
    )
    async def easy_button(self, interaction, button):
        await self.choose(interaction, "easy")

    @discord.ui.button(
        label="Medium",
        emoji="🟡",
        style=discord.ButtonStyle.primary,
    )
    async def medium_button(self, interaction, button):
        await self.choose(interaction, "medium")

    @discord.ui.button(
        label="Hard",
        emoji="🔴",
        style=discord.ButtonStyle.danger,
    )
    async def hard_button(self, interaction, button):
        await self.choose(interaction, "hard")


# =========================================================
# COLOR SELECTION
# =========================================================

class ChessSideView(discord.ui.View):
    def __init__(self, user, difficulty):
        super().__init__(timeout=60)
        self.user = user
        self.difficulty = difficulty

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This game setup isn't for you.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="White",
        emoji="⚪",
        style=discord.ButtonStyle.primary,
    )
    async def white_button(self, interaction, button):
        await interaction.response.defer()
        await start_bot_game(
            interaction,
            self.user,
            chess.WHITE,
            self.difficulty,
        )
        self.stop()

    @discord.ui.button(
        label="Black",
        emoji="⚫",
        style=discord.ButtonStyle.secondary,
    )
    async def black_button(self, interaction, button):
        await interaction.response.defer()
        await start_bot_game(
            interaction,
            self.user,
            chess.BLACK,
            self.difficulty,
        )
        self.stop()


# =========================================================
# BOT GAME
# =========================================================

async def start_bot_game(interaction, user, color, difficulty):
    if is_playing(user.id):
        await interaction.followup.send(
            "❌ You already have an active game.",
            ephemeral=True,
        )
        return

    game_id = str(uuid.uuid4())

    try:
        game = ChessGame(color, depth=difficulty["depth"])
    except Exception as exc:
        await interaction.followup.send(
            f"❌ Could not start Stockfish: `{exc}`",
            ephemeral=True,
        )
        return

    games[game_id] = {
        "mode": "bot",
        "game": game,
        "difficulty": difficulty,
        "players": [user.id],
        "colors": {user.id: color},
        "channel_id": interaction.channel.id,
        "message_id": None,
    }

    player_games[user.id] = game_id

    if color == chess.WHITE:
        file = make_board_file(game.board, chess.WHITE)

        message = await interaction.edit_original_response(
            content=(
                f"{difficulty['emoji']} **{difficulty['name']} mode**\n"
                f"_{difficulty['message']}_\n\n"
                "♟️ **Game started!**\n\n"
                "You're **White ⚪**.\n"
                "Reply to this message with your move.\n\n"
                "Examples: `e4`, `Nf3`, `O-O`"
            ),
            view=None,
            attachments=[file],
        )

        games[game_id]["message_id"] = message.id

    else:
        await interaction.edit_original_response(
            content=(
                f"{difficulty['emoji']} **{difficulty['name']} mode**\n"
                f"_{difficulty['message']}_\n\n"
                "♟️ **Game started!**\n\n"
                "You're **Black ⚫**.\n"
                "Pixar is thinking..."
            ),
            view=None,
        )

        bot_move = game.make_bot_move()

        file = make_board_file(game.board, chess.BLACK)

        message = await interaction.channel.send(
            content=(
                f"⚪ **Pixar played {bot_move}**\n\n"
                "Reply to this message with your move."
            ),
            file=file,
        )

        games[game_id]["message_id"] = message.id


# =========================================================
# CHALLENGE
# =========================================================

class ChallengeView(discord.ui.View):
    def __init__(self, challenger, challenged):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challenged = challenged

    async def interaction_check(self, interaction):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message(
                "❌ This challenge isn't for you.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="Accept",
        emoji="✅",
        style=discord.ButtonStyle.success,
    )
    async def accept(self, interaction, button):
        if is_playing(self.challenger.id):
            await interaction.response.send_message(
                "❌ The challenger is already playing.",
                ephemeral=True,
            )
            self.stop()
            return

        if is_playing(self.challenged.id):
            await interaction.response.send_message(
                "❌ You are already playing another game.",
                ephemeral=True,
            )
            self.stop()
            return

        await interaction.response.edit_message(
            content=(
                f"✅ {self.challenged.mention} accepted!\n\n"
                f"{self.challenger.mention}, choose your side:"
            ),
            view=PvPSideView(self.challenger, self.challenged),
        )
        self.stop()

    @discord.ui.button(
        label="Decline",
        emoji="❌",
        style=discord.ButtonStyle.danger,
    )
    async def decline(self, interaction, button):
        await interaction.response.edit_message(
            content=(
                f"❌ {self.challenged.mention} declined "
                "the challenge."
            ),
            view=None,
        )
        self.stop()


# =========================================================
# PVP COLOR SELECTION
# =========================================================

class PvPSideView(discord.ui.View):
    def __init__(self, challenger, opponent):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent

    async def interaction_check(self, interaction):
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message(
                "❌ Only the challenger can choose the color.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="White",
        emoji="⚪",
        style=discord.ButtonStyle.primary,
    )
    async def white(self, interaction, button):
        await interaction.response.defer()
        await start_pvp_game(
            interaction,
            self.challenger,
            self.opponent,
            chess.WHITE,
        )
        self.stop()

    @discord.ui.button(
        label="Black",
        emoji="⚫",
        style=discord.ButtonStyle.secondary,
    )
    async def black(self, interaction, button):
        await interaction.response.defer()
        await start_pvp_game(
            interaction,
            self.challenger,
            self.opponent,
            chess.BLACK,
        )
        self.stop()


# =========================================================
# START PVP GAME
# =========================================================

async def start_pvp_game(interaction, challenger, opponent, challenger_color):
    if is_playing(challenger.id):
        await interaction.followup.send(
            "❌ You are already playing.",
            ephemeral=True,
        )
        return

    if is_playing(opponent.id):
        await interaction.followup.send(
            "❌ Your opponent is already playing.",
            ephemeral=True,
        )
        return

    opponent_color = (
        chess.BLACK if challenger_color == chess.WHITE else chess.WHITE
    )

    game_id = str(uuid.uuid4())
    board = chess.Board()

    games[game_id] = {
        "mode": "pvp",
        "board": board,
        "players": [challenger.id, opponent.id],
        "colors": {
            challenger.id: challenger_color,
            opponent.id: opponent_color,
        },
        "channel_id": interaction.channel.id,
        "message_id": None,
        "draw_offer": None,
    }

    player_games[challenger.id] = game_id
    player_games[opponent.id] = game_id

    white_id = get_color_player(games[game_id], chess.WHITE)
    black_id = get_color_player(games[game_id], chess.BLACK)

    file = make_board_file(board, chess.WHITE)

    message = await interaction.channel.send(
        content=(
            "♟️ **PvP Chess**\n\n"
            f"⚪ White: {player_mention(interaction.guild, white_id)}\n"
            f"⚫ Black: {player_mention(interaction.guild, black_id)}\n\n"
            f"➡️ {player_mention(interaction.guild, white_id)}, "
            "**it's your turn!**\n\n"
            "Reply to this message with your move."
        ),
        file=file,
    )

    games[game_id]["message_id"] = message.id


# =========================================================
# /PLAY
# =========================================================

@bot.tree.command(
    name="play",
    description="Start a chess game against Pixar",
)
async def play(interaction):
    if is_playing(interaction.user.id):
        await interaction.response.send_message(
            "❌ You already have an active game.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "♟️ **Choose your difficulty**\n\n"
        "🟢 **Easy** — Don't worry, I'll go easy on you. 😇\n"
        "🟡 **Medium** — Alright... I'll give you a fighting chance.\n"
        "🔴 **Hard** — Yeah... you're about to get cooked. 💀",
        view=DifficultyView(interaction.user),
    )


# =========================================================
# /CHALLENGE
# =========================================================

@bot.tree.command(
    name="challenge",
    description="Challenge another player to chess",
)
@app_commands.describe(
    player="The player you want to challenge"
)
async def challenge(interaction, player: discord.Member):
    challenger = interaction.user

    if player.id == challenger.id:
        await interaction.response.send_message(
            "❌ You can't challenge yourself.",
            ephemeral=True,
        )
        return

    if player.bot:
        await interaction.response.send_message(
            "❌ You can't challenge a bot.",
            ephemeral=True,
        )
        return

    if is_playing(challenger.id):
        await interaction.response.send_message(
            "❌ You are already playing a game.",
            ephemeral=True,
        )
        return

    if is_playing(player.id):
        await interaction.response.send_message(
            f"❌ {player.mention} is already playing a game.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        content=(
            "♟️ **Chess Challenge!**\n\n"
            f"{challenger.mention} has challenged {player.mention}!\n\n"
            f"{player.mention}, accept or decline."
        ),
        view=ChallengeView(challenger, player),
    )


# =========================================================
# /RESIGN
# =========================================================

@bot.tree.command(
    name="resign",
    description="Resign your current chess game",
)
async def resign(interaction):
    game_id, data = get_game(interaction.user.id)

    if data is None:
        await interaction.response.send_message(
            "❌ You don't have an active game.",
            ephemeral=True,
        )
        return

    resigning_name = player_name(
        interaction.guild,
        interaction.user.id,
    )

    if data["mode"] == "pvp":
        opponent_id = next(
            uid for uid in data["players"]
            if uid != interaction.user.id
        )

        winner_name = player_name(
            interaction.guild,
            opponent_id,
        )

        remove_game(game_id)

        await interaction.response.send_message(
            f"🏳️ **{resigning_name} resigned!**\n\n"
            f"🏆 **{winner_name} wins!**"
        )
        return

    remove_game(game_id)

    await interaction.response.send_message(
        f"🏳️ **{resigning_name} resigned!**\n\n"
        "🏆 **Pixar wins!**"
    )


# =========================================================
# /DRAW
# =========================================================

class DrawOfferView(discord.ui.View):
    def __init__(self, game_id, offered_by, opponent):
        super().__init__(timeout=60)
        self.game_id = game_id
        self.offered_by = offered_by
        self.opponent = opponent

    async def interaction_check(self, interaction):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(
                "❌ This draw offer isn't for you.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="Accept Draw",
        emoji="✅",
        style=discord.ButtonStyle.success,
    )
    async def accept_draw(self, interaction, button):
        data = games.get(self.game_id)

        if data is None:
            await interaction.response.send_message(
                "❌ This game has already ended.",
                ephemeral=True,
            )
            self.stop()
            return

        await interaction.response.edit_message(
            content=(
                "🤝 **Draw agreed!**\n\n"
                f"{player_name(interaction.guild, self.offered_by.id)} "
                "offered a draw.\n"
                f"{player_name(interaction.guild, self.opponent.id)} "
                "accepted.\n\n"
                "🏁 **Game ends in a draw.**"
            ),
            view=None,
        )

        remove_game(self.game_id)
        self.stop()

    @discord.ui.button(
        label="Decline Draw",
        emoji="❌",
        style=discord.ButtonStyle.danger,
    )
    async def decline_draw(self, interaction, button):
        data = games.get(self.game_id)

        if data is None:
            await interaction.response.send_message(
                "❌ This game has already ended.",
                ephemeral=True,
            )
            self.stop()
            return

        data["draw_offer"] = None

        await interaction.response.edit_message(
            content=(
                "❌ **Draw offer declined.**\n\n"
                f"{player_name(interaction.guild, self.opponent.id)} "
                "declined the draw.\n\n"
                "♟️ **The game continues!**"
            ),
            view=None,
        )
        self.stop()

    async def on_timeout(self):
        data = games.get(self.game_id)
        if data is not None:
            data["draw_offer"] = None


@bot.tree.command(
    name="draw",
    description="Offer a draw to your opponent",
)
async def draw(interaction):
    game_id, data = get_game(interaction.user.id)

    if data is None:
        await interaction.response.send_message(
            "❌ You don't have an active game.",
            ephemeral=True,
        )
        return

    if data["mode"] != "pvp":
        await interaction.response.send_message(
            "❌ You can't offer a draw to Pixar.",
            ephemeral=True,
        )
        return

    board = data["board"]

    if board_game_over(board):
        await interaction.response.send_message(
            "❌ The game has already ended.",
            ephemeral=True,
        )
        return

    if data.get("draw_offer") is not None:
        await interaction.response.send_message(
            "❌ You already have a pending draw offer.",
            ephemeral=True,
        )
        return

    opponent_id = next(
        uid for uid in data["players"]
        if uid != interaction.user.id
    )

    try:
        opponent = await interaction.guild.fetch_member(opponent_id)
    except discord.NotFound:
        await interaction.response.send_message(
            "❌ Could not find your opponent in this server.",
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "❌ Discord couldn't retrieve your opponent right now. Try again.",
            ephemeral=True,
        )
        return

    data["draw_offer"] = {
        "from": interaction.user.id,
        "to": opponent.id,
    }

    await interaction.response.send_message(
        content=(
            "🤝 **Draw Offer**\n\n"
            f"{player_name(interaction.guild, interaction.user.id)} "
            "has offered a draw!\n\n"
            f"{opponent.mention}, **do you accept?**"
        ),
        view=DrawOfferView(
            game_id,
            interaction.user,
            opponent,
        ),
    )


# =========================================================
# /HELP
# =========================================================

@bot.tree.command(
    name="help",
    description="Show Pixar Chess commands",
)
async def help_command(interaction):
    embed = discord.Embed(
        title="♟️ Pixar Chess — Help",
        description="Play against Pixar or challenge another player.",
    )

    embed.add_field(
        name="🎮 /play",
        value="Start a game against Pixar. Choose difficulty, then White or Black.",
        inline=False,
    )

    embed.add_field(
        name="⚙️ Difficulty",
        value=(
            "🟢 **Easy** — depth 5 — fastest\n"
            "🟡 **Medium** — depth 10 — fast\n"
            "🔴 **Hard** — depth 20 — strongest and slower"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚔️ /challenge",
        value="Challenge another Discord player.",
        inline=False,
    )

    embed.add_field(
        name="🏳️ /resign",
        value="Resign your current game.",
        inline=False,
    )

    embed.add_field(
        name="🤝 /draw",
        value="Offer a draw to your PvP opponent. They can accept or decline.",
        inline=False,
    )

    embed.add_field(
        name="⚖️ Automatic draws",
        value=(
            "Stalemate, threefold repetition, 50-move rule, "
            "fivefold repetition, 75-move rule, and insufficient material."
        ),
        inline=False,
    )

    embed.add_field(
        name="♟️ Making moves",
        value=(
            "Reply directly to the current chess board message.\n\n"
            "Examples: `e4`, `Nf3`, `O-O`, `Qxd5`"
        ),
        inline=False,
    )

    embed.add_field(
        name="👥 PvP",
        value="Only ONE board is used. It automatically rotates after every move.",
        inline=False,
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as exc:
        print(f"Slash command sync error: {exc}")

    print("Bot is ready!")


# =========================================================
# MESSAGE HANDLER
# =========================================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id

    # Users who are not playing are ignored.
    if user_id not in player_games:
        return

    game_id = player_games[user_id]
    data = games.get(game_id)

    if data is None:
        player_games.pop(user_id, None)
        return

    if message.channel.id != data["channel_id"]:
        return

    # Prefix commands such as !stop, if you add any later.
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    # A move must always be a reply to the current board message.
    if message.reference is None:
        return

    if message.reference.message_id != data["message_id"]:
        return

    # =====================================================
    # PVP
    # =====================================================

    if data["mode"] == "pvp":
        board = data["board"]
        player_color = data["colors"][user_id]

        if board.turn != player_color:
            return

        move_text = message.content.strip()

        try:
            move = board.parse_san(move_text)
        except ValueError:
            board_message = await message.channel.fetch_message(
                data["message_id"]
            )

            file = make_board_file(board, player_color)

            await board_message.edit(
                content=(
                    "♟️ **PvP Chess**\n\n"
                    f"⚪ White: <@{get_color_player(data, chess.WHITE)}>\n"
                    f"⚫ Black: <@{get_color_player(data, chess.BLACK)}>\n\n"
                    "❌ **Invalid or illegal move!**\n\n"
                    f"➡️ <@{user_id}>, it's still your turn.\n\n"
                    "Examples: `e4`, `Nf3`, `O-O`"
                ),
                attachments=[file],
            )
            return

        move_san = board.san(move)
        board.push(move)

        board_message = await message.channel.fetch_message(
            data["message_id"]
        )

        # Game finished: edit the SAME board message.
        if board_game_over(board):
            file = make_board_file(board, player_color)

            await board_message.edit(
                content=(
                    "♟️ **PvP Chess — Game Over**\n\n"
                    f"⚪ White: <@{get_color_player(data, chess.WHITE)}>\n"
                    f"⚫ Black: <@{get_color_player(data, chess.BLACK)}>\n\n"
                    f"**{player_name(message.guild, user_id)} "
                    f"played {move_san}**\n\n"
                    f"{result_text(board, data, message.guild)}"
                ),
                attachments=[file],
            )

            remove_game(game_id)
            return

        opponent_id = next(
            uid for uid in data["players"]
            if uid != user_id
        )

        opponent_color = data["colors"][opponent_id]

        # IMPORTANT:
        # The SAME Discord message is edited and the board rotates.
        file = make_board_file(board, opponent_color)

        await board_message.edit(
            content=(
                "♟️ **PvP Chess**\n\n"
                f"⚪ White: <@{get_color_player(data, chess.WHITE)}>\n"
                f"⚫ Black: <@{get_color_player(data, chess.BLACK)}>\n\n"
                f"**{player_name(message.guild, user_id)} "
                f"played {move_san}**\n\n"
                f"➡️ <@{opponent_id}>, **it's your turn!**\n\n"
                "Reply to this message with your move."
            ),
            attachments=[file],
        )

        return

    # =====================================================
    # PIXAR
    # =====================================================

    game = data["game"]
    player_color = data["colors"][user_id]
    move_text = message.content.strip()

    success, move_san = game.make_player_move(move_text)

    board_message = await message.channel.fetch_message(
        data["message_id"]
    )

    if not success:
        file = make_board_file(game.board, player_color)

        await board_message.edit(
            content=(
                f"{data['difficulty']['emoji']} "
                f"**Pixar Chess — {data['difficulty']['name']}**\n\n"
                "❌ **Invalid or illegal move!**\n\n"
                "Reply to this message with a legal move.\n\n"
                "Examples: `e4`, `Nf3`, `O-O`"
            ),
            attachments=[file],
        )
        return

    player_icon = "⚪" if player_color == chess.WHITE else "⚫"

    if board_game_over(game.board):
        file = make_board_file(game.board, player_color)

        await board_message.edit(
            content=(
                f"{data['difficulty']['emoji']} "
                f"**Pixar Chess — {data['difficulty']['name']}**\n\n"
                f"{player_icon} **You played {move_san}**\n\n"
                f"🏁 **Game over!**\n"
                f"Result: `{game.board.result()}`"
            ),
            attachments=[file],
        )

        remove_game(game_id)
        return

    bot_move = game.make_bot_move()

    bot_icon = "⚫" if player_color == chess.WHITE else "⚪"
    file = make_board_file(game.board, player_color)

    await board_message.edit(
        content=(
            f"{data['difficulty']['emoji']} "
            f"**Pixar Chess — {data['difficulty']['name']}**\n\n"
            f"{player_icon} **You played {move_san}**\n"
            f"{bot_icon} **Pixar played {bot_move}**\n\n"
            "Reply to this message with your move."
        ),
        attachments=[file],
    )

    if board_game_over(game.board):
        await board_message.edit(
            content=(
                f"{data['difficulty']['emoji']} "
                f"**Pixar Chess — {data['difficulty']['name']} — Game Over**\n\n"
                f"{player_icon} **You played {move_san}**\n"
                f"{bot_icon} **Pixar played {bot_move}**\n\n"
                f"🏁 **Game over!**\n"
                f"Result: `{game.board.result()}`"
            ),
            attachments=[file],
        )

        remove_game(game_id)


# =========================================================
# RUN
# =========================================================

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from your .env file."
    )

bot.run(TOKEN)
