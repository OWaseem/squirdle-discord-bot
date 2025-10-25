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
    global bot_updating, daily_game
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

    # --- Personal game state ---
    personal_status = "❌ No active personal game"
    if user_id in active_games and not active_games[user_id]["finished"]:
        attempts_used = active_games[user_id]["attempts"]
        remaining = active_games[user_id]["max_tries"] - attempts_used
        personal_status = f"🎮 Active — {remaining} tries left"

    # --- Daily game state ---
    user_attempts = len(daily_game["attempts"].get(user_id, []))
    daily_remaining = 9 - user_attempts
    if user_id in daily_game["completions"]:
        daily_status = "✅ Completed!"
    elif user_attempts >= 9:
        daily_status = "❌ Out of tries!"
    elif user_attempts > 0:
        daily_status = f"🕹️ In progress — {daily_remaining} tries left"
    else:
        daily_status = "💤 Not started yet"

    # --- Embed layout ---
    embed = discord.Embed(
        title="🧩 Squirdle Bot Status",
        color=discord.Color.green()
    )
    embed.add_field(name="🟢 Bot Status", value="Online and ready!", inline=False)
    embed.add_field(name="📅 Daily Game", value=daily_status, inline=False)
    embed.add_field(name="🎮 Personal Game", value=personal_status, inline=False)
    embed.set_footer(text="💡 Use /help for all commands")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="help", description="Learn how to play Squirdle!")
async def help_command(interaction: discord.Interaction):
    help_text = """🎮 **How to Play Squirdle**

**Commands:**
• `/start` — Start a personal Squirdle (your own random Pokémon)
• `/daily` — Play today's shared Squirdle (same for everyone!)
• `/guess` — Make a guess in your active game
• `/leaderboard` — See today's fastest solvers
• `/stats` — View your daily game stats
• `/quit` — Quit your personal game
• `/status` — Check if the bot is working
• `/help` — Show this guide

---

**Game Rules:**
1. You have **9 tries** to guess the secret Pokémon in either mode.
2. Each guess gives you hints about:
   - **Generation:** Earlier / later / same generation  
   - **Type:** Shared types or none in common  
   - **Height:** Taller / shorter / same height  
   - **Weight:** Heavier / lighter / same weight  
   - **Pokédex Number:** Higher / lower / same number
3. If you run out of 9 tries, the game ends and reveals the Pokémon.

---

**Modes:**
🟢 **Daily Mode**
- Everyone plays the same Pokémon of the day.
- You can leave and come back anytime — progress is saved automatically.
- Resets each midnight (EDT).  
- Shows your completion time on the **leaderboard**.

🔵 **Personal Mode**
- Your own private game with a random Pokémon.
- Can be quit anytime with `/quit`.
- If you start the daily while in a personal game, your personal one will automatically end and show its answer.

---

**Tips:**
• Use the Pokémon name auto-complete when guessing.  
• Think logically: compare each hint before guessing again.  
• New daily available every midnight (EDT).  

Good luck, Trainer! 🍀
"""
    await interaction.response.send_message(help_text)


# -------------------- DAILY GAME --------------------
@bot.tree.command(name="daily", description="Start today's Squirdle - same for everyone!")
async def daily(interaction: discord.Interaction):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    # --- Auto-close any active personal game before starting daily ---
    if user_id in active_games and not active_games[user_id]["finished"]:
        personal_secret = active_games[user_id]["secret"]["name"].title()
        del active_games[user_id]
        await interaction.response.send_message(
            f"🛑 You had an unfinished personal Squirdle game.\n"
            f"The secret Pokémon was **{personal_secret}**!\n\n"
            f"🎮 Starting today's Squirdle now..."
        )
        await interaction.followup.send(
            f"🎮 Welcome to today's Squirdle! You have 9 tries to guess the secret Pokémon.\n\n"
            f"Use `/guess name:<pokemon>` to make your first guess!\n"
            f"💡 Use `/leaderboard` to see today's fastest solvers!"
        )
        return

    # If already solved
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

    # Normal entry messages
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


