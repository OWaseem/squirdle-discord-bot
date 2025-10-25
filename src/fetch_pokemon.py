import asyncio
import json
from pathlib import Path
import httpx
from tqdm import tqdm

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = DATA_DIR / "pokemon.json"

POKEAPI = "https://pokeapi.co/api/v2"

GEN_MAP = {
    "generation-i": 1, "generation-ii": 2, "generation-iii": 3,
    "generation-iv": 4, "generation-v": 5, "generation-vi": 6,
    "generation-vii": 7, "generation-viii": 8, "generation-ix": 9
}

def dm_to_m(dm):
    return round(float(dm) / 10.0, 2)

def hg_to_kg(hg):
    return round(float(hg) / 10.0, 1)

async def get_json(client, url):
    resp = await client.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.json()

async def fetch_all_basic_list(client):
    url = f"{POKEAPI}/pokemon?limit=20000"
    data = await get_json(client, url)
    return data["results"]

async def fetch_pokemon_entry(client, url):
    p = await get_json(client, url)
    if not p.get("is_default", True):
        return None

    name = p["name"]
    pokedex = p["id"]
    types = [t["type"]["name"] for t in p["types"]]
    height_m = dm_to_m(p["height"])
    weight_kg = hg_to_kg(p["weight"])

    species = await get_json(client, p["species"]["url"])
    gen_name = species["generation"]["name"]
    generation = GEN_MAP.get(gen_name, None)

    return {
        "name": name,
        "pokedex": pokedex,
        "types": types,
        "height_m": height_m,
        "weight_kg": weight_kg,
        "generation": generation
    }

async def main():
    async with httpx.AsyncClient() as client:
        raw_list = await fetch_all_basic_list(client)
        entries = []
        pbar = tqdm(raw_list, desc="Fetching Pokémon", unit="poke")

        for item in pbar:
            try:
                entry = await fetch_pokemon_entry(client, item["url"])
                if entry:
                    entries.append(entry)
            except Exception:
                continue

        entries = [e for e in entries if e.get("generation")]
        entries.sort(key=lambda x: x["pokedex"])

        with OUTFILE.open("w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

        print(f"Wrote {len(entries)} entries → {OUTFILE}")

if __name__ == "__main__":
    asyncio.run(main())
