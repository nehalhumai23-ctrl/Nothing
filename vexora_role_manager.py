"""
VEXORA HUB role manager cog
discord.py 2.x

Commands:
  .rc
  .cp <channel> <role> <permission1,permission2> <on/off>
  .rp <role> <permission1,permission2> <on/off>

Load with:
  await bot.load_extension("vexora_role_manager")

Make sure your bot has Manage Roles and Manage Channels permissions,
and its highest role is above the roles/channels it needs to manage.
"""

from __future__ import annotations

import discord
from discord.ext import commands
import json
import asyncio
from pathlib import Path


# Permissions granted to ordinary verified members.
BASIC_MEMBER = {
    "view_channel",
    "send_messages",
    "read_message_history",
    "add_reactions",
    "embed_links",
    "attach_files",
    "use_external_emojis",
    "use_external_stickers",
    "connect",
    "speak",
    "use_voice_activation",
    "send_messages_in_threads",
    "create_public_threads",
}


def make_permissions(*names: str) -> discord.Permissions:
    """Build a Permissions object from permission flag names."""
    perms = discord.Permissions.none()
    for name in names:
        if name not in discord.Permissions.VALID_FLAGS:
            raise ValueError(f"Unknown Discord permission in role config: {name}")
        setattr(perms, name, True)
    return perms


# (role name, hex colour, permission flags)
ROLE_DEFINITIONS: list[tuple[str, int, set[str]]] = [
    # Staff & management
    ("・👑︰Owner◞", 0xF1C40F, {"administrator"}),
    ("・💎︰Co-Owner◞", 0x00D4FF, {
        "manage_guild", "manage_channels", "manage_roles", "view_audit_log",
        "manage_messages", "kick_members", "ban_members", "moderate_members",
        "manage_events",
    }),
    ("・🛡️︰Head Admin◞", 0xE74C3C, {
        "manage_channels", "manage_messages", "manage_events", "view_audit_log",
        "kick_members", "ban_members", "moderate_members", "manage_nicknames",
    }),
    ("・⚜️︰Admin◞", 0xE67E22, {
        "manage_messages", "manage_events", "view_audit_log", "kick_members",
        "ban_members", "moderate_members", "manage_nicknames",
    }),
    ("・🔰︰Head Moderator◞", 0x3498DB, {
        "manage_messages", "view_audit_log", "kick_members",
        "moderate_members", "manage_nicknames",
    }),
    ("・🔨︰Moderator◞", 0x2980B9, {
        "manage_messages", "kick_members", "moderate_members", "manage_nicknames",
    }),
    ("・🧰︰Helper◞", 0x2ECC71, {
        "view_channel", "send_messages", "read_message_history", "add_reactions",
        "connect", "speak",
    }),
    ("・🎫︰Support Team◞", 0x1ABC9C, {
        "view_channel", "send_messages", "read_message_history", "add_reactions",
    }),
    ("・🤖︰Bot◞", 0x94A3B8, set()),

    # Special
    ("・.︰Bypass◞", 0x64748B, set()),

    # Community & premium
    ("・💠︰VIP◞", 0xFFD700, BASIC_MEMBER | {"attach_files", "embed_links"}),
    ("・✨︰Premium◞", 0xA970FF, BASIC_MEMBER | {
        "attach_files", "embed_links", "use_external_emojis", "use_external_stickers",
    }),
    ("・🚀︰Booster◞", 0xFF73FA, BASIC_MEMBER | {
        "attach_files", "embed_links", "use_external_emojis", "use_external_stickers",
    }),
    ("・🎥︰Content Creator◞", 0x55C7FF, BASIC_MEMBER | {
        "attach_files", "embed_links", "create_public_threads",
    }),
    ("・📸︰Media◞", 0xE879F9, BASIC_MEMBER | {"attach_files", "embed_links"}),
    ("・🤝︰Partner◞", 0xF59E0B, BASIC_MEMBER | {"attach_files", "embed_links"}),
    ("・💬︰Active Member◞", 0x22C55E, BASIC_MEMBER.copy()),
    ("・🌱︰Member◞", 0xAAB2BD, BASIC_MEMBER.copy()),
    ("・🆕︰New Member◞", 0x38BDF8, {"view_channel", "read_message_history"}),

    # Gaming
    ("・⛏️︰Minecraft◞", 0x16A34A, BASIC_MEMBER.copy()),
    ("・🔪︰Among Us◞", 0xEF4444, BASIC_MEMBER.copy()),
    ("・🎯︰Valorant◞", 0xFF4655, BASIC_MEMBER.copy()),
    ("・🔫︰BGMI◞", 0xD97706, BASIC_MEMBER.copy()),
    ("・🍳︰Roblox◞", 0xFFFFFF, BASIC_MEMBER.copy()),
    ("・🚗︰GTA V◞", 0x65A30D, BASIC_MEMBER.copy()),
    ("・🔥︰Free Fire◞", 0xF97316, BASIC_MEMBER.copy()),
    ("・🏆︰Fortnite◞", 0x8B5CF6, BASIC_MEMBER.copy()),
    ("・🚀︰Rocket League◞", 0x0EA5E9, BASIC_MEMBER.copy()),
    ("・🧱︰Stumble Guys◞", 0xF472B6, BASIC_MEMBER.copy()),
    ("・🎵︰Music Lover◞", 0xD946EF, BASIC_MEMBER.copy()),
    ("・😂︰Meme Lord◞", 0xFACC15, BASIC_MEMBER.copy()),

    # Gender & social
    ("・♂️︰Boys◞", 0x3B82F6, BASIC_MEMBER.copy()),
    ("・♀️︰Girls◞", 0xF472B6, BASIC_MEMBER.copy()),
    ("・💬︰Chatty◞", 0x2DD4BF, BASIC_MEMBER.copy()),
    ("・🎨︰Artist◞", 0xC084FC, BASIC_MEMBER | {"attach_files", "embed_links"}),
    ("・📷︰Photographer◞", 0x64748B, BASIC_MEMBER | {"attach_files", "embed_links"}),
]


