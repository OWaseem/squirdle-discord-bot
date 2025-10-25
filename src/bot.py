import os
import random
import json
import discord
import signal
import sys
from datetime import datetime, timezone
discord.opus = None   # 👈 Prevents Render crash (disables audio)

# Fix for Python 3.13 audioop module issue
try:
    import audioop
except ImportError:
    # Create a dummy audioop module for Python 3.13+
    import sys
    import types
    audioop = types.ModuleType('audioop')
    audioop.ratecv = lambda *args, **kwargs: (b'', 0)
    audioop.lin2lin = lambda *args, **kwargs: b''
    audioop.lin2ulaw = lambda *args, **kwargs: b''
    audioop.lin2alaw = lambda *args, **kwargs: b''
    audioop.ulaw2lin = lambda *args, **kwargs: b''
    audioop.alaw2lin = lambda *args, **kwargs: b''
    audioop.lin2adpcm = lambda *args, **kwargs: (b'', 0)
    audioop.adpcm2lin = lambda *args, **kwargs: b''
    sys.modules['audioop'] = audioop

from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# ---------------------------
# KEEP-ALIVE SERVER (for uptime checks)
# ---------------------------
app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------------------
# DISCORD BOT SETUP
# ---------------------------
keep_alive()  # Start the uptime web server
load_dotenv()  # Load token from .env (for local dev)

TOKEN = os.getenv("DISCORD_TOKEN")

# Load Pokémon data
import os
data_path = os.path.join(os.path.dirname(__file__), "..", "data", "pokemon.json")
with open(data_path, "r", encoding="utf-8") as f:
    POKEMON_DATA = json.load(f)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix="!", intents=intents)
active_games = {}  # Keep for backward compatibility
bot_updating = False  # Track if bot is updating

# Daily Squirdle system
daily_game = {
    "pokemon": None,
    "date": None,
    "attempts": {},  # user_id: [list of guesses]
    "completions": {},  # user_id: completion_time
    "leaderboard": []  # sorted by completion time
}

def find_pokemon(name):
    name = name.lower().strip()
    for p in POKEMON_DATA:
        if p["name"] == name:
            return p
    return None

def initialize_daily_game():
    """Initialize or reset the daily game"""
    global daily_game
    today = datetime.now(timezone.utc).date()
    
    # Check if we need to reset for a new day
    if daily_game["date"] != today:
        # Use date as seed for consistent daily Pokémon
        seed = today.toordinal()
        random.seed(seed)
        daily_pokemon = random.choice(POKEMON_DATA)
        
        daily_game = {
            "pokemon": daily_pokemon,
            "date": today,
            "attempts": {},
            "completions": {},
            "leaderboard": []
        }
        print(f"🎮 Daily Squirdle initialized: {daily_pokemon['name'].title()}")
    
    return daily_game

@bot.event
async def on_ready():
    global bot_updating
    bot_updating = False  # Bot is back online
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()
    print("🌐 Slash commands synced!")
    
    # Initialize daily game
    initialize_daily_game()

@bot.event
async def on_disconnect():
    global bot_updating
    bot_updating = True  # Bot is updating/disconnecting
    print("🔄 Bot is updating - please wait a moment...")

@bot.event
async def on_resumed():
    global bot_updating
    bot_updating = False  # Bot reconnected
    print("✅ Bot reconnected and ready!")

@bot.tree.command(name="status", description="Check if the bot is working!")
async def status(interaction: discord.Interaction):
    global bot_updating
    if bot_updating:
        await interaction.response.send_message("🔄 Bot is updating - please wait a moment! New features are being deployed.")
    else:
        await interaction.response.send_message("✅ Bot is online and ready to play Squirdle!")

@bot.tree.command(name="updating", description="Mark bot as updating (for development)")
async def updating(interaction: discord.Interaction):
    global bot_updating
    bot_updating = True
    await interaction.response.send_message("🔄 Bot marked as updating - users will be notified!")

@bot.tree.command(name="help", description="Learn how to play Squirdle!")
async def help_command(interaction: discord.Interaction):
    help_text = """🎮 **How to Play Squirdle**

**Commands:**
• `/daily` - Play today's Squirdle (same for everyone!)
• `/guess` - Make a guess in daily game
• `/leaderboard` - See today's fastest solvers
• `/stats` - Your daily statistics
• `/status` - Check if bot is working
• `/help` - Show this guide

**Game Rules:**
1. You have **9 tries** to guess today's secret Pokémon
2. Each guess gives you hints about:
   - **Generation:** Earlier/later/same generation
   - **Type:** Shared types or no shared types
   - **Height:** Secret is taller/shorter/same height
   - **Weight:** Secret is heavier/lighter/same weight
   - **Pokédex:** Secret has higher/lower/same number

**Daily Features:**
• **Same puzzle for everyone** - Like Wordle!
• **Daily reset** - New Pokémon at midnight UTC
• **Leaderboard** - See who solved it fastest
• **One attempt per day** - No multiple tries

**Tips:**
• Use auto-completion when typing Pokémon names
• Start with popular Pokémon (Pikachu, Charizard, etc.)
• Use hints to narrow down your next guess
• Everyone plays the same puzzle!

**Win:** Guess the exact Pokémon!
**Lose:** Run out of 9 tries

Good luck! 🍀"""
    
    await interaction.response.send_message(help_text)

