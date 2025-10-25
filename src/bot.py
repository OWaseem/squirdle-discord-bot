import os
import random
from datetime import datetime, timezone
from flask import Flask
from threading import Thread
import discord
from discord import app_commands
from discord.ext import commands
from .game_logic import find_pokemon, POKEMON_DATA

# =========================================================
# Flask keep-alive (UNCHANGED for Render uptime)
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

daily_game = None
active_games = {}
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
            "attempts": {},
            "completions": {},
            "leaderboard": []
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
# Commands
# =========================================================
@bot.tree.command(name="status", description="Check if the bot is working!")
async def status(interaction: discord.Interaction):
    global bot_updating
    if bot_updating:
        await interaction.response.send_message("🔄 Bot is updating - please wait a moment! New features are being deployed.")
    else:
        await interaction.response.send_message("✅ Bot is online and ready to play Squirdle!")


@bot.tree.command(name="help", description="Learn how to play Squirdle!")
async def help_command(interaction: discord.Interaction):
    help_text = """🎮 **How to Play Squirdle**

**Commands:**
• `/start` - Play an individual Squirdle (your own random Pokémon!)
• `/daily` - Play today's Squirdle (same for everyone!)
• `/guess` - Make a guess in your current game
• `/leaderboard` - See today's fastest solvers
• `/stats` - Your daily statistics
• `/quitdaily` - Reset your daily progress and start fresh
• `/quit` - Quit your individual game
• `/status` - Check if bot is working
• `/help` - Show this guide

**Game Rules:**
1. You have **9 tries** to guess the secret Pokémon
2. Each guess gives you hints about:
   - **Generation:** Earlier/later/same generation
   - **Type:** Shared types or no shared types
   - **Height:** Secret is taller/shorter/same height
   - **Weight:** Secret is heavier/lighter/same weight
   - **Pokédex:** Secret has higher/lower/same number

**Daily Features:**
• **Same puzzle for everyone** - Like Wordle!
• **Daily reset** - New Pokémon at midnight EDT
• **Leaderboard** - See who solved it fastest

**Tips:**
• Use auto-completion when typing Pokémon names
• Start with popular Pokémon (Pikachu, Charizard, etc.)
• Use hints to narrow down your next guess

**Win:** Guess the exact Pokémon!
**Lose:** Run out of 9 tries

Good luck! 🍀"""
    await interaction.response.send_message(help_text)


# =========================================================
# DAILY GAME
# =========================================================
@bot.tree.command(name="daily", description="Start today's Squirdle - same for everyone!")
async def daily(interaction: discord.Interaction):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    if user_id in daily_game["completions"]:
        completion_time = daily_game["completions"][user_id]
        await interaction.response.send_message(
            f"🎉 You already solved today's Squirdle! Completed at {completion_time.strftime('%H:%M EDT')}.\n\n"
            f"🕐 New puzzle available at midnight EDT!"
        )
        return

    user_attempts = daily_game["attempts"].get(user_id, [])
    if len(user_attempts) >= 9:
        await interaction.response.send_message(
            f"❌ You've used all 9 attempts for today's Squirdle!\n\n"
            f"🕐 New puzzle available at midnight EDT!"
        )
        return

    if user_attempts:
        remaining = 9 - len(user_attempts)
        await interaction.response.send_message(
            f"🎮 Welcome back to today's Squirdle! You have {remaining} attempts remaining.\n\n"
            f"Use `/guess name:<pokemon>` to make your next guess!"
        )
    else:
        await interaction.response.send_message(
            f"🎮 Welcome to today's Squirdle! You have 9 tries to guess the secret Pokémon.\n\n"
            f"Use `/guess name:<pokemon>` to make your first guess!\n"
            f"💡 Use `/leaderboard` to see today's fastest solvers!"
        )


# =========================================================
# PERSONAL GAME
# =========================================================
@bot.tree.command(name="start", description="Start a new individual Squirdle game!")
async def start(interaction: discord.Interaction):
    user_id = interaction.user.id
    secret = random.choice(POKEMON_DATA)
    active_games[user_id] = {
        "secret": secret,
        "attempts": 0,
        "max_tries": 9,
        "finished": False
    }
    await interaction.response.send_message(
        f"🎮 New game started, {interaction.user.name}! You have 9 tries to guess the Pokémon.\n"
        f"Use `/guess name:<pokemon>` to make your first guess.\n\n"
        f"💡 Use `/help` to learn how to play!\n🛑 Use `/quit` to exit your current game!"
    )


