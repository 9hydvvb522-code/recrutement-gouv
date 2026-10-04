import json
import os
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
# rôles des recruteurs, séparés par des virgules (vide ou 0 = pas de restriction)
RECRUITER_ROLE_IDS = [
    int(x) for x in os.getenv("RECRUITER_ROLE_ID", "0").replace(" ", "").split(",")
    if x and x != "0"
]
ACCEPTED_ROLE_ID = int(os.getenv("ACCEPTED_ROLE_ID"))          # rôle "candidature acceptée" à ping
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", "0"))   # salon des pings (0 = salon du panel)

# salon où les candidats doivent venir quand un recruteur est dispo
ENTRETIEN_CHANNEL_ID = int(os.getenv("ENTRETIEN_CHANNEL_ID", "1554901523622789341"))
ENTRETIEN_URL = f"https://discord.com/channels/1486833515545886844/{ENTRETIEN_CHANNEL_ID}"

DATA_FILE = Path("data.json")


def load_available() -> list:
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    return []


def save_available() -> None:
    DATA_FILE.write_text(json.dumps(available), encoding="utf-8")


available = load_available()  # IDs des recruteurs actuellement dispos


def is_recruiter(member: discord.Member) -> bool:
    if not RECRUITER_ROLE_IDS:
        return True
    return any(r.id in RECRUITER_ROLE_IDS for r in member.roles)


def status_text() -> str:
    n = len(available)
    if n == 0:
        return "🔴 Aucun recruteur dispo | Made By Azalee"
    if n == 1:
        return "🟢 1 recruteur dispo | Made By Azalee"
    return f"🟢 {n} recruteurs dispos | Made By Azalee"


def make_activity() -> discord.Activity:
    return discord.Activity(type=discord.ActivityType.watching, name=status_text())


async def update_status() -> None:
    try:
        await bot.change_presence(activity=make_activity())
        print(f"Statut mis à jour : {status_text()}")
    except Exception as e:
        print(f"Impossible de mettre à jour le statut : {e}")


def get_notify_channel(interaction: discord.Interaction):
    return bot.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else interaction.channel


def build_embed() -> discord.Embed:
    n = len(available)
    if n == 0:
        desc = "## 🔴 Aucun recruteur disponible\nMerci de patienter jusqu'à la prochaine disponibilité."
    else:
        label = "recruteur disponible" if n == 1 else "recruteurs disponibles"
        desc = f"## 🟢 {n} {label}\n" + "\n".join(f"🟢 <@{r}>" for r in available)
    embed = discord.Embed(
        title="DISPONIBILITÉ DES RECRUTEURS",
        description=desc,
        color=discord.Color.blurple(),
    )
    icon = bot.user.display_avatar.url if bot.user else None
    embed.set_footer(text="Recruteurs : utilisez les boutons pour changer votre statut", icon_url=icon)
    return embed


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # panel permanent

    @discord.ui.button(label="Plus dispo", emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="panel:indispo")
    async def indispo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_recruiter(interaction.user):
            return await interaction.response.send_message("Réservé aux recruteurs.", ephemeral=True)

        if interaction.user.id not in available:
            return await interaction.response.send_message("Tu n'étais pas marqué comme disponible.", ephemeral=True)

        available.remove(interaction.user.id)
        save_available()
        await interaction.response.edit_message(embed=build_embed(), view=self)
        await update_status()

        embed = discord.Embed(
            title="🔴 Recruteur indisponible",
            description=f"{interaction.user.mention} n'est **plus disponible** pour le moment.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Merci de patienter jusqu'à la prochaine disponibilité")

        channel = get_notify_channel(interaction)
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())  # aucun ping

    @discord.ui.button(label="Je suis dispo", emoji="✅", style=discord.ButtonStyle.success, custom_id="panel:dispo")
    async def dispo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_recruiter(interaction.user):
            return await interaction.response.send_message("Réservé aux recruteurs.", ephemeral=True)

        if interaction.user.id in available:
            return await interaction.response.send_message("Tu es déjà marqué comme disponible.", ephemeral=True)

        available.append(interaction.user.id)
        save_available()

        await interaction.response.edit_message(embed=build_embed(), view=self)
        await update_status()

        embed = discord.Embed(
            title="🟢 Un recruteur est disponible !",
            description=(
                f"{interaction.user.mention} est maintenant **disponible** pour passer un entretien.\n\n"
                f"👉 Viens dans <#{ENTRETIEN_CHANNEL_ID}> pour être pris en charge."
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="👤 Recruteur", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐 Disponible depuis", value=discord.utils.format_dt(discord.utils.utcnow(), "R"), inline=True)
        embed.add_field(name="📍 Salon", value=f"[Clique ici pour rejoindre]({ENTRETIEN_URL})", inline=False)
        embed.set_footer(text="Candidature acceptée • Entretien")

        channel = get_notify_channel(interaction)
        await channel.send(
            content=f"<@&{ACCEPTED_ROLE_ID}>",  # le ping doit être dans le texte, pas dans l'embed
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True, users=False),
        )

    @discord.ui.button(label="Voir les dispos", emoji="📋", style=discord.ButtonStyle.primary, custom_id="panel:voir")
    async def voir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if available:
            txt = "**Recruteurs disponibles :**\n" + "\n".join(f"🟢 <@{r}>" for r in available)
        else:
            txt = "Aucun recruteur n'est disponible pour le moment."
        await interaction.response.send_message(
            txt, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


class RecruiterBot(discord.Client):
    def __init__(self):
        super().__init__(
            intents=discord.Intents.default(),
            activity=make_activity(),  # <- le texte est dans status_text()
            status=discord.Status.online,  # online / idle / dnd
        )
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(PanelView())  # les boutons restent actifs après un redémarrage
        synced = await self.tree.sync()
        print(f"{len(synced)} commande(s) synchronisée(s) : {[c.name for c in synced]}")


bot = RecruiterBot()


@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
    await update_status()


@bot.tree.command(name="panel", description="(Admin) Poster le panel de disponibilité des recruteurs")
@app_commands.default_permissions(administrator=True)
async def panel(interaction: discord.Interaction):
    await interaction.channel.send(embed=build_embed(), view=PanelView())
    await interaction.response.send_message("Panel posté ✅", ephemeral=True)


bot.run(TOKEN)
