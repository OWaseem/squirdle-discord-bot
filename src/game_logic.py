import json
import random

# Load Pokémon data
with open("data/pokemon.json", "r", encoding="utf-8") as f:
    POKEMON_DATA = json.load(f)

def find_pokemon(name):
    """Return the Pokémon dictionary that matches the given name."""
    name = name.lower().strip()
    for p in POKEMON_DATA:
        if p["name"] == name:
            return p
    return None

def compare_pokemon(guess, secret):
    """Compare two Pokémon and return hint strings."""
    results = []

    # Generation
    if guess["generation"] == secret["generation"]:
        results.append("Generation: ✅ same generation")
    elif guess["generation"] > secret["generation"]:
        results.append("Generation: 🔽 secret Pokémon is from an earlier gen")
    else:
        results.append("Generation: 🔼 secret Pokémon is from a later gen")

    # Type match
    type_overlap = set(guess["types"]) & set(secret["types"])
    if type_overlap:
        results.append(f"Type: ✅ shared type(s): {', '.join(type_overlap)}")
    else:
        results.append("Type: ❌ no shared types")

    # Height comparison
    if guess["height_m"] == secret["height_m"]:
        results.append("Height: ✅ same height")
    elif guess["height_m"] > secret["height_m"]:
        results.append("Height: 🔽 secret Pokémon is shorter")
    else:
        results.append("Height: 🔼 secret Pokémon is taller")

    # Weight comparison
    if guess["weight_kg"] == secret["weight_kg"]:
        results.append("Weight: ✅ same weight")
    elif guess["weight_kg"] > secret["weight_kg"]:
        results.append("Weight: 🔽 secret Pokémon is lighter")
    else:
        results.append("Weight: 🔼 secret Pokémon is heavier")

    # Pokédex number comparison
    if guess["pokedex"] == secret["pokedex"]:
        results.append("Pokédex: 🎯 correct Pokémon!")
    elif guess["pokedex"] > secret["pokedex"]:
        results.append("Pokédex: 🔽 secret Pokémon has a lower number")
    else:
        results.append("Pokédex: 🔼 secret Pokémon has a higher number")

    return results

def main():
    # Choose a random secret Pokémon
    secret = random.choice(POKEMON_DATA)
    print("A secret Pokémon has been chosen! You have 9 tries to guess it.\n")

    max_tries = 9
    attempts = 0

    while attempts < max_tries:
        print(f"Attempt {attempts + 1} of {max_tries}")
        guess_name = input("Enter your guess (or 'quit'): ").strip().lower()

        if guess_name == "quit":
            print(f"The secret Pokémon was {secret['name'].title()}.")
            break

        guess = find_pokemon(guess_name)
        if not guess:
            print("❌ Pokémon not found. Try again.\n")
            continue

        attempts += 1
        results = compare_pokemon(guess, secret)

        # Show results for this guess
        print()
        for r in results:
            print(r)
        print()

        # Check if the player guessed correctly
        if guess["name"] == secret["name"]:
            print(f"🎉 You got it in {attempts} tries!")
            break

        # If out of tries, end game
        if attempts == max_tries:
            print(f"❌ Out of tries! The secret Pokémon was {secret['name'].title()}.")
            break

if __name__ == "__main__":
    main()