# -------------------- PERSONAL GAME --------------------
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
    f"💡 Use `/help` to learn how to play!\n🛑 Use `/quit` to exit your current game!",
    ephemeral=True
)


@bot.tree.command(name="quit", description="Quit your current individual game")
async def quit_personal(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in active_games and not active_games[user_id]["finished"]:
        del active_games[user_id]
        await interaction.response.send_message("🛑 Your individual game has been ended.", ephemeral=True)
    else:
        await interaction.response.send_message("ℹ️ You don't have an active individual game.", ephemeral=True)


# -------------------- AUTOCOMPLETE --------------------
async def pokemon_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    matches = []
    current_lower = current.lower()
    for p in POKEMON_DATA:
        if current_lower in p["name"].lower():
            matches.append(app_commands.Choice(name=p["name"].title(), value=p["name"]))
            if len(matches) >= 25:  # Discord limit
                break
    return matches


# -------------------- GUESS (auto-detect mode) --------------------
@bot.tree.command(name="guess", description="Make a guess in your current Squirdle game!")
@app_commands.describe(name="The Pokémon you want to guess")
@app_commands.autocomplete(name=pokemon_autocomplete)
async def guess(interaction: discord.Interaction, name: str):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    # PERSONAL GAME takes precedence
    if user_id in active_games and not active_games[user_id]["finished"]:
        game = active_games[user_id]

        guess_data = find_pokemon(name)
        if not guess_data:
            await interaction.response.send_message("❌ Pokémon not found! Try again.")
            return

        game["attempts"] += 1
        attempts_left = game["max_tries"] - game["attempts"]
        secret = game["secret"]

        results = compare_and_build_message(guess_data, secret)

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

        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # DAILY GAME
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
        msg = "\n".join(results)
        msg += f"\n🎊 You solved today's Squirdle in {len(user_attempts)} tries!"
    else:
        if guess_data["pokedex"] > secret["pokedex"]:
            results.append("Pokédex: 🔽 secret has a lower number")
        else:
            results.append("Pokédex: 🔼 secret has a higher number")

        if len(user_attempts) >= 9:
            results.append(f"❌ Out of tries! Today's Pokémon was **{secret['name'].title()}**.")
        else:
            remaining = 9 - len(user_attempts)
            results.append(f"🕹️ {remaining} tries left.")

        msg = "\n".join(results)

    await interaction.response.send_message(msg)


# -------------------- LEADERBOARD / STATS (daily) --------------------
@bot.tree.command(name="leaderboard", description="See today's fastest Squirdle solvers!")
async def leaderboard(interaction: discord.Interaction):
    global daily_game
    initialize_daily_game()
    user_id = interaction.user.id

    # --- No completions yet ---
    if not daily_game["leaderboard"]:
        embed = discord.Embed(
            title="🏆 Today's Squirdle Leaderboard",
            description="No one has solved today's Squirdle yet!\nBe the first to make it on the board! 💪",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="💡 Use /daily to start playing!")
        await interaction.response.send_message(embed=embed)
        return

    # --- Sort leaderboard by attempts then completion time ---
    daily_game["leaderboard"].sort(key=lambda x: (x["attempts"], x["completion_time"]))

    # --- Build top 10 entries ---
    leaderboard_lines = []
    for i, entry in enumerate(daily_game["leaderboard"][:10], 1):
        rank_emoji = (
            "🥇" if i == 1 else
            "🥈" if i == 2 else
            "🥉" if i == 3 else
            f"{i}️⃣"
        )
        time_str = entry["completion_time"].strftime("%H:%M EDT")
        leaderboard_lines.append(
            f"{rank_emoji} **{entry['username']}** — {entry['attempts']} tries ({time_str})"
        )

    description = "\n".join(leaderboard_lines)

    # --- Add note for extra solvers ---
    extra = len(daily_game["leaderboard"]) - 10
    if extra > 0:
        description += f"\n\n...and **{extra}** more trainers are on the board!"

    # --- Create public leaderboard embed ---
    public_embed = discord.Embed(
        title="🏆 Today's Squirdle Leaderboard",
        description=description,
        color=discord.Color.gold()
    )
    public_embed.set_footer(text="💡 The leaderboard resets daily at midnight (EDT).")

    # --- Send the public leaderboard embed ---
    await interaction.response.send_message(embed=public_embed)

    # --- Personal details (private follow-up) ---
    user_rank = None
    user_attempts = None
    for i, entry in enumerate(daily_game["leaderboard"], 1):
        if entry["user_id"] == user_id:
            user_rank = i
            user_attempts = entry["attempts"]
            break

    # --- Private embed (ephemeral) ---
    if user_rank:
        daily_pokemon_name = daily_game["pokemon"]["name"].title()
        if user_rank <= 10:
            desc = (
                f"You're currently **#{user_rank}** with **{user_attempts}** tries — amazing work! 💪\n"
                f"Today's secret Pokémon was **{daily_pokemon_name}** 🐾"
            )
        else:
            desc = (
                f"You're currently **#{user_rank}** with **{user_attempts}** tries.\n"
                f"Keep training to make the top 10! 🔥\n"
                f"Today's secret Pokémon was **{daily_pokemon_name}** 🐾"
            )
        private_embed = discord.Embed(
            title="🔒 Your Personal Squirdle Summary",
            description=desc,
            color=discord.Color.green()
        )
        private_embed.set_footer(text="This message is private and visible only to you.")
        await interaction.followup.send(embed=private_embed, ephemeral=True)
    else:
        private_embed = discord.Embed(
            title="🔒 Your Personal Squirdle Summary",
            description="You haven’t solved today’s Squirdle yet!\nUse `/daily` to play and earn your spot 🕹️",
            color=discord.Color.orange()
        )
        private_embed.set_footer(text="This message is private and visible only to you.")
        await interaction.followup.send(embed=private_embed, ephemeral=True)


@bot.tree.command(name="stats", description="View your personal and daily Squirdle statistics!")
async def stats(interaction: discord.Interaction):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    # --- Daily Stats ---
    attempts = len(daily_game["attempts"].get(user_id, []))
    solved = user_id in daily_game["completions"]

    if solved:
        completion_time = daily_game["completions"][user_id].strftime("%H:%M EDT")
        daily_title = "✅ Daily Game — Solved!"
        daily_details = f"**Attempts used:** {attempts}\n**Completion time:** {completion_time}"
        color = discord.Color.green()
    elif attempts >= 9:
        daily_title = "❌ Daily Game — Out of Tries!"
        daily_details = f"**Attempts used:** {attempts}/9"
        color = discord.Color.red()
    elif attempts > 0:
        remaining = 9 - attempts
        daily_title = "🕹️ Daily Game — In Progress"
        daily_details = f"**Attempts used:** {attempts}/9\n**Tries remaining:** {remaining}"
        color = discord.Color.orange()
    else:
        daily_title = "💤 Daily Game — Not Started"
        daily_details = "Use `/daily` to begin!"
        color = discord.Color.blurple()

    # --- Personal Stats ---
    if user_id in active_games and not active_games[user_id]["finished"]:
        game = active_games[user_id]
        personal_details = (
            f"**Attempts used:** {game['attempts']}/{game['max_tries']}\n"
            f"**Tries remaining:** {game['max_tries'] - game['attempts']}"
        )
    else:
        personal_details = "No active personal game."

    # --- Embed layout ---
    embed = discord.Embed(
        title="📊 Your Squirdle Stats",
        color=color
    )
    embed.add_field(name=daily_title, value=daily_details, inline=False)
    embed.add_field(name="🎮 Personal Game", value=personal_details, inline=False)
    embed.set_footer(text="🏆 Use /leaderboard to see today's top solvers!")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# KEEP-ALIVE + RUN
# =========================================================
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