@bot.tree.command(name="daily", description="Start today's Squirdle - same for everyone!")
async def daily(interaction: discord.Interaction):
    global daily_game
    user_id = interaction.user.id
    
    # Initialize daily game if needed
    initialize_daily_game()
    
    # Check if user already completed today's puzzle
    if user_id in daily_game["completions"]:
        completion_time = daily_game["completions"][user_id]
        await interaction.response.send_message(
            f"🎉 You already solved today's Squirdle! Completed at {completion_time.strftime('%H:%M UTC')}.\n\n"
            f"🕐 New puzzle available at midnight UTC!"
        )
        return
    
    # Check if user has attempts remaining
    user_attempts = daily_game["attempts"].get(user_id, [])
    if len(user_attempts) >= 9:
        await interaction.response.send_message(
            f"❌ You've used all 9 attempts for today's Squirdle!\n\n"
            f"🕐 New puzzle available at midnight UTC!"
        )
        return
    
    # Show current progress or start message
    if user_attempts:
        attempts_used = len(user_attempts)
        remaining = 9 - attempts_used
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

@bot.tree.command(name="start", description="Start a new Squirdle game!")
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
        f"🎮 New game started, {interaction.user.name}! You have 9 tries to guess the Pokémon. Use `/guess name:<pokemon>` - auto-completion will help with spelling!\n\n💡 Use `/help` to learn how to play!\n🛑 Use `/quit` to exit your current game!"
    )

async def pokemon_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    # Get first 25 Pokémon that match the current input
    matches = []
    current_lower = current.lower()
    
    for pokemon in POKEMON_DATA:
        if current_lower in pokemon["name"].lower():
            matches.append(app_commands.Choice(name=pokemon["name"].title(), value=pokemon["name"]))
            if len(matches) >= 25:  # Discord limit
                break
    
    return matches

@bot.tree.command(name="guess", description="Guess a Pokémon in today's Squirdle!")
@app_commands.describe(name="The Pokémon you want to guess")
@app_commands.autocomplete(name=pokemon_autocomplete)
async def guess(interaction: discord.Interaction, name: str):
    global daily_game
    user_id = interaction.user.id
    
    # Initialize daily game if needed
    initialize_daily_game()
    
    # Check if user already completed today's puzzle
    if user_id in daily_game["completions"]:
        await interaction.response.send_message("🎉 You already solved today's Squirdle! New puzzle available at midnight UTC.")
        return
    
    # Check if user has attempts remaining
    user_attempts = daily_game["attempts"].get(user_id, [])
    if len(user_attempts) >= 9:
        await interaction.response.send_message("❌ You've used all 9 attempts for today's Squirdle! New puzzle available at midnight UTC.")
        return
    
    guess = find_pokemon(name)
    if not guess:
        await interaction.response.send_message("❌ Pokémon not found! Try again.")
        return
    
    # Add this guess to user's attempts
    user_attempts.append(guess)
    daily_game["attempts"][user_id] = user_attempts
    
    secret = daily_game["pokemon"]
    results = []

    # Compare attributes
    if guess["generation"] == secret["generation"]:
        results.append("Generation: ✅ same generation")
    elif guess["generation"] > secret["generation"]:
        results.append("Generation: 🔽 earlier gen")
    else:
        results.append("Generation: 🔼 later gen")

    type_overlap = set(guess["types"]) & set(secret["types"])
    if type_overlap:
        results.append(f"Type: ✅ shared {', '.join(type_overlap)}")
    else:
        results.append("Type: ❌ no shared types")

    if guess["height_m"] > secret["height_m"]:
        results.append("Height: 🔽 secret is shorter")
    elif guess["height_m"] < secret["height_m"]:
        results.append("Height: 🔼 secret is taller")
    else:
        results.append("Height: ✅ same height")

    if guess["weight_kg"] > secret["weight_kg"]:
        results.append("Weight: 🔽 secret is lighter")
    elif guess["weight_kg"] < secret["weight_kg"]:
        results.append("Weight: 🔼 secret is heavier")
    else:
        results.append("Weight: ✅ same weight")

    if guess["pokedex"] == secret["pokedex"]:
        results.append("🎉 Correct Pokémon!")
        # Record completion
        completion_time = datetime.now(timezone.utc)
        daily_game["completions"][user_id] = completion_time
        daily_game["leaderboard"].append({
            "user_id": user_id,
            "username": interaction.user.display_name,
            "attempts": len(user_attempts),
            "completion_time": completion_time
        })
        # Sort leaderboard by attempts, then by completion time
        daily_game["leaderboard"].sort(key=lambda x: (x["attempts"], x["completion_time"]))
        
        msg = "\n".join(results)
        msg += f"\n🎊 You solved today's Squirdle in {len(user_attempts)} tries!"
        msg += f"\n🏆 You're #{daily_game['leaderboard'].index({'user_id': user_id, 'username': interaction.user.display_name, 'attempts': len(user_attempts), 'completion_time': completion_time}) + 1} on today's leaderboard!"
    elif guess["pokedex"] > secret["pokedex"]:
        results.append("Pokédex: 🔽 secret has a lower number")
    else:
        results.append("Pokédex: 🔼 secret has a higher number")

    msg = "\n".join(results)
    if len(user_attempts) >= 9:
        msg += f"\n❌ Out of tries! Today's Pokémon was **{secret['name'].title()}**."
    else:
        remaining = 9 - len(user_attempts)
        msg += f"\n🕹️ {remaining} tries left."

    await interaction.response.send_message(msg)

