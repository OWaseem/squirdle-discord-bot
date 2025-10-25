import os
import random
import json
import discord
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

def find_pokemon(name):
    name = name.lower().strip()
    for p in POKEMON_DATA:
        if p["name"] == name:
            return p
    return None

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()
    print("🌐 Slash commands synced!")

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
        f"🎮 New game started, {interaction.user.name}! You have 9 tries to guess the Pokémon. Use `/guess name:<pokemon>`."
    )

@bot.tree.command(name="guess", description="Guess a Pokémon!")
@app_commands.describe(name="The Pokémon you want to guess")
async def guess(interaction: discord.Interaction, name: str):
    user_id = interaction.user.id

    if user_id not in active_games or active_games[user_id]["finished"]:
        await interaction.response.send_message("❌ No active game! Use `/start` first.")
        return

    game = active_games[user_id]
    secret = game["secret"]
    game["attempts"] += 1
    guess = find_pokemon(name)

    if not guess:
        await interaction.response.send_message("❌ Pokémon not found! Try again.")
        return

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
        game["finished"] = True
    elif guess["pokedex"] > secret["pokedex"]:
        results.append("Pokédex: 🔽 secret is lower")
    else:
        results.append("Pokédex: 🔼 secret is higher")

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

if __name__ == "__main__":
    bot.run(TOKEN)