PERMISSION_ALIASES = {
    "view_channels": "view_channel",
    "manage_server": "manage_guild",
    "use_voice_activity": "use_voice_activation",
    "external_emojis": "use_external_emojis",
    "external_stickers": "use_external_stickers",
}

# Only the guild owner can turn these particularly sensitive permissions ON
# through .rp. Staff admins can still manage ordinary permissions.
OWNER_ONLY_ENABLE = {
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
}


def parse_permission_names(raw: str) -> list[str]:
    names = []
    for item in raw.split(","):
        name = item.strip().lower().replace("-", "_").replace(" ", "_")
        name = PERMISSION_ALIASES.get(name, name)
        if not name:
            continue
        if name not in discord.Permissions.VALID_FLAGS:
            valid = ", ".join(sorted(discord.Permissions.VALID_FLAGS))
            raise ValueError(
                f"`{name}` valid permission nahi hai. Permission names snake_case mein use karo.\n"
                f"Examples: `send_messages`, `view_channel`, `manage_messages`."
            )
        if name not in names:
            names.append(name)
    if not names:
        raise ValueError("Kam se kam ek permission name do.")
    return names


class VexoraRoleManager(commands.Cog):
    VERIFIED_ROLE_NAME = "・🌱︰Member◞"
    SETTINGS_FILE = Path("data/verification_settings.json")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verification_enabled: set[int] = set()
        self._settings_lock = asyncio.Lock()
        self._load_verification_settings()

    def _load_verification_settings(self) -> None:
        """Load guilds with automatic member verification enabled."""
        try:
            if self.SETTINGS_FILE.exists():
                data = json.loads(self.SETTINGS_FILE.read_text(encoding="utf-8"))
                self.verification_enabled = {int(guild_id) for guild_id in data.get("enabled_guilds", [])}
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"[VEXORA] Could not load verification settings: {exc}")
            self.verification_enabled = set()

    async def _save_verification_settings(self) -> None:
        async with self._settings_lock:
            self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {"enabled_guilds": sorted(self.verification_enabled)}
            temp_file = self.SETTINGS_FILE.with_suffix(".tmp")
            temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_file.replace(self.SETTINGS_FILE)

    def _verified_role(self, guild: discord.Guild) -> discord.Role | None:
        return discord.utils.get(guild.roles, name=self.VERIFIED_ROLE_NAME)

    async def _check_verification_setup(self, ctx: commands.Context) -> discord.Role | None:
        if not await self._can_manage(ctx):
            return None
        role = self._verified_role(ctx.guild)
        if role is None:
            await ctx.reply(
                f"❌ Verified role nahi mila. Pehle `.rc` se roles create karo, "
                f"ya `{self.VERIFIED_ROLE_NAME}` naam ka role banao.",
                mention_author=False,
            )
            return None
        me = ctx.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            await ctx.reply("❌ Bot ko **Manage Roles** permission chahiye.", mention_author=False)
            return None
        if role >= me.top_role:
            await ctx.reply("❌ Bot ka highest role verified role se upar hona chahiye.", mention_author=False)
            return None
        return role

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Automatically give the verified role to new members when enabled."""
        if member.guild.id not in self.verification_enabled:
            return
        role = self._verified_role(member.guild)
        me = member.guild.me
        if role is None or me is None or not me.guild_permissions.manage_roles or role >= me.top_role:
            print(f"[VEXORA] Could not auto-verify new member {member.id} in {member.guild.id}: role/permissions issue")
            return
        try:
            await member.add_roles(role, reason="VEXORA automatic verification is enabled")
        except discord.Forbidden:
            print(f"[VEXORA] Missing permissions to auto-verify member {member.id}")
        except discord.HTTPException as exc:
            print(f"[VEXORA] Auto-verification failed for {member.id}: {exc}")

    @commands.command(name="verifyon")
    @commands.guild_only()
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    async def verify_on(self, ctx: commands.Context):
        """Verify all current members and automatically verify future joiners."""
        role = await self._check_verification_setup(ctx)
        if role is None:
            return

        self.verification_enabled.add(ctx.guild.id)
        try:
            await self._save_verification_settings()
        except OSError as exc:
            self.verification_enabled.discard(ctx.guild.id)
            return await ctx.reply(f"❌ Auto-verification setting save nahi ho payi: `{exc}`", mention_author=False)

        status = await ctx.reply(
            "⏳ **Verification started** — existing members ko verified role diya ja raha hai. "
            "New members bhi automatically verify honge.",
            mention_author=False,
        )
        added = 0
        already_had = 0
        failed = 0
        # Use the member cache populated by the members intent; fetch_members also
        # ensures the operation covers members not currently cached.
        try:
            async for member in ctx.guild.fetch_members(limit=None):
                if member.bot or role in member.roles:
                    already_had += 1
                    continue
                try:
                    await member.add_roles(role, reason=f"Bulk verification enabled by {ctx.author}")
                    added += 1
                except (discord.Forbidden, discord.HTTPException):
                    failed += 1
        except discord.Forbidden:
            failed += 1
            await status.edit(content=(
            "✅ **Verification enabled**\n"
            f"Verified now: **{added}**\n"
            f"Already verified: **{already_had}**\n"
            f"Failed: **{failed}**\n"
            "New members will also be automatically verified."
        ))

    @commands.command(name="rverify")
    @commands.guild_only()
    async def remove_verification(self, ctx: commands.Context, member: discord.Member):
        """Remove the verified role from one member."""
        if not await self._can_manage(ctx):
            return
        role = self._verified_role(ctx.guild)
        if role is None:
            return await ctx.reply(f"❌ Verified role `{self.VERIFIED_ROLE_NAME}` nahi mila.", mention_author=False)
        me = ctx.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return await ctx.reply("❌ Bot ko **Manage Roles** permission chahiye.", mention_author=False)
        if role >= me.top_role:
            return await ctx.reply("❌ Bot ka highest role verified role se upar hona chahiye.", mention_author=False)
        if role not in member.roles:
            return await ctx.reply(f"ℹ️ {member.mention} ke paas verified role nahi hai.", mention_author=False)
        try:
            await member.remove_roles(role, reason=f"Verification removed by {ctx.author}")
        except discord.Forbidden:
            return await ctx.reply("❌ Role remove nahi ho saka. Bot role hierarchy check karo.", mention_author=False)
        except discord.HTTPException as exc:
            return await ctx.reply(f"❌ Discord API error: `{exc}`", mention_author=False)
        await ctx.reply(f"✅ {member.mention} ka verification remove kar diya gaya.", mention_author=False)

    async def _can_manage(self, ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            await ctx.reply("Ye command sirf server ke andar use ho sakti hai.", mention_author=False)
            return False
        if ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator:
            return True
        if ctx.author.guild_permissions.manage_roles:
            return True
        await ctx.reply("❌ Is command ke liye **Manage Roles** ya **Administrator** permission chahiye.", mention_author=False)
        return False

    async def _bot_can_manage_role(self, ctx: commands.Context, role: discord.Role) -> bool:
        me = ctx.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            await ctx.reply("❌ Bot ko **Manage Roles** permission do.", mention_author=False)
            return False
        if role.is_default():
            await ctx.reply("❌ @everyone role ko is command se edit nahi kar sakte.", mention_author=False)
            return False
        if role >= me.top_role:
            await ctx.reply("❌ Bot ka highest role target role se upar hona chahiye.", mention_author=False)
            return False
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            await ctx.reply("❌ Tum apne highest role ke barabar ya usse upar wala role edit nahi kar sakte.", mention_author=False)
            return False
        return True

    @commands.command(name="rc")
    @commands.guild_only()
    async def create_roles(self, ctx: commands.Context):
        """Create all predefined VEXORA HUB roles with colours and permissions."""
        if not await self._can_manage(ctx):
            return

        me = ctx.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return await ctx.reply("❌ Bot ko **Manage Roles** permission do.", mention_author=False)

        created = 0
        skipped = 0
        failed: list[str] = []

        # Create from highest to lowest in the definition list.
        for name, colour, permission_names in ROLE_DEFINITIONS:
            existing = discord.utils.get(ctx.guild.roles, name=name)
            if existing:
                skipped += 1
                continue

            try:
                permissions = make_permissions(*sorted(permission_names))
                await ctx.guild.create_role(
                    name=name,
                    colour=discord.Colour(colour),
                    permissions=permissions,
                    hoist=True,
                    mentionable=False,
                    reason=f"VEXORA HUB role setup requested by {ctx.author}",
                )
                created += 1
            except discord.Forbidden:
                failed.append(f"{name}: Missing permission / role hierarchy")
            except discord.HTTPException as exc:
                failed.append(f"{name}: Discord API error ({exc.status})")

        summary = (
            f"✅ **VEXORA role setup complete**\n"
            f"Created: **{created}**\n"
            f"Already existed (skipped): **{skipped}**\n"
            f"Failed: **{len(failed)}**"
        )
        if failed:
            summary += "\n\n**Failed roles:**\n" + "\n".join(f"• {item}" for item in failed[:10])
        summary += "\n\nRole positions may need arranging manually in Server Settings → Roles."
        await ctx.reply(summary, mention_author=False)

    @commands.command(name="cp")
    @commands.guild_only()
    async def channel_permissions(
        self,
        ctx: commands.Context,
        channel_name: str,
        role: discord.Role,
        permissions: str,
        state: str,
    ):
        """
        Change channel-specific role permissions.
        Example: .cp #general @Member send_messages,attach_files on
        """
        if not await self._can_manage(ctx):
            return
        if state.lower() not in {"on", "off"}:
            return await ctx.reply("Use `on` ya `off` at the end.", mention_author=False)
        if not await self._bot_can_manage_role(ctx, role):
            return

        try:
            channel = await commands.GuildChannelConverter().convert(ctx, channel_name)
        except commands.BadArgument:
            return await ctx.reply("❌ Channel nahi mila. Channel mention ya exact name use karo.", mention_author=False)

        try:
            names = parse_permission_names(permissions, channel=True)
        except ValueError as exc:
            return await ctx.reply(f"❌ {exc}", mention_author=False)

        me = ctx.guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return await ctx.reply("❌ Channel overwrites edit karne ke liye bot ko **Manage Channels** permission bhi chahiye.", mention_author=False)

        overwrite = channel.overwrites_for(role)
        value = state.lower() == "on"
        try:
            overwrite.update(**{name: value for name in names})
            await channel.set_permissions(
                role,
                overwrite=overwrite,
                reason=f"Channel permissions changed by {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.reply("❌ Discord ne permission change reject kar diya. Bot role hierarchy aur Manage Channels check karo.", mention_author=False)
        except discord.HTTPException as exc:
            return await ctx.reply(f"❌ Discord API error: `{exc}`", mention_author=False)

        await ctx.reply(
            f"✅ **Channel permissions updated**\n"
            f"Channel: {channel.mention}\n"
            f"Role: {role.mention}\n"
            f"Permissions: `{', '.join(names)}`\n"
            f"State: **{state.upper()}**",
            mention_author=False,
        )

    @commands.command(name="rp")
    @commands.guild_only()
    async def role_permissions(
        self,
        ctx: commands.Context,
        role: discord.Role,
        permissions: str,
        state: str,
    ):
        """
        Change server-wide role permissions.
        Example: .rp @Moderator kick_members,manage_messages on
        """
        if not await self._can_manage(ctx):
            return
        if state.lower() not in {"on", "off"}:
            return await ctx.reply("Use `on` ya `off` at the end.", mention_author=False)
        if not await self._bot_can_manage_role(ctx, role):
            return

        try:
            names = parse_permission_names(permissions)
        except ValueError as exc:
            return await ctx.reply(f"❌ {exc}", mention_author=False)

        enabling = state.lower() == "on"
        if enabling and any(name in OWNER_ONLY_ENABLE for name in names):
            if ctx.author.id != ctx.guild.owner_id:
                return await ctx.reply(
                    "❌ In sensitive permissions ko ON sirf **server owner** kar sakta hai: "
                    "`administrator`, `manage_guild`, `manage_roles`, `manage_channels`, `manage_webhooks`.",
                    mention_author=False,
                )

        new_permissions = role.permissions
        try:
            new_permissions.update(**{name: enabling for name in names})
            await role.edit(
                permissions=new_permissions,
                reason=f"Role permissions changed by {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.reply("❌ Bot role hierarchy ya Manage Roles permission check karo.", mention_author=False)
        except discord.HTTPException as exc:
            return await ctx.reply(f"❌ Discord API error: `{exc}`", mention_author=False)

        await ctx.reply(
            f"✅ **Role permissions updated**\n"
            f"Role: {role.mention}\n"
            f"Permissions: `{', '.join(names)}`\n"
            f"State: **{state.upper()}**",
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(VexoraRoleManager(bot))
