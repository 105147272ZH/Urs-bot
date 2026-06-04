#!/usr/bin/env python3
"""
Urs Commissar Bot - Precision War Strategy Engine for Politics & War
Builds custom attack sequences per war based on 3-roll damage simulation.
"""

import os
import json
import math
import asyncio
import logging
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime

load_dotenv()

# Config
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
P_AND_W_API_KEY = os.getenv("P_AND_W_API_KEY")
YOUR_SERVER_ID = int(os.getenv("YOUR_SERVER_ID", "1428154519266656278"))
PANDW_NATION_ID = 634658
PANDW_ALLIANCE_ID = 14873
PANDW_BASE = "https://politicsandwar.com/api"

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("urs-commissar")

# Enable all intents
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================================
# P&W API Helper - DEBUG MODE
# ============================================================================

async def pandw_query(session: aiohttp.ClientSession, query: str, variables: dict = None):
    """Execute GraphQL query against P&W API with debug logging."""
    url = f"{PANDW_BASE}/graphql"
    payload = {
        "query": query,
        "variables": variables or {}
    }
    headers = {"Authorization": f"Bearer {P_AND_W_API_KEY}"}
    
    logger.debug(f"Sending request to {url}")
    logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
    logger.debug(f"Headers: {headers}")
    
    async with session.post(url, json=payload, headers=headers) as resp:
        logger.debug(f"Response status: {resp.status}")
        text = await resp.text()
        logger.debug(f"Response body (first 500 chars): {text[:500]}")
        
        if resp.status != 200:
            logger.error(f"P&W API error {resp.status}: {text}")
            raise RuntimeError(f"P&W API {resp.status}: {text}")
        
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Response was: {text}")
            raise RuntimeError(f"Invalid JSON response: {e}")
        
        if "errors" in data:
            logger.error(f"GraphQL errors: {data['errors']}")
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        
        return data.get("data", {})

# ============================================================================
# War Strategy Engine - 3-Roll Combat Simulator
# ============================================================================

