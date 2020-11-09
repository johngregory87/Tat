import discord
import modules.vars as vars
import asyncio
from modules.logs import *
import sys


async def start_bot(discord_connector, analytics):
    """
    Start the bot cycle
    :param analytics: GoogleAnalytics object
    :param discord_connector: DiscordConnector object
    :return: None
    """
    info("Starting monitoring...")
    analytics.event(event_category="Platform", event_action=sys.platform)
    await discord_connector.get_tautulli_channel()
    message = await discord_connector.get_old_message_in_tautulli_channel()
    while True:
        message = await discord_connector.edit_message(previous_message=message)


async def add_emoji_number_reactions(message, count):
    """
    Add number reactions to a message for user interaction
    :param message: message to add emojis to
    :param count: how many emojis to add
    :return: None
    """
    
    if count <= 0:
        return
        
    # Only add reactions if necessary, and remove unnecessary reactions
    cache_msg = await message.channel.fetch_message(message.id)
    msg_emoji = [str(r.emoji) for r in cache_msg.reactions]
    
    emoji_to_remove = []
    
    for i,e in enumerate(msg_emoji):
        if i >= count or i != vars.emoji_numbers.index(e):
            emoji_to_remove.append(e)
    
    # if all reactions need to be removed, do it all at once
    if len(emoji_to_remove) == len(msg_emoji):
        await message.clear_reactions()
        msg_emoji = []
    else:
        for e in emoji_to_remove:
            await message.clear_reaction(e)
            del(msg_emoji[msg_emoji.index(e)])
    
    for i in range(0, count):
        if vars.emoji_numbers[i] not in msg_emoji:
            await message.add_reaction(vars.emoji_numbers[i])


class DiscordConnector:
    def __init__(self, token, owner_id, refresh_time, tautulli_channel_id, tautulli_connector, analytics, use_embeds, plex_pass):
        self.token = token
        self.owner_id = owner_id
        self.refresh_time = refresh_time
        self.tautulli_channel_id = tautulli_channel_id
        self.tautulli_channel = None
        self.tautulli = tautulli_connector
        self.analytics = analytics
        self.use_embeds = use_embeds
        self.plex_pass = plex_pass
        self.client = discord.Client()
        self.on_ready = self.client.event(self.on_ready)

    async def on_ready(self):
        info('Connected to Discord.')
        await start_bot(discord_connector=self, analytics=self.analytics)

    def connect(self):
        info('Connecting to Discord...')
        self.client.run(self.token)

    async def edit_message(self, previous_message):
        """
        Collect new summary info, replace old message with new one
        :param previous_message: discord.Message to replace
        :return: new discord.Message
        """
        new_message, count = self.tautulli.refresh_data()
        
        # For performance and aesthetics, edit the old message if 1) the old message is the newest message in the channel, or 2) if the only messages that are newer were written by this bot (which would be stream stop messages that have aleady been deleted)
        use_old_message = False
        async for msg in self.tautulli_channel.history(limit=100):
            if msg.author != self.client.user:
                use_old_message = False
                break
            elif msg.id == previous_message.id:
                use_old_message = True
                break
        
        if use_old_message:
            if self.use_embeds and (len(previous_message.embeds) == 0 or new_message.to_dict() != previous_message.embeds[0].to_dict()):
                debug("Editing old message")
                await previous_message.edit(embed=new_message, content=None) # reset content to None to remove startup message
            elif not self.use_embeds and previous_message.content != new_message:
                debug("Editing old message")
                await previous_message.edit(content=new_message, embed=None)
            new_message = previous_message
        else:
            debug("Sending new message")
            try:
                await previous_message.delete()
            except Exception as e:
                debug("Failed to delete old (specified) message: {}".format(e))
                await tautulli_channel.purge(check=is_me)
            if self.use_embeds:
                new_message = await self.tautulli_channel.send(embed=new_message)
            else:
                new_message = await self.tautulli_channel.send(content=new_message)
        
        if self.plex_pass:
            await add_emoji_number_reactions(message=new_message, count=count)
            
            # check to see if the user clicked a reaction *while* they were being added
            cache_msg = await new_message.channel.fetch_message(new_message.id)
            for reaction in cache_msg.reactions:
                if reaction.count > 1:
                    async for user in reaction.users():
                        if user.id == self.owner_id:
                            loc = vars.emoji_numbers.index(str(reaction.emoji))
                            debug("Stopping stream {}".format(loc))
                            stopped_message = self.tautulli.stop_stream(stream_number=loc)
                            info(stopped_message)
                            end_notification = await self.tautulli_channel.send(content=stopped_message)
                            await asyncio.sleep(min([5,self.refresh_time]))
                            await end_notification.delete()
                            await new_message.clear_reaction(str(reaction.emoji))
                            return new_message
                            
            def check(reaction, user):
                return user.id == self.owner_id and reaction.message.id == new_message.id and str(reaction.emoji) in vars.emoji_numbers

            try:
                reaction, user = await self.client.wait_for('reaction_add', timeout=float(self.refresh_time), check=check)
            except asyncio.TimeoutError as e:
                pass
            else:
                loc = vars.emoji_numbers.index(str(reaction.emoji))
                debug("Stopping stream {}".format(loc))
                stopped_message = self.tautulli.stop_stream(stream_number=loc)
                info(stopped_message)
                end_notification = await self.tautulli_channel.send(content=stopped_message)
                await asyncio.sleep(min([5,self.refresh_time]))
                await end_notification.delete()
                await new_message.clear_reaction(str(reaction.emoji))
        else:
            await asyncio.sleep(self.refresh_time)
        return new_message

    async def get_tautulli_channel(self):
        info(f"Getting channel ID {self.tautulli_channel_id}")
        self.tautulli_channel = self.client.get_channel(self.tautulli_channel_id)
        info(f"Channel ID {self.tautulli_channel_id} collected.")
        return self.tautulli_channel

    async def get_old_message_in_tautulli_channel(self):
        """
        Get the last message sent in the Tautulli channel, used to start the bot loop
        :return: discord.Message
        """
        last_bot_message_id = ""
        while last_bot_message_id == "":
            async for msg in self.tautulli_channel.history(limit=100):
                if msg.author == self.client.user:
                    last_bot_message_id = msg.id
                    await msg.clear_reactions()
                    break
            if last_bot_message_id == "":
                info("Couldn't find old message, sending 'Start up'")
                await self.tautulli_channel.send(content="Start up")
        return await self.tautulli_channel.fetch_message(last_bot_message_id)
