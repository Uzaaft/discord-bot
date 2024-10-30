from itertools import filterfalse

import discord

from app import config, view
from app.features.invites import log_invite
from app.utils import is_tester, try_dm


class ConfirmBulkInvite(discord.ui.View):
    def __init__(
        self, members: list[discord.Member], message: discord.Message, prompt: str
    ) -> None:
        super().__init__(timeout=None)
        self._members = members
        self._message = message
        self._prompt = prompt
        self._used = False

    @discord.ui.button(
        label="Yes",
        emoji="✅",
        custom_id="ghostty:bulk_invite:confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, but: discord.ui.Button
    ) -> None:
        if self._used:
            return
        self._used = True
        await interaction.response.defer(thinking=True, ephemeral=True)

        invited_members = set[discord.Member]()
        for member in filterfalse(is_tester, self._members):
            await member.add_roles(
                discord.Object(config.TESTER_ROLE_ID),
                reason="invite to beta context menu",
            )
            await try_dm(member, view.NEW_TESTER_DM)
            await log_invite(
                interaction.user,
                member,
                note=f"bulk invite at {self._message.jump_url}",
            )
            invited_members.add(member)

        content = f"Invited {len(invited_members)} members."
        if already_testers := set(self._members) - invited_members:
            content += f" {len(already_testers)} were already testers: "
            content += " ".join(member.mention for member in already_testers)

        await interaction.followup.send(content=content, ephemeral=True)

    @discord.ui.button(
        label="No",
        emoji="❌",
        custom_id="ghostty:bulk_invite:cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, but: discord.ui.Button
    ) -> None:
        if self._used:
            return
        await interaction.response.edit_message(
            content="Bulk invite cancelled.", view=None
        )