class WarAnalyzer:
    """Analyzes a single war and builds custom attack sequence."""
    
    def __init__(self, war_data: dict, attacker_data: dict, defender_data: dict):
        self.war = war_data
        self.attacker = attacker_data
        self.defender = defender_data
        
        # Current war state
        self.attacker_resistance = war_data.get("attacker_resistance", 100)
        self.defender_resistance = war_data.get("defender_resistance", 100)
        self.attacker_map = war_data.get("attacker_map", 0)
        self.defender_map = war_data.get("defender_map", 0)
        self.ground_control = war_data.get("ground_control", "")
        self.air_superiority = war_data.get("air_superiority", "")
        self.naval_blockade = war_data.get("naval_blockade", "")
        
        # Defender military (exact counts)
        self.def_soldiers = defender_data.get("soldiers", 0)
        self.def_tanks = defender_data.get("tanks", 0)
        self.def_aircraft = defender_data.get("aircraft", 0)
        self.def_ships = defender_data.get("ships", 0)
        
        # Attacker military (exact counts)
        self.att_soldiers = attacker_data.get("soldiers", 0)
        self.att_tanks = attacker_data.get("tanks", 0)
        self.att_aircraft = attacker_data.get("aircraft", 0)
        self.att_ships = attacker_data.get("ships", 0)
    
    def combat_value(self, soldiers: int, tanks: int, aircraft: int, ships: int, 
                     has_munitions: bool = True, has_gasoline: bool = True) -> float:
        """Calculate combat value for a unit set (40%-100% bracket system)."""
        cv = 0.0
        if soldiers > 0:
            soldier_cv = 1.75 if has_munitions else 1.0
            cv += soldiers * soldier_cv
        if tanks > 0 and has_munitions and has_gasoline:
            cv += tanks * 1.0
        cv += aircraft * 1.0
        cv += ships * 1.0
        return cv
    
    def simulate_battle(self, att_soldiers: int, att_tanks: int, att_aircraft: int, att_ships: int,
                        def_soldiers: int, def_tanks: int, def_aircraft: int, def_ships: int,
                        scenario: str = "average") -> Dict:
        """Simulate a single battle with 3-roll system."""
        att_cv = self.combat_value(att_soldiers, att_tanks, att_aircraft, att_ships, True, True)
        def_cv = self.combat_value(def_soldiers, def_tanks, def_aircraft, def_ships, True, True)
        
        if self.air_superiority == "Attacker":
            def_cv *= 0.5
        
        if scenario == "worst":
            att_roll = 0.40
            def_roll = 1.00
        elif scenario == "best":
            att_roll = 1.00
            def_roll = 0.40
        else:
            att_roll = 0.70
            def_roll = 0.70
        
        att_damage = att_cv * att_roll
        def_damage = def_cv * def_roll
        
        ratio = att_damage / (def_damage + 0.001)
        if ratio >= 2.5:
            victory = "Immense Triumph"
            resistance_burn = 2
            loot_percent = 0.75
        elif ratio >= 1.8:
            victory = "Massive Victory"
            resistance_burn = 2
            loot_percent = 0.65
        elif ratio >= 1.2:
            victory = "Strong Victory"
            resistance_burn = 1
            loot_percent = 0.50
        elif ratio >= 0.8:
            victory = "Pyrrhic Victory"
            resistance_burn = 1
            loot_percent = 0.35
        else:
            victory = "Failure / Defeat"
            resistance_burn = 0
            loot_percent = 0.0
        
        casualty_multiplier = (def_damage / (att_damage + 0.001)) * 0.1
        att_soldier_loss = int(att_soldiers * casualty_multiplier * 0.6)
        att_tank_loss = int(att_tanks * casualty_multiplier * 0.4)
        
        return {
            "victory": victory,
            "resistance_burn": resistance_burn,
            "loot_percent": loot_percent,
            "att_soldier_loss": att_soldier_loss,
            "att_tank_loss": att_tank_loss,
            "att_damage": att_damage,
            "def_damage": def_damage,
            "ratio": ratio
        }
    
    def can_win(self) -> bool:
        """Check if worst-case battle is winnable."""
        result = self.simulate_battle(
            self.att_soldiers, self.att_tanks, self.att_aircraft, self.att_ships,
            self.def_soldiers, self.def_tanks, self.def_aircraft, self.def_ships,
            scenario="worst"
        )
        return result["victory"] not in ["Failure / Defeat"]
    
    def build_strategy(self) -> Tuple[str, List[str]]:
        """Determine optimal attack sequence for this war."""
        sequence = []
        summary = ""
        
        if not self.can_win():
            return ("❌ CANNOT WIN - Even with perfect rolls, attacker is too strong.", [])
        
        if self.def_aircraft > 50:
            sequence.append("Air Strike (Break enemy aircraft)")
            summary += "• Enemy has strong air presence. Airstrikes first to secure air superiority.\n"
        
        if self.def_ships > 20 and self.naval_blockade != "Attacker":
            sequence.append("Naval Attack (Establish blockade)")
            summary += "• Establish naval blockade to cut resource trading.\n"
        
        turns_to_beige = math.ceil(self.defender_resistance / 2.0)
        summary += f"• Ground attacks to burn resistance ({self.defender_resistance} → 0 = ~{turns_to_beige} turns).\n"
        
        for i in range(turns_to_beige):
            sequence.append(f"Ground Attack #{i+1} (Cash farm + resistance burn)")
        
        summary += f"• Final hit: Beige protection triggers, massive resource loot.\n"
        
        return (summary, sequence)
    
    def generate_report(self) -> str:
        """Generate full Discord embed-formatted war report."""
        can_win = self.can_win()
        
        if not can_win:
            return f"""
🔴 WAR #{self.war['id']}
⚔️ Attacker: {self.attacker['leader_name']} ({self.attacker['nation_name']}) — Score {self.attacker['score']}
  🪖 {self.att_soldiers:,} | 🛡️ {self.att_tanks:,} | ✈️ {self.att_aircraft:,} | 🚢 {self.att_ships:,}
🛡️ Defending: {self.defender['leader_name']} ({self.defender['nation_name']})

❌ **CANNOT WIN** — Even with perfect rolls (100% us, 40% them), attacker's military advantage is insurmountable.
            """
        
        strategy_summary, sequence = self.build_strategy()
        
        report = f"""
🔴 WAR #{self.war['id']}
⚔️ Attacker: {self.attacker['leader_name']} ({self.attacker['nation_name']}) — Score {self.attacker['score']}
  🪖 {self.att_soldiers:,} | 🛡️ {self.att_tanks:,} | ✈️ {self.att_aircraft:,} | 🚢 {self.att_ships:,}
🛡️ Defending: {self.defender['leader_name']} ({self.defender['nation_name']})

✅ **CAN WIN** — Attacker is vulnerable.

**Strategy Overview:**
{strategy_summary}

**Recommended Attack Sequence:**
"""
        for i, attack in enumerate(sequence, 1):
            report += f"{i}. {attack}\n"
        
        best = self.simulate_battle(self.att_soldiers, self.att_tanks, self.att_aircraft, self.att_ships,
                                     self.def_soldiers, self.def_tanks, self.def_aircraft, self.def_ships,
                                     scenario="best")
        avg = self.simulate_battle(self.att_soldiers, self.att_tanks, self.att_aircraft, self.att_ships,
                                    self.def_soldiers, self.def_tanks, self.def_aircraft, self.def_ships,
                                    scenario="average")
        worst = self.simulate_battle(self.att_soldiers, self.att_tanks, self.att_aircraft, self.att_ships,
                                      self.def_soldiers, self.def_tanks, self.def_aircraft, self.def_ships,
                                      scenario="worst")
        
        report += f"""
**Combat Simulation:**
🔵 **Average (70% rolls):** {avg['victory']} | Casualties: ~{avg['att_soldier_loss']:,} soldiers, ~{avg['att_tank_loss']:,} tanks
🟢 **Best (100% us, 40% them):** {best['victory']} | Casualties: ~{best['att_soldier_loss']:,} soldiers, ~{best['att_tank_loss']:,} tanks
🔴 **Worst (40% us, 100% them):** {worst['victory']} | Casualties: ~{worst['att_soldier_loss']:,} soldiers, ~{worst['att_tank_loss']:,} tanks

**War State:**
• Resistance: {self.defender_resistance}/100
• Air Superiority: {"Attacker" if self.air_superiority == "Attacker" else "Defender" if self.air_superiority == "Defender" else "Contested"}
• Naval Blockade: {"Active" if self.naval_blockade == "Attacker" else "None"}
        """
        
        return report

