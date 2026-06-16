#!/usr/bin/env python3
"""
URS Commissar Bot v2.0 - Tactical War Intelligence & Economic Audit Engine
Aesthetic: Soviet / Marxist-Leninist Vanguard
"""

import os
import asyncio
import logging
import sqlite3
import math
import random
from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION & ENVIRONMENT ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PANDW_API_KEY = os.getenv("P_AND_W_API_KEY")
YOUR_SERVER_ID = int(os.getenv("YOUR_SERVER_ID", "1428154519266656278"))
ALLIANCE_ID = 14873
GRAPHQL_URL = "https://api.politicsandwar.com/graphql"
PORT = int(os.getenv("PORT", 8080))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("urs-commissar")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
DB_FILE = "urs_state.db"

# --- HTTP SERVER FOR RENDER ---
async def health_check(request):
    return web.Response(text="☭ URS Commissar Online", status=200)

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"☭ HTTP server listening on port {PORT}")

# --- DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registration (
            discord_id INTEGER PRIMARY KEY,
            nation_id INTEGER UNIQUE,
            leader_name TEXT,
            nation_name TEXT
        )
    """)
    conn.commit()
    conn.close()

# --- P&W GRAPHQL API CLIENT ---
async def fetch_pw_api(query: str, variables: dict = None):
    headers = {
        "X-Api-Key": PANDW_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"query": query, "variables": variables or {}}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GRAPHQL_URL, json=payload, headers=headers, timeout=15) as response:
                if response.status != 200:
                    raw_err = await response.text()
                    raise RuntimeError(f"API Error {response.status}: {raw_err}")
                data = await response.json()
                if "errors" in data:
                    raise RuntimeError(f"GraphQL Error: {data['errors']}")
                return data.get("data", {})
        except Exception as e:
            logger.error(f"API Communication breakdown: {str(e)}")
            raise

# --- CORE MILITARY CONSTANTS & UTILS ---
MILITARY_CAPS = {
    "soldiers_per_city": 15000,
    "tanks_per_city": 1250,
    "aircraft_per_city": 75,
    "ships_per_city": 15
}

def chunk_text(text, max_chars=1800):
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0
    for line in lines:
        if current_length + len(line) + 1 > max_chars:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks

def calculate_combat_value(unit_type, count, supplied=True):
    if count <= 0: return 0.0
    if not supplied and unit_type in ["tanks", "aircraft", "ships"]: return 0.0
    base_values = {"soldiers": 1.75, "tanks": 40.0, "aircraft": 80.0, "ships": 120.0}
    return float(count * base_values.get(unit_type, 1.0))

def run_3_roll_simulation(attacker_cv, defender_cv, air_superiority=False, is_tank=False):
    if defender_cv <= 0: return "IMMENSE TRIUMPH", 0.0
    if is_tank and air_superiority: defender_cv *= 0.5
    att_rolls = sum([random.uniform(0.4, 1.0) * attacker_cv for _ in range(3)])
    def_rolls = sum([random.uniform(0.4, 1.0) * defender_cv for _ in range(3)])
    ratio = att_rolls / (def_rolls if def_rolls > 0 else 1.0)
    
    if ratio >= 1.75: return "IMMENSE TRIUMPH", ratio
    elif ratio >= 1.25: return "MAJOR VICTORY", ratio
    elif ratio >= 0.85: return "VICTORY", ratio
    else: return "DEFEAT", ratio

def generate_precise_tactical_sequence(attacker, defender):
    plan = []
    steps = 1
    air_sup = False
    
    if defender["aircraft"] > 0 and attacker["aircraft"] > 0:
        plan.append(f"**Step {steps}: Operations in the Sky**\n  ↳ Deploy {attacker['aircraft']} Aircraft on Dogfight sweeps to break Air Superiority.")
        steps += 1
        air_sup = True

    if defender["ships"] > 0 and attacker["ships"] > 0:
        plan.append(f"**Step {steps}: Global Market Isolation**\n  ↳ Execute Naval Blockade using {attacker['ships']} Ships.")
        steps += 1

    rem_resistance = 100
    ground_hits = 0
    while rem_resistance > 10 and ground_hits < 4:
        outcome, _ = run_3_roll_simulation(
            calculate_combat_value("soldiers", attacker["soldiers"]) + calculate_combat_value("tanks", attacker["tanks"]),
            calculate_combat_value("soldiers", defender["soldiers"]) + calculate_combat_value("tanks", defender["tanks"], air_superiority=air_sup),
            air_superiority=air_sup, is_tank=True
        )
        if outcome in ["IMMENSE TRIUMPH", "MAJOR VICTORY"]:
            plan.append(f"**Step {steps}: Ground Operation {ground_hits + 1}**\n  ↳ Launch Ground Assault. Result: **{outcome}** (-10 Resistance).")
            rem_resistance -= 10
            ground_hits += 1
            steps += 1
        else: break

    plan.append(f"**Step {steps}: The Ultimatum**\n  ↳ Deliver final Ground Strike to drop resistance to 0 and secure Beige loot.")
    return "\n".join(plan)

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    logger.info(f"☭ Commissar {bot.user} has assumed operational command.")
    guild_obj = discord.Object(id=YOUR_SERVER_ID)
    bot.tree.copy_global_to(guild=guild_obj)
    await bot.tree.sync(guild=guild_obj)
    logger.info(f"⭐ Directives securely mapped to server frame: {YOUR_SERVER_ID}")

# --- COMMANDS ---

@bot.tree.command(name="status", description="Show bot status")
@app_commands.guilds(discord.Object(id=YOUR_SERVER_ID))
async def status(interaction: discord.Interaction):
    await interaction.response.send_message(f"☭ **URS Commissar Online**\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

@bot.tree.command(name="register", description="Bind your physical state parameters to your Discord profile.")
@app_commands.describe(nation_id="Your unique numerical P&W nation ID string.")
@app_commands.guilds(discord.Object(id=YOUR_SERVER_ID))
async def register(interaction: discord.Interaction, nation_id: int):
    await interaction.response.defer(ephemeral=True)
    query = 'query ($id: ID!) { nation(id: $id) { leader_name, name, alliance_id } }'
    try:
        data = await fetch_pw_api(query, {"id": nation_id})
        nation = data.get("nation")
        if not nation: return await interaction.followup.send("❌ Target state profile could not be discovered.")
        if nation["alliance_id"] != str(ALLIANCE_ID): return await interaction.followup.send(f"❌ State belongs to alliance [{nation['alliance_id']}]. Must reside inside URS [14873].")
            
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT OR REPLACE INTO registration (discord_id, nation_id, leader_name, nation_name) VALUES (?, ?, ?, ?)", 
                     (interaction.user.id, nation_id, nation["leader_name"], nation["name"]))
        conn.commit()
        conn.close()
        await interaction.followup.send(f"✅ **Registration Locked!** Tied to: **{nation['leader_name']} ({nation['name']})**.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failure: {str(e)}")

@bot.tree.command(name="mobilize", description="Execute inventory diagnostics for all active Frontline Comrades.")
@app_commands.guilds(discord.Object(id=YOUR_SERVER_ID))
async def mobilize(interaction: discord.Interaction):
    await interaction.response.defer()
    query = 'query ($id: ID!) { alliance(id: $id) { nations { leader_name, name, cities { id }, soldiers, tanks, aircraft, ships, money, steel, aluminum } } }'
    try:
        data = await fetch_pw_api(query, {"id": ALLIANCE_ID})
        nations = data.get("alliance", {}).get("nations", [])
        if not nations: return await interaction.followup.send("❌ No citizens registered.")
            
        output_buffer = ["☭ **PEOPLE'S MOBILIZATION DIRECTIVE** ☭\n"]
        total_deficients = 0
        
        for nation in nations:
            city_count = len(nation["cities"])
            max_sol = city_count * MILITARY_CAPS["soldiers_per_city"]
            max_tnk = city_count * MILITARY_CAPS["tanks_per_city"]
            max_air = city_count * MILITARY_CAPS["aircraft_per_city"]
            max_shp = city_count * MILITARY_CAPS["ships_per_city"]
            
            s_def = max(0, max_sol - nation["soldiers"])
            t_def = max(0, max_tnk - nation["tanks"])
            a_def = max(0, max_air - nation["aircraft"])
            sh_def = max(0, max_shp - nation["ships"])
            
            if s_def > 0 or t_def > 0 or a_def > 0 or sh_def > 0:
                total_deficients += 1
                output_buffer.append(
                    f"⛑️ **Comrade {nation['leader_name']}** ({nation['name']}) — 🏙️ {city_count} Cities\n"
                    f" ┣ 🪖 Soldiers: {nation['soldiers']:,} / {max_sol:,} *(need +{s_def:,})*\n"
                    f" ┣ 🛡️ Tanks:    {nation['tanks']:,} / {max_tnk:,} *(need +{t_def:,})*\n"
                    f" ┣ ✈️ Aircraft: {nation['aircraft']:,} / {max_air:,} *(need +{a_def:,})*\n"
                    f" ┣ 🚢 Ships:    {nation['ships']:,} / {max_shp:,} *(need +{sh_def:,})*\n"
                    f" ┗ 💵 ${nation['money']:,.2f} | ⚙️ {nation['steel']:,}t Steel | 🔩 {nation['aluminum']:,}t Alum\n"
                )
        
        if total_deficients == 0: return await interaction.followup.send("⭐ **THE PEOPLE'S ARMY STANDS FULLY MOBILIZED!**")
        for i, chunk in enumerate(chunk_text("\n".join(output_buffer))):
            await interaction.followup.send(chunk) if i == 0 else await interaction.channel.send(chunk)
    except Exception as e:
        await interaction.followup.send(f"❌ Failure: {str(e)}")

@bot.tree.command(name="grant", description="Calculate material allocations needed to plug production deficits.")
@app_commands.guilds(discord.Object(id=YOUR_SERVER_ID))
async def grant(interaction: discord.Interaction, soldiers: int=0, tanks: int=0, aircraft: int=0, ships: int=0):
    cash = (soldiers * 121.25) + (tanks * 1487.50) + (aircraft * 4850.00) + (ships * 24250.00)
    steel, alum = (tanks * 0.50) + (ships * 25.00), (aircraft * 5.00) + (ships * 5.00)
    embed = discord.Embed(title="☭ REVOLUTIONARY RESOURCE ALLOCATION ☭", color=discord.Color.red())
    embed.add_field(name="Required Materials", value=f"💵 ${cash:,.2f} | ⚙️ {steel:,}t Steel | 🔩 {alum:,}t Alum", inline=False)
    embed.add_field(name="🏦 PASTE INTO ALLIANCE TREASURY", value=f"
http://googleusercontent.com/immersive_entry_chip/0

