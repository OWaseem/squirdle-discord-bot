import os
import random
from datetime import datetime, timezone
from flask import Flask
from threading import Thread

import discord
from discord import app_commands
from discord.ext import commands

# IMPORTANT: relative import because we run with `python -m src.bot`
from .game_logic import find_pokemon, POKEMON_DATA

# =========================================================
# Flask keep-alive (UNCHANGED)
# =========================================================
app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

# =========================================================
# Discord Bot Setup
# =========================================================
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Daily game state (shared puzzle)
daily_game = None  # dict initialized each day
# Personal games per user_id
active_games: dict[int, dict] = {}
bot_updating = False


# =========================================================
# Daily Game Initialization
# =========================================================
def initialize_daily_game():
    """Initialize or refresh the daily game if the date changed."""
    global daily_game
    today_edt = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not daily_game or daily_game["date"] != today_edt:
        random.seed(today_edt)
        daily_pokemon = random.choice(POKEMON_DATA)
        daily_game = {
            "pokemon": daily_pokemon,
            "date": today_edt,
            "attempts": {},      # user_id -> [list of guesses (dicts)]
            "completions": {},   # user_id -> datetime
            "leaderboard": []    # list of {user_id, username, attempts, completion_time}
        }
        print(f"🎮 Daily Squirdle initialized: {daily_pokemon['name'].title()}")
    return daily_game


# =========================================================
# Events
# =========================================================
@bot.event
async def on_ready():
    global bot_updating
    bot_updating = False
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()
    print("🌐 Slash commands synced!")
    initialize_daily_game()

@bot.event
async def on_disconnect():
    global bot_updating
    bot_updating = True
    print("🔄 Bot is updating - please wait a moment...")

@bot.event
async def on_resumed():
    global bot_updating
    bot_updating = False
    print("✅ Bot reconnected and ready!")


# =========================================================
# Helpers
# =========================================================
async def send_not_found(interaction):
    await interaction.response.send_message("❌ Pokémon not found! Try again.")


def compare_and_build_message(guess, secret):
    """Return list of hint strings comparing guess vs secret."""
    results = []

    # Generation
    if guess["generation"] == secret["generation"]:
        results.append("Generation: ✅ same generation")
    elif guess["generation"] > secret["generation"]:
        results.append("Generation: 🔽 earlier gen")
    else:
        results.append("Generation: 🔼 later gen")

    # Types
    type_overlap = set(guess["types"]) & set(secret["types"])
    if type_overlap:
        results.append(f"Type: ✅ shared {', '.join(type_overlap)}")
    else:
        results.append("Type: ❌ no shared types")

    # Height
    if guess["height_m"] > secret["height_m"]:
        results.append("Height: 🔽 secret is shorter")
    elif guess["height_m"] < secret["height_m"]:
        results.append("Height: 🔼 secret is taller")
    else:
        results.append("Height: ✅ same height")

    # Weight
    if guess["weight_kg"] > secret["weight_kg"]:
        results.append("Weight: 🔽 secret is lighter")
    elif guess["weight_kg"] < secret["weight_kg"]:
        results.append("Weight: 🔼 secret is heavier")
    else:
        results.append("Weight: ✅ same weight")

    return results


# =========================================================
# Commands
# =========================================================

