from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from traceback import print_tb
from typing import cast

import discord
from discord.ext import commands
from sentry_sdk import capture_exception

from app.db.connect import Session
from app.db.utils import fetch_user
from app.features.entity_mentions import ENTITY_REGEX, handle_entities
from app.setup import bot, config
from app.utils import check_message, is_dm, is_mod, try_dm
from app.view import register_vouch_view


@bot.event
async def on_ready() -> None:
    register_vouch_view()
    print(f"Bot logged on as {bot.user}!")


@bot.event
async def on_error(*_: object) -> None:
    handle_error(cast(BaseException, sys.exc_info()[1]))


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: Exception
) -> None:
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "Something went wrong :(", ephemeral=True
        )
    handle_error(error)


@bot.event
async def on_message(message: discord.Message) -> None:
    # Ignore our own messages
    if message.author == bot.user:
        return

    # Special trigger command to request an invite.
    # trigger = "I WANT GHOSTTY"
    # if message.content.strip().upper() == trigger:
    #     if message.guild is None:
    #         await message.channel.send("Tell me you want me in the Ghostty server!")
    #         return
    #
    #     if message.content.strip() == trigger:
    #         # TODO
    #         return
    #
    #     await message.channel.send("Louder. LOUDER!!")
    #     return

    # Simple test
    if message.guild is None and message.content == "ping":
        await try_dm(message.author, "pong")
        return

    # Look for issue/PR/discussion mentions and name/link them
    if ENTITY_REGEX.search(message.content):
        await handle_entities(message)

    # Delete non-image messages in #showcase
    if message.channel.id == config.SHOWCASE_CHANNEL_ID and not check_message(
        message, lambda msg: msg.attachments
    ):
        await message.delete()

    # Mod-only sync command
    if message.content.rstrip() == "!sync":
        await sync(bot, message)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    if not (new_roles := set(after.roles) - set(before.roles)):
        return
    if next(iter(new_roles)).id == config.TESTER_ROLE_ID:
        user = fetch_user(after, new_user=True)
        if user.tester_since is None:
            with Session() as session:
                user.tester_since = dt.datetime.now(tz=dt.UTC)
                user.is_vouch_blacklisted = False
                session.add(user)
                session.commit()


async def sync(bot: commands.Bot, message: discord.Message) -> None:
    """Syncs all global commands."""
    if is_dm(message.author) or not is_mod(message.author):
        return

    await bot.tree.sync()
    await try_dm(message.author, "Command tree synced.")


def handle_error(error: BaseException) -> None:
    if _is_ratelimit(error):
        # Restart the bot with a delay at startup.
        # This effectively replaces the current process.
        os.execv(
            sys.executable,
            (
                "python",
                Path(__file__).parent / "__main__.py",
                *sys.argv[1:],
                "--rate-limit-delay",
            ),
        )

    if config.SENTRY_DSN is not None:
        capture_exception(error)
        return

    print(type(error).__name__, "->", error)
    print_tb(error.__traceback__)
    if isinstance(error, discord.app_commands.CommandInvokeError):
        handle_error(error.original)


def _is_ratelimit(error: BaseException) -> bool:
    if isinstance(error, discord.app_commands.CommandInvokeError):
        error = error.original
    return isinstance(error, discord.HTTPException) and error.status == 429
