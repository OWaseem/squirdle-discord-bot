import os
import random
import json
import discord
import signal
import sys
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
active_games = {}
bot_updating = False  # Track if bot is updating

def find_pokemon(name):
    name = name.lower().strip()
    for p in POKEMON_DATA:
        if p["name"] == name:
            return p
    return None

@bot.event
async def on_ready():
    global bot_updating
    bot_updating = False  # Bot is back online
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()
    print("🌐 Slash commands synced!")

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
        f"🎮 New game started, {interaction.user.name}! You have 9 tries to guess the Pokémon. Use `/guess name:<pokemon>` - don't worry about spelling, I'll show you the correct name!\n\n💡 Use `/status` to check if the bot is working!\n🛑 Use `/quit` to exit your current game!"
    )

@bot.tree.command(name="guess", description="Guess a Pokémon!")
@app_commands.describe(name="The Pokémon you want to guess")
@app_commands.autocomplete(name=async def pokemon_autocomplete(
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
)
async def guess(interaction: discord.Interaction, name: str):
    user_id = interaction.user.id

    if user_id not in active_games or active_games[user_id]["finished"]:
        await interaction.response.send_message("❌ No active game! Use `/start` first.")
        return

    game = active_games[user_id]
    secret = game["secret"]
    guess = find_pokemon(name)

    if not guess:
        await interaction.response.send_message("❌ Pokémon not found! Try again.")
        return
    
    # Only increment attempts for valid Pokémon guesses
    game["attempts"] += 1
    
    # Auto-provide the Pokémon name for reference
    guess_name = guess["name"].title()

    results = []
    
    # Show the Pokémon name they guessed
    results.append(f"**{guess_name}**")

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
        game["finished"] = True
    elif guess["pokedex"] > secret["pokedex"]:
        results.append("Pokédex: 🔽 secret has a lower number")
    else:
        results.append("Pokédex: 🔼 secret has a higher number")

    msg = "\n".join(results)
    if game["finished"]:
        msg += f"\n🎊 You got it in {game['attempts']} tries!"
    elif game["attempts"] >= game["max_tries"]:
        msg += f"\n❌ Out of tries! The Pokémon was **{secret['name'].title()}**."
        game["finished"] = True
    else:
        remaining = game["max_tries"] - game["attempts"]
        msg += f"\n🕹️ {remaining} tries left."

    await interaction.response.send_message(msg)

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