@bot.tree.command(name="status", description="Check if the bot is working and your current game status!")
async def status(interaction: discord.Interaction):
    global bot_updating, daily_game, active_games
    user_id = interaction.user.id
    initialize_daily_game()

    if bot_updating:
        embed = discord.Embed(
            title="🔄 Bot Updating",
            description="Please wait a moment! New features are being deployed.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    personal_status = "❌ No active personal game"
    last_personal_guess = None
    if user_id in active_games and not active_games[user_id]["finished"]:
        game = active_games[user_id]
        remaining = game["max_tries"] - game["attempts"]
        personal_status = f"🎮 Active — {remaining} tries left"
        if game.get("guesses"):
            last_personal_guess = game["guesses"][-1]

    user_attempts = len(daily_game["attempts"].get(user_id, []))
    daily_remaining = 9 - user_attempts
    last_daily_guess = None
    if user_id in daily_game["completions"]:
        daily_status = "✅ Completed!"
    elif user_attempts >= 9:
        daily_status = "❌ Out of tries!"
    elif user_attempts > 0:
        daily_status = f"🕹️ In progress — {daily_remaining} tries left"
        last_daily_guess = daily_game["attempts"][user_id][-1]
    else:
        daily_status = "💤 Not started yet"

    embed = discord.Embed(title="🧩 Squirdle Bot Status", color=discord.Color.green())
    embed.add_field(name="🟢 Bot Status", value="Online and ready!", inline=False)
    embed.add_field(name="📅 Daily Game", value=daily_status, inline=False)
    embed.add_field(name="🎮 Personal Game", value=personal_status, inline=False)

    if last_daily_guess or last_personal_guess:
        summary = ""
        if last_daily_guess:
            summary += f"📅 **Last Daily Guess:** {last_daily_guess.get('name', 'Unknown').title()}\n"
        if last_personal_guess:
            summary += f"🎮 **Last Personal Guess:** {last_personal_guess.get('name', 'Unknown').title()}\n"
        embed.add_field(name="🔍 Recent Guess Summary", value=summary.strip(), inline=False)

    embed.set_footer(text="💡 Use /stats for detailed hint breakdowns and progress.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# -------------------- HELP --------------------

@bot.tree.command(name="help", description="Learn how to play Squirdle!")
async def help_command(interaction: discord.Interaction):
    """Displays game rules and command guide in compact, styled embeds."""
    # --- Embed 1: Overview + Commands ---
    embed1 = discord.Embed(
        title="🎮 Welcome to **Squirdle** — the Pokémon Wordle Game!",
        description=(
            "Guess the secret Pokémon using clues about its **generation**, **type**, **height**, "
            "**weight**, and **Pokédex number**. You have **9 tries** per game — choose wisely, Trainer! ⚡"
        ),
        color=discord.Color.blurple()
    )

    embed1.add_field(
        name="🧩 Commands",
        value=(
            "• `/start` — Begin a new **personal game** (private to you)\n"
            "• `/daily` — Play today’s **shared daily puzzle**\n"
            "• `/guess` — Make a guess in your active game\n"
            "• `/stats` — View detailed progress and last hints\n"
            "• `/status` — Check your ongoing games\n"
            "• `/leaderboard` — See today’s top solvers\n"
            "• `/quit` — End your personal game early\n"
            "• `/help` — Show this guide"
        ),
        inline=False
    )

    embed1.add_field(
        name="📅 Game Modes",
        value=(
            "🟢 **Daily Mode** — Same Pokémon for everyone, resets at midnight (EDT).\n"
            "🔵 **Personal Mode** — Private challenge unique to you."
        ),
        inline=False
    )

    # --- Embed 2: Hints, Privacy, Tips ---
    embed2 = discord.Embed(
        title="💡 How to Play & Get Better!",
        color=discord.Color.green()
    )

    embed2.add_field(
        name="🧠 Hints You’ll Receive",
        value=(
            "• **Generation** → earlier / later / same\n"
            "• **Type** → shared / none\n"
            "• **Height** → taller / shorter / same\n"
            "• **Weight** → heavier / lighter / same\n"
            "• **Pokédex** → higher / lower / same"
        ),
        inline=False
    )

    embed2.add_field(
        name="🔒 Privacy",
        value=(
            "All personal game messages are **private**.\n"
            "`/leaderboard` results are public, but your full stats remain private."
        ),
        inline=False
    )

    embed2.add_field(
        name="🏆 Tips for Trainers",
        value=(
            "• Use autocomplete when guessing.\n"
            "• Track clues logically to narrow your guesses.\n"
            "• Play both modes — they don’t interfere!\n"
            "• Daily Pokémon resets every midnight (EDT)."
        ),
        inline=False
    )

    embed2.set_footer(text="Good luck, Trainer — your Pokédex mastery awaits! 🏆")

    # --- Send both embeds (ephemeral or public as you prefer) ---
    await interaction.response.send_message(embeds=[embed1, embed2], ephemeral=True)



# -------------------- DAILY --------------------
@bot.tree.command(name="daily", description="Start today's Squirdle - same for everyone!")
async def daily(interaction: discord.Interaction):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    user_attempts = daily_game["attempts"].get(user_id, [])
    message = ""

    # --- Determine the correct message for the user's state ---
    if user_id in daily_game["completions"]:
        t = daily_game["completions"][user_id].strftime("%H:%M EDT")
        message = (
            f"🎉 You already solved today's Squirdle at {t}.\n"
            f"🕐 New puzzle available at midnight EDT!"
        )

    elif len(user_attempts) >= 9:
        message = (
            f"❌ You've used all 9 attempts for today's Squirdle!\n"
            f"🕐 New puzzle available at midnight EDT!"
        )

    elif user_attempts:
        remaining = 9 - len(user_attempts)
        message = (
            f"🎮 Welcome back to today's Squirdle! You have {remaining} attempts remaining.\n"
            f"Use `/guess name:<pokemon>` to continue playing!\n"
            f"💡 Use `/leaderboard` to see today's fastest solvers!"
        )

    else:
        message = (
            f"🎮 Starting today's Squirdle! You can keep playing your personal game alongside this one.\n\n"
            f"Use `/guess name:<pokemon>` to make your first guess.\n"
            f"💡 Use `/leaderboard` to see today's fastest solvers!"
        )

    # --- Send one clear, public message ---
    await interaction.response.send_message(message, ephemeral=False)



# -------------------- START --------------------
@bot.tree.command(name="start", description="Start a new personal Squirdle game!")
async def start(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in active_games and not active_games[user_id]["finished"]:
        secret_name = active_games[user_id]["secret"]["name"].title()
        await interaction.response.send_message(
            f"⚠️ You already have a personal game!\n🕹️ Pokémon (hidden): **{secret_name}**\nUse `/quit` to end it first.",
            ephemeral=True
        )
        return

    secret = random.choice(POKEMON_DATA)
    active_games[user_id] = {
        "secret": secret,
        "attempts": 0,
        "max_tries": 9,
        "finished": False,
        "guesses": []  # ✅ added
    }

    await interaction.response.send_message(
        f"🎮 New personal game started!\nYou have 9 tries to guess the Pokémon.\nUse `/guess` to make your first guess.\n🛑 `/quit` ends and reveals it.",
        ephemeral=True
    )


# -------------------- QUIT --------------------
@bot.tree.command(name="quit", description="Quit your current personal Squirdle game")
async def quit_personal(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in active_games and not active_games[user_id]["finished"]:
        secret_name = active_games[user_id]["secret"]["name"].title()
        del active_games[user_id]
        await interaction.response.send_message(
            f"🛑 You ended your personal game.\nThe secret Pokémon was **{secret_name}**! 🔍",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "ℹ️ You don't have an active personal game. Use `/start` to begin one!",
            ephemeral=True
        )


# -------------------- AUTOCOMPLETE --------------------
async def pokemon_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Return up to 25 Pokémon names matching the current input (for /guess autocomplete)."""
    query = (current or "").strip().lower()
    matches: list[app_commands.Choice[str]] = []

    # If user typed nothing, suggest a few starters
    if not query:
        for p in POKEMON_DATA[:10]:
            matches.append(app_commands.Choice(name=p["name"].title(), value=p["name"]))
        return matches

    # Search all Pokémon
    for p in POKEMON_DATA:
        name = p["name"]
        if query in name.lower():
            matches.append(app_commands.Choice(name=name.title(), value=name))
            if len(matches) >= 25:  # Discord autocomplete limit
                break

    return matches

# -------------------- GUESS --------------------
@bot.tree.command(name="guess", description="Make a guess in your current Squirdle game!")
@app_commands.describe(name="The Pokémon you want to guess")
@app_commands.autocomplete(name=pokemon_autocomplete)
async def guess(interaction: discord.Interaction, name: str):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    # PERSONAL FIRST
    if user_id in active_games and not active_games[user_id]["finished"]:
        game = active_games[user_id]
        guess_data = find_pokemon(name)
        if not guess_data:
            await interaction.response.send_message("❌ Pokémon not found!", ephemeral=True)
            return

        game["guesses"].append(guess_data)
        game["attempts"] += 1
        attempts_left = game["max_tries"] - game["attempts"]
        secret = game["secret"]

        results = compare_and_build_message(guess_data, secret)
        if guess_data["pokedex"] == secret["pokedex"]:
            results.append("🎉 Correct Pokémon!")
            game["finished"] = True
            msg = "\n".join(results) + f"\n🎊 Solved in {game['attempts']} tries!"
        else:
            if guess_data["pokedex"] > secret["pokedex"]:
                results.append("Pokédex: 🔽 lower number")
            else:
                results.append("Pokédex: 🔼 higher number")
            if attempts_left <= 0:
                results.append(f"❌ Out of tries! It was **{secret['name'].title()}**.")
                game["finished"] = True
            else:
                results.append(f"🕹️ {attempts_left} tries left.")
            msg = "\n".join(results)

        embed = discord.Embed(title="🎮 Personal Guess Result", description=msg, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # DAILY GAME
    user_attempts = daily_game["attempts"].get(user_id, [])
    if len(user_attempts) >= 9:
        await interaction.response.send_message("❌ All 9 attempts used! Wait until midnight.", ephemeral=True)
        return

    guess_data = find_pokemon(name)
    if not guess_data:
        await interaction.response.send_message("❌ Pokémon not found!", ephemeral=True)
        return

    user_attempts.append(guess_data)
    daily_game["attempts"][user_id] = user_attempts
    secret = daily_game["pokemon"]
    results = compare_and_build_message(guess_data, secret)

    if guess_data["pokedex"] == secret["pokedex"]:
        results.append("🎉 Correct Pokémon!")
        completion_time = datetime.now(timezone.utc)
        daily_game["completions"][user_id] = completion_time
        daily_game["leaderboard"].append({
            "user_id": user_id,
            "username": interaction.user.display_name,
            "attempts": len(user_attempts),
            "completion_time": completion_time
        })
        daily_game["leaderboard"].sort(key=lambda x: (x["attempts"], x["completion_time"]))
        msg = "\n".join(results) + f"\n🎊 Solved today's Squirdle in {len(user_attempts)} tries!"
    else:
        if guess_data["pokedex"] > secret["pokedex"]:
            results.append("Pokédex: 🔽 lower number")
        else:
            results.append("Pokédex: 🔼 higher number")
        if len(user_attempts) >= 9:
            results.append(f"❌ Out of tries! It was **{secret['name'].title()}**.")
        else:
            remaining = 9 - len(user_attempts)
            results.append(f"🕹️ {remaining} tries left.")
        msg = "\n".join(results)

    embed = discord.Embed(title="📅 Daily Guess Result", description=msg, color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)


# -------------------- STATS --------------------
@bot.tree.command(name="stats", description="View your personal and daily Squirdle statistics!")
async def stats(interaction: discord.Interaction):
    global daily_game, active_games
    user_id = interaction.user.id
    initialize_daily_game()

    attempts = len(daily_game["attempts"].get(user_id, []))
    solved = user_id in daily_game["completions"]

    if solved:
        t = daily_game["completions"][user_id].strftime("%H:%M EDT")
        daily_title = "✅ Daily Game — Solved!"
        daily_details = f"**Attempts:** {attempts}\n**Completed:** {t}"
        color = discord.Color.green()
    elif attempts >= 9:
        daily_title = "❌ Daily Game — Out of Tries!"
        daily_details = f"**Attempts:** {attempts}/9"
        color = discord.Color.red()
    elif attempts > 0:
        remaining = 9 - attempts
        daily_title = "🕹️ Daily Game — In Progress"
        daily_details = f"**Attempts:** {attempts}/9\n**Remaining:** {remaining}"
        color = discord.Color.orange()
    else:
        daily_title = "💤 Daily Game — Not Started"
        daily_details = "Use `/daily` to begin!"
        color = discord.Color.blurple()

    # ✅ Recomputed hint summary dynamically
    if attempts > 0:
        last_guess = daily_game["attempts"][user_id][-1]
        secret = daily_game["pokemon"]
        last_msgs = compare_and_build_message(last_guess, secret)
        if last_guess["pokedex"] > secret["pokedex"]:
            last_msgs.append("Pokédex: 🔽 lower number")
        elif last_guess["pokedex"] < secret["pokedex"]:
            last_msgs.append("Pokédex: 🔼 higher number")
        else:
            last_msgs.append("Pokédex: ✅ same number")
        daily_details += "\n\n🔍 **Last Daily Guess Summary**\n• Pokémon: **{}**\n• {}".format(
            last_guess["name"].title(), "\n• ".join(last_msgs)
        )

    if user_id in active_games and not active_games[user_id]["finished"]:
        game = active_games[user_id]
        personal_details = f"**Attempts:** {game['attempts']}/{game['max_tries']}\n**Remaining:** {game['max_tries'] - game['attempts']}"
        if game.get("guesses"):
            last_guess = game["guesses"][-1]
            secret = game["secret"]
            last_msgs = compare_and_build_message(last_guess, secret)
            if last_guess["pokedex"] > secret["pokedex"]:
                last_msgs.append("Pokédex: 🔽 lower number")
            elif last_guess["pokedex"] < secret["pokedex"]:
                last_msgs.append("Pokédex: 🔼 higher number")
            else:
                last_msgs.append("Pokédex: ✅ same number")
            personal_details += "\n\n🔍 **Last Personal Guess Summary**\n• Pokémon: **{}**\n• {}".format(
                last_guess["name"].title(), "\n• ".join(last_msgs)
            )
    else:
        personal_details = "No active personal game."

    embed = discord.Embed(title="📊 Your Squirdle Stats", color=color)
    embed.add_field(name=daily_title, value=daily_details, inline=False)
    embed.add_field(name="🎮 Personal Game", value=personal_details, inline=False)
    embed.set_footer(text="🏆 Use /leaderboard to see today's top solvers!")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# KEEP-ALIVE + RUN
# =========================================================
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