# ============================================================================
# Discord Commands
# ============================================================================

@bot.event
async def on_ready():
    logger.info(f"☭ Logged in as {bot.user}")
    guild_obj = discord.Object(id=YOUR_SERVER_ID)
    bot.tree.copy_global_to(guild=guild_obj)
    await bot.tree.sync(guild=guild_obj)
    logger.info(f"☭ Synced commands to guild {YOUR_SERVER_ID}")

@bot.tree.command(name="counter", description="Analyze all defensive wars and build precise attack strategies")
@app_commands.guilds(discord.Object(id=YOUR_SERVER_ID))
async def counter_command(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("Testing P&W API connection...")
            
            # Test basic nation query first
            test_query = """
            query {
              nation(id: 634658) {
                id
                leader_name
                nation_name
              }
            }
            """
            
            test_data = await pandw_query(session, test_query)
            logger.info(f"Test query result: {test_data}")
            
            # Fetch alliance wars
            wars_query = """
            query($id: Int!) {
              alliance(id: $id) {
                wars {
                  id
                  attacker_id
                  defender_id
                  attacker_resistance
                  defender_resistance
                  attacker_map
                  defender_map
                  ground_control
                  air_superiority
                  naval_blockade
                  status
                }
              }
            }
            """
            
            wars_data = await pandw_query(session, wars_query, {"id": PANDW_ALLIANCE_ID})
            logger.info(f"Wars data: {wars_data}")
            wars = wars_data.get("alliance", {}).get("wars", [])
            
            if not wars:
                await interaction.followup.send("☭ No active wars detected.")
                return
            
            # Analyze each war
            for war in wars[:10]:
                attacker_id = war.get("attacker_id")
                defender_id = war.get("defender_id")
                
                nations_query = """
                query($attacker: Int!, $defender: Int!) {
                  attacker: nation(id: $attacker) {
                    id
                    leader_name
                    nation_name
                    score
                    soldiers
                    tanks
                    aircraft
                    ships
                  }
                  defender: nation(id: $defender) {
                    id
                    leader_name
                    nation_name
                    score
                    soldiers
                    tanks
                    aircraft
                    ships
                  }
                }
                """
                
                nations_data = await pandw_query(session, nations_query, 
                                                 {"attacker": attacker_id, "defender": defender_id})
                
                attacker = nations_data.get("attacker", {})
                defender = nations_data.get("defender", {})
                
                analyzer = WarAnalyzer(war, attacker, defender)
                report = analyzer.generate_report()
                
                if len(report) > 2000:
                    chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
                    for chunk in chunks:
                        await interaction.followup.send(chunk)
                else:
                    await interaction.followup.send(report)
                
                await asyncio.sleep(0.5)
    
    except Exception as e:
        logger.exception("Error in /counter")
        error_msg = f"❌ Party communications failed: {str(e)}"
        await interaction.followup.send(error_msg)

@bot.tree.command(name="status", description="Show bot status")
@app_commands.guilds(discord.Object(id=YOUR_SERVER_ID))
async def status_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"☭ **URS Commissar Online**\n"
        f"API Key configured: {bool(P_AND_W_API_KEY)}\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

# ============================================================================
# Entry Point
# ============================================================================

def main():
    if not DISCORD_TOKEN or not P_AND_W_API_KEY:
        logger.error("❌ Missing DISCORD_TOKEN or P_AND_W_API_KEY")
        return
    
    logger.info("☭ URS Commissar starting...")
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