# =========================================================
# GUESS COMMAND (auto-detect game mode)
# =========================================================
@bot.tree.command(name="guess", description="Make a guess in your current Squirdle game!")
@app_commands.describe(name="The Pokémon you want to guess")
async def guess(interaction: discord.Interaction, name: str):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    # Detect which game mode user is in
    if user_id in active_games and not active_games[user_id]["finished"]:
        # PERSONAL GAME
        game = active_games[user_id]
        secret = game["secret"]
        game["attempts"] += 1
        attempts_left = game["max_tries"] - game["attempts"]

        guess_data = find_pokemon(name)
        if not guess_data:
            await interaction.response.send_message("❌ Pokémon not found! Try again.")
            return

        results = []
        # Compare attributes
        if guess_data["generation"] == secret["generation"]:
            results.append("Generation: ✅ same generation")
        elif guess_data["generation"] > secret["generation"]:
            results.append("Generation: 🔽 earlier gen")
        else:
            results.append("Generation: 🔼 later gen")

        type_overlap = set(guess_data["types"]) & set(secret["types"])
        if type_overlap:
            results.append(f"Type: ✅ shared {', '.join(type_overlap)}")
        else:
            results.append("Type: ❌ no shared types")

        if guess_data["height_m"] > secret["height_m"]:
            results.append("Height: 🔽 secret is shorter")
        elif guess_data["height_m"] < secret["height_m"]:
            results.append("Height: 🔼 secret is taller")
        else:
            results.append("Height: ✅ same height")

        if guess_data["weight_kg"] > secret["weight_kg"]:
            results.append("Weight: 🔽 secret is lighter")
        elif guess_data["weight_kg"] < secret["weight_kg"]:
            results.append("Weight: 🔼 secret is heavier")
        else:
            results.append("Weight: ✅ same weight")

        if guess_data["pokedex"] == secret["pokedex"]:
            results.append("🎉 Correct Pokémon!")
            game["finished"] = True
            msg = "\n".join(results)
            msg += f"\n🎊 You solved your personal Squirdle in {game['attempts']} tries!"
        else:
            if guess_data["pokedex"] > secret["pokedex"]:
                results.append("Pokédex: 🔽 secret has a lower number")
            else:
                results.append("Pokédex: 🔼 secret has a higher number")

            if attempts_left <= 0:
                results.append(f"❌ Out of tries! The Pokémon was **{secret['name'].title()}**.")
                game["finished"] = True
            else:
                results.append(f"🕹️ {attempts_left} tries left.")

            msg = "\n".join(results)

        await interaction.response.send_message(msg)
        return

    # Otherwise -> DAILY GAME
    user_attempts = daily_game["attempts"].get(user_id, [])
    if len(user_attempts) >= 9:
        await interaction.response.send_message("❌ You've used all 9 attempts for today's Squirdle! New puzzle available at midnight EDT.")
        return

    guess_data = find_pokemon(name)
    if not guess_data:
        await interaction.response.send_message("❌ Pokémon not found! Try again.")
        return

    user_attempts.append(guess_data)
    daily_game["attempts"][user_id] = user_attempts
    secret = daily_game["pokemon"]

    results = []
    if guess_data["generation"] == secret["generation"]:
        results.append("Generation: ✅ same generation")
    elif guess_data["generation"] > secret["generation"]:
        results.append("Generation: 🔽 earlier gen")
    else:
        results.append("Generation: 🔼 later gen")

    type_overlap = set(guess_data["types"]) & set(secret["types"])
    if type_overlap:
        results.append(f"Type: ✅ shared {', '.join(type_overlap)}")
    else:
        results.append("Type: ❌ no shared types")

    if guess_data["height_m"] > secret["height_m"]:
        results.append("Height: 🔽 secret is shorter")
    elif guess_data["height_m"] < secret["height_m"]:
        results.append("Height: 🔼 secret is taller")
    else:
        results.append("Height: ✅ same height")

    if guess_data["weight_kg"] > secret["weight_kg"]:
        results.append("Weight: 🔽 secret is lighter")
    elif guess_data["weight_kg"] < secret["weight_kg"]:
        results.append("Weight: 🔼 secret is heavier")
    else:
        results.append("Weight: ✅ same weight")

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
        msg = "\n".join(results)
        msg += f"\n🎊 You solved today's Squirdle in {len(user_attempts)} tries!"
    elif guess_data["pokedex"] > secret["pokedex"]:
        results.append("Pokédex: 🔽 secret has a lower number")
        msg = "\n".join(results)
    else:
        results.append("Pokédex: 🔼 secret has a higher number")
        msg = "\n".join(results)

    if len(user_attempts) >= 9 and guess_data["pokedex"] != secret["pokedex"]:
        msg += f"\n❌ Out of tries! Today's Pokémon was **{secret['name'].title()}**."
    else:
        remaining = 9 - len(user_attempts)
        msg += f"\n🕹️ {remaining} tries left."

    await interaction.response.send_message(msg)


# =========================================================
# LEADERBOARD (unchanged)
# =========================================================
@bot.tree.command(name="leaderboard", description="See today's fastest Squirdle solvers!")
async def leaderboard(interaction: discord.Interaction):
    global daily_game
    initialize_daily_game()

    if not daily_game["leaderboard"]:
        await interaction.response.send_message("🏆 No one has solved today's Squirdle yet! Be the first!")
        return

    leaderboard_text = "🏆 **Today's Squirdle Leaderboard**\n\n"
    for i, entry in enumerate(daily_game["leaderboard"][:10], 1):
        time_str = entry["completion_time"].strftime("%H:%M EDT")
        leaderboard_text += f"{i}. **{entry['username']}** - {entry['attempts']} tries ({time_str})\n"

    if len(daily_game["leaderboard"]) > 10:
        leaderboard_text += f"\n... and {len(daily_game['leaderboard']) - 10} more!"

    await interaction.response.send_message(leaderboard_text)


# =========================================================
# KEEP-ALIVE THREAD + BOT RUN
# =========================================================
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