@bot.tree.command(name="leaderboard", description="See today's fastest Squirdle solvers!")
async def leaderboard(interaction: discord.Interaction):
    global daily_game
    initialize_daily_game()
    
    if not daily_game["leaderboard"]:
        await interaction.response.send_message("🏆 No one has solved today's Squirdle yet! Be the first!")
        return
    
    leaderboard_text = "🏆 **Today's Squirdle Leaderboard**\n\n"
    for i, entry in enumerate(daily_game["leaderboard"][:10], 1):  # Top 10
        time_str = entry["completion_time"].strftime("%H:%M UTC")
        leaderboard_text += f"{i}. **{entry['username']}** - {entry['attempts']} tries ({time_str})\n"
    
    if len(daily_game["leaderboard"]) > 10:
        leaderboard_text += f"\n... and {len(daily_game['leaderboard']) - 10} more!"
    
    await interaction.response.send_message(leaderboard_text)

@bot.tree.command(name="stats", description="Your daily Squirdle statistics!")
async def stats(interaction: discord.Interaction):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()
    
    user_attempts = daily_game["attempts"].get(user_id, [])
    
    if user_id in daily_game["completions"]:
        completion_time = daily_game["completions"][user_id]
        attempts_used = len(user_attempts)
        time_str = completion_time.strftime("%H:%M UTC")
        
        # Find rank on leaderboard
        rank = None
        for i, entry in enumerate(daily_game["leaderboard"], 1):
            if entry["user_id"] == user_id:
                rank = i
                break
        
        stats_text = f"🎉 **Today's Squirdle - SOLVED!**\n\n"
        stats_text += f"✅ **Completed in {attempts_used} tries**\n"
        stats_text += f"⏰ **Completed at {time_str}**\n"
        if rank:
            stats_text += f"🏆 **Rank #{rank}** on leaderboard\n"
        stats_text += f"\n🕐 New puzzle available at midnight UTC!"
    elif user_attempts:
        attempts_used = len(user_attempts)
        remaining = 9 - attempts_used
        stats_text = f"🎮 **Today's Squirdle Progress**\n\n"
        stats_text += f"📊 **Attempts used:** {attempts_used}/9\n"
        stats_text += f"🕹️ **Attempts remaining:** {remaining}\n"
        stats_text += f"\nUse `/guess name:<pokemon>` to continue!"
    else:
        stats_text = f"🎮 **Today's Squirdle**\n\n"
        stats_text += f"📊 **Status:** Not started\n"
        stats_text += f"🕹️ **Attempts available:** 9\n"
        stats_text += f"\nUse `/daily` to start today's puzzle!"
    
    await interaction.response.send_message(stats_text)

@bot.tree.command(name="quit", description="Quit your current Squirdle game!")
async def quit_game(interaction: discord.Interaction):
    user_id = interaction.user.id
    
    if user_id not in active_games:
        await interaction.response.send_message("❌ No active game to quit! Use `/start` to begin a new game.")
        return
    
    if active_games[user_id]["finished"]:
        await interaction.response.send_message("❌ Your game is already finished! Use `/start` to begin a new game.")
        return
    
    # Remove the game
    del active_games[user_id]
    await interaction.response.send_message("👋 Game quit! Use `/start` to begin a new Squirdle game when you're ready!")

if __name__ == "__main__":
    bot.run(TOKEN)
