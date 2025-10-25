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

    # --- Check bot state ---
    if bot_updating:
        embed = discord.Embed(
            title="🔄 Bot Updating",
            description="Please wait a moment! New features are being deployed.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # --- PERSONAL GAME STATUS ---
    personal_status = "❌ No active personal game"
    last_personal_guess = None

    if user_id in active_games and not active_games[user_id]["finished"]:
        game = active_games[user_id]
        attempts_used = game["attempts"]
        remaining = game["max_tries"] - attempts_used
        personal_status = f"🎮 Active — {remaining} tries left"

        # Add last guess info if available
        if "guesses" in game and game["guesses"]:
            last_personal_guess = game["guesses"][-1]

    # --- DAILY GAME STATUS ---
    user_attempts = len(daily_game["attempts"].get(user_id, []))
    daily_remaining = 9 - user_attempts
    last_daily_guess = None

    if user_id in daily_game["completions"]:
        daily_status = "✅ Completed!"
    elif user_attempts >= 9:
        daily_status = "❌ Out of tries!"
    elif user_attempts > 0:
        daily_status = f"🕹️ In progress — {daily_remaining} tries left"
        # Add last daily guess info
        if user_id in daily_game["attempts"] and daily_game["attempts"][user_id]:
            last_daily_guess = daily_game["attempts"][user_id][-1]
    else:
        daily_status = "💤 Not started yet"

    # --- EMBED LAYOUT ---
    embed = discord.Embed(
        title="🧩 Squirdle Bot Status",
        color=discord.Color.green()
    )
    embed.add_field(name="🟢 Bot Status", value="Online and ready!", inline=False)
    embed.add_field(name="📅 Daily Game", value=daily_status, inline=False)
    embed.add_field(name="🎮 Personal Game", value=personal_status, inline=False)

    # --- Add short last guess summary ---
    if last_daily_guess or last_personal_guess:
        summary = ""
        if last_daily_guess:
            summary += f"📅 **Last Daily Guess:** {last_daily_guess.title()}\n"
        if last_personal_guess:
            summary += f"🎮 **Last Personal Guess:** {last_personal_guess.title()}\n"
        embed.add_field(
            name="🔍 Recent Guess Summary",
            value=summary.strip(),
            inline=False
        )

    embed.set_footer(text="💡 Use /stats for detailed hint breakdowns and progress.")
    await interaction.response.send_message(embed=embed, ephemeral=True)



@bot.tree.command(name="help", description="Learn how to play Squirdle!")
async def help_command(interaction: discord.Interaction):
    help_text = """🎮 **Welcome to Squirdle — the Pokémon Wordle Game!**

Guess the secret Pokémon using clues about its **generation**, **type**, **height**, **weight**, and **Pokédex number**.  
You have **9 tries** per game — choose wisely, Trainer! ⚡

---

### 🧩 **Commands**
• `/start` — Begin a new **personal game** (private to you).  
• `/daily` — Play today’s **shared daily puzzle** (same Pokémon for everyone).  
• `/guess` — Make a guess in your current game *(all guesses and hints are private)*.  
• `/stats` — View detailed stats for **both** your daily and personal games, including your **last guess breakdown**.  
• `/status` — Check your current game progress for both modes.  
• `/leaderboard` — See today’s top solvers (public), with your personal rank shown privately.  
• `/quit` — Quit your personal game at any time.  
• `/help` — Display this guide.  

---

### 📅 **Game Modes**
🟢 **Daily Mode**
- Everyone plays the same Pokémon each day.
- You can start or continue it anytime with `/daily`.  
- Progress is saved automatically until midnight (EDT).  
- Your guesses and results are **private**.  
- The daily Pokémon is revealed only to you after completion or 9 failed tries.  
- You can play the daily and personal games **at the same time** — progress is tracked separately!

🔵 **Personal Mode**
- A fully **private** game unique to you.  
- You can play it alongside your daily puzzle.  
- Progress, hints, and results are visible **only to you**.  
- You can quit at any time with `/quit`.  

---

### 💡 **Hints You’ll Receive**
Each guess provides feedback about:  
- **Generation** → earlier / later / same  
- **Type** → shared or none in common  
- **Height** → taller / shorter / same  
- **Weight** → heavier / lighter / same  
- **Pokédex** → higher / lower / same  

---

### 🔒 **Privacy & Visibility**
- All commands marked *(private)* send **ephemeral messages**, visible only to you.  
- `/leaderboard` is public for everyone to see, but your detailed rank and Pokémon reveal stay private.  
- You can safely play in any channel without spoiling the answer for others.

---

### 🧠 **Tips for Trainers**
• Use Pokémon autocomplete when guessing.  
• Track clues logically to narrow down your options.  
• Daily Pokémon resets automatically every midnight (EDT).  
• You can play both modes anytime — they won’t interfere!  

Good luck, Trainer — your Pokédex mastery awaits! 🏆
"""
    await interaction.response.send_message(help_text, ephemeral=True)



# -------------------- DAILY GAME --------------------
@bot.tree.command(name="daily", description="Start today's Squirdle - same for everyone!")
async def daily(interaction: discord.Interaction):
    global daily_game
    user_id = interaction.user.id
    initialize_daily_game()

    # --- Start or resume daily game without touching personal game ---
    await interaction.response.send_message(
        f"🎮 Starting today's Squirdle! You can keep playing your personal game alongside this one.\n\n"
        f"Use `/guess name:<pokemon>` to make your first guess.\n"
        f"💡 Use `/leaderboard` to see today's fastest solvers!"
)

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
@bot.tree.command(name="start", description="Start a new personal Squirdle game!")
async def start(interaction: discord.Interaction):
    user_id = interaction.user.id

    # Check if user already has an active game
    if user_id in active_games and not active_games[user_id]["finished"]:
        secret_name = active_games[user_id]["secret"]["name"].title()
        await interaction.response.send_message(
            f"⚠️ You already have an active personal game in progress!\n"
            f"Do you want to end it and start a new one?\n\n"
            f"🕹️ Current game's secret Pokémon: **{secret_name}** (hidden until you quit or finish)",
            ephemeral=True
        )
        return

    # Start new game if none active
    secret = random.choice(POKEMON_DATA)
    active_games[user_id] = {
        "secret": secret,
        "attempts": 0,
        "max_tries": 9,
        "finished": False
    }

    await interaction.response.send_message(
        f"🎮 New personal game started, {interaction.user.name}!\n"
        f"You have **9 tries** to guess the Pokémon.\n\n"
        f"Use `/guess name:<pokemon>` to make your first guess.\n"
        f"💡 Use `/help` to learn how to play.\n"
        f"🛑 Use `/quit` anytime to end your game and reveal the Pokémon.",
        ephemeral=True
    )


@bot.tree.command(name="quit", description="Quit your current personal Squirdle game")
async def quit_personal(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in active_games and not active_games[user_id]["finished"]:
        secret_name = active_games[user_id]["secret"]["name"].title()
        del active_games[user_id]
        await interaction.response.send_message(
            f"🛑 You ended your personal game.\n"
            f"The secret Pokémon was **{secret_name}**! 🔍\n\n"
            f"Use `/start` anytime to begin a new challenge.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "ℹ️ You don't have an active personal game right now. Use `/start` to begin one!",
            ephemeral=True
        )


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
            await interaction.response.send_message("❌ Pokémon not found! Try again.", ephemeral=True)
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
        await interaction.response.send_message("❌ You've used all 9 attempts for today's Squirdle! New puzzle available at midnight EDT.", ephemeral=True)
        return

    guess_data = find_pokemon(name)
    if not guess_data:
        await interaction.response.send_message("❌ Pokémon not found! Try again.", ephemeral=True)
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

    await interaction.response.send_message(msg, ephemeral=True)


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
    global daily_game, active_games
    user_id = interaction.user.id
    initialize_daily_game()

    # --- DAILY STATS ---
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

    # --- Add Last Guess Summary for Daily Game ---
    if attempts > 0 and user_id in daily_game["attempts"]:
        last_guess = daily_game["attempts"][user_id][-1]
        if "hints" in daily_game and user_id in daily_game["hints"]:
            daily_hints = daily_game["hints"][user_id].get(last_guess, None)
            if daily_hints:
                daily_details += "\n\n🔍 **Last Daily Guess Summary**\n"
                daily_details += f"• Pokémon: **{last_guess.title()}**\n"
                daily_details += f"• Generation Hint: {daily_hints.get('generation_hint', '—')}\n"
                daily_details += f"• Type Hint: {daily_hints.get('type_hint', '—')}\n"
                daily_details += f"• Height Hint: {daily_hints.get('height_hint', '—')}\n"
                daily_details += f"• Weight Hint: {daily_hints.get('weight_hint', '—')}\n"
                daily_details += f"• Pokédex Hint: {daily_hints.get('pokedex_hint', '—')}\n"

    # --- PERSONAL GAME STATS ---
    if user_id in active_games and not active_games[user_id]["finished"]:
        game = active_games[user_id]
        personal_details = (
            f"**Attempts used:** {game['attempts']}/{game['max_tries']}\n"
            f"**Tries remaining:** {game['max_tries'] - game['attempts']}"
        )

        # Add last guess info if available
        if "guesses" in game and game["guesses"]:
            last_guess = game["guesses"][-1]
            last_hints = game.get("hints", {}).get(last_guess, None)
            if last_hints:
                personal_details += "\n\n🔍 **Last Personal Guess Summary**\n"
                personal_details += f"• Pokémon: **{last_guess.title()}**\n"
                personal_details += f"• Generation Hint: {last_hints.get('generation_hint', '—')}\n"
                personal_details += f"• Type Hint: {last_hints.get('type_hint', '—')}\n"
                personal_details += f"• Height Hint: {last_hints.get('height_hint', '—')}\n"
                personal_details += f"• Weight Hint: {last_hints.get('weight_hint', '—')}\n"
                personal_details += f"• Pokédex Hint: {last_hints.get('pokedex_hint', '—')}\n"
    else:
        personal_details = "No active personal game."

    # --- EMBED LAYOUT ---
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
