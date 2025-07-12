import os
import sys
import asyncio
import libTempo
import discord
import sqlite3
import discord
from discord.ext import commands, tasks
import typing
import dotenv
import aiohttp
version = "2.0.0"



# set intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


# make the bot
bot = commands.Bot(command_prefix = '$',intents=intents, activity=discord.Game(name='Play some music!'))
bot.settings = libTempo.load_settings(version)
bot.backends = libTempo.import_backends("Backends/Music")


#update checks
bot.ownerupdated = False
@tasks.loop(hours=1)
async def updatecheck():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.github.com/repos/jumpers775/Tempo/releases/latest') as resp:
            resp = await resp.json()
            latestversion = resp["tag_name"] # keep for formatting in message
            newestversion = int("".join(resp["tag_name"].split(".")))
            currentversion = int("".join(version.split("."))) 
            if newestversion > currentversion:
                print(f"Update Available!\n{version} --> {latestversion}")
                if bot.settings["updateDM"] and (not bot.ownerupdated or updateversion != newestversion):
                    updateversion = newestversion
                    app_info = await bot.application_info()
                    bot.ownerupdated = True
                    user = bot.get_user(app_info.owner.id)
                    await user.send(f"Update Available!\n{version} --> {newestversion}\n {resp['html_url']}\n\n To update, run `git pull`, then `conda env update -f environment.yml`.")

@bot.event
async def on_ready():
    await updatecheck()
    print(f"{bot.user} is online.")
    bot.players = {}
    for guild in bot.guilds:
        bot.players[guild.id] = libTempo.MusicPlayer(bot.backends, bot.settings["Voice"])

@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: typing.Optional[typing.Literal["~"]] = None) -> None:
    #Global command sync
    if not guilds:
        if spec == "~":
            bot.tree.copy_global_to(guild=ctx.guild)
            fmt = await bot.tree.sync(guild=ctx.guild)
        else:
            fmt = await bot.tree.sync()
        await ctx.send(
            f"Synced {len(fmt)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return
    # Local command sync
    assert guilds is not None
    fmt = 0
    for guild in guilds:
        try:
            await bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            fmt += 1

    await ctx.send(f"Synced the tree to {fmt}/{len(guilds)} guilds.")@commands.is_owner()



@discord.app_commands.command(name='play', description='plays a song')
async def play(interaction: discord.Interaction, song:str, platform:str = None):
    try:
        channel = interaction.user.voice.channel
    except:
        await interaction.response.send_message("you are not currently in a voice channel.")
        return
    permissions = channel.permissions_for(interaction.guild.me)
    if not permissions.connect or not permissions.speak:
        await interaction.response.send_message("I do not have permission to play music in that voice channel.")
        return
    userbackends = libTempo.getuserdata(interaction.user.id)
    if platform != None and platform not in userbackends["keys"] and platform != "default":
        await interaction.response.send_message("You are not authorized to use that platform.")
        return
    await interaction.response.send_message("Searching...")
    if platform == None or platform == "default":
        userbackend = libTempo.getuserbackend(interaction.user.id)
    else:
        userbackend = [platform, libTempo.getuserkey(interaction.user.id, platform)]
    result = await bot.backends[userbackend[0]].search(song, interaction.user, key=userbackend[1])
    options = []
    for i in range(len(result)):
        options.append(discord.SelectOption(label=f'{i+1}) '+ result[i].title, description=f'By {result[i].author}', emoji='🎧'))
    view = PlaySelectListView(options=options, interaction=interaction,results=result)
    await interaction.edit_original_response(content="Choose a song", view=view)
@play.autocomplete('platform')
async def shuffle_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    platforms = list(bot.backends.keys())
    platforms.insert(0, "default")
    return [
        discord.app_commands.Choice(name=platform, value=platform)
        for platform in platforms if current.lower() in platform.lower()
    ]


#view class to select the correct song.
class PlaySelectListView(discord.ui.View):
    def __init__(self, *, timeout = 180, options: dict, interaction: discord.Interaction,results: list):
        super().__init__(timeout=timeout)
        self.add_item(PlaySelectSong(option=options, interaction=interaction,results=results))

class PlaySelectSong(discord.ui.Select):
    def __init__(self,option: dict, interaction: discord.Interaction, results: list):
        #set options to the possibilities for the song
        self.results=results
        #allow access to the original interaction
        self.original_interaction = interaction
        # ask for an option to be selected
        super().__init__(placeholder="Select an option",options=option)
    async def callback(self, interaction: discord.Interaction):
        selection = int(self.values[0].split(") ")[0])-1
        option = self.results[selection]
        if bot.players[interaction.guild.id].active == False:
            try:
                await bot.players[interaction.guild.id].join_channel(self.original_interaction.user.voice.channel) 
            except:
                await self.original_interaction.edit_original_response(content="you are not currently in a voice channel.", view=None)
                return
        bot.players[interaction.guild.id].add_song(option)
        if len(bot.players[interaction.guild.id].playlist) == 1:
            await self.original_interaction.edit_original_response(content=f"Now Playing {option.title}.", view=None)
            bot.players[interaction.guild.id].play()
        else:
            await self.original_interaction.edit_original_response(content=f"{option.title} added to the queue.", view=None)

bot.tree.add_command(play)


@discord.app_commands.command(name='stop', description='Stops the current session')
async def stop(interaction: discord.Interaction):
    if bot.players[interaction.guild.id].active == False:
        await interaction.response.send_message("There is nothing to stop.")
        return
    bot.players[interaction.guild.id].stop()
    await interaction.response.send_message("Session stopped.")

bot.tree.add_command(stop)


@discord.app_commands.command(name='pause', description='Pauses the current song')
async def pause(interaction: discord.Interaction):
    if bot.players[interaction.guild.id].active == False:
        await interaction.response.send_message("There is nothing to pause.")
        return
    bot.players[interaction.guild.id].pause()
    await interaction.response.send_message(f"Paused {bot.players[interaction.guild.id].playlist.GetCurrentEntry().title}.")

bot.tree.add_command(pause)

@discord.app_commands.command(name='resume', description='Resumes the current song')
async def resume(interaction: discord.Interaction):
    if bot.players[interaction.guild.id].active == False:
        await interaction.response.send_message("There is nothing to resume.")
        return
    bot.players[interaction.guild.id].resume()
    await interaction.response.send_message(f"Resumed {bot.players[interaction.guild.id].playlist.GetCurrentEntry().title}.")

bot.tree.add_command(resume)

@discord.app_commands.command(name='skip', description='Skips the current song')
async def skip(interaction: discord.Interaction):
    if bot.players[interaction.guild.id].active == False:
        await interaction.response.send_message("There is nothing to skip.")
        return
    title = bot.players[interaction.guild.id].playlist.GetCurrentEntry().title
    bot.players[interaction.guild.id].skip()
    await interaction.response.send_message(f"Skipped {title}.")

bot.tree.add_command(skip)


@discord.app_commands.command(name='queue', description='Shows the Queue')
async def queue(interaction: discord.Interaction):
    if len(bot.players[interaction.guild.id].playlist) == 0:
        await interaction.response.send_message("There is no music playing.")
        return
    
    entries = bot.players[interaction.guild.id].getQueue()
    embed = discord.Embed(title="Current Song Queue", color=0x00ff00)
    
    # Calculate total duration
    total_duration = 0
    for song in entries:
        total_duration += song[2]

    # Convert total duration to mm:ss format
    total_minutes, total_seconds = divmod(total_duration, 60)
    total_duration_str = f"{total_minutes}:{total_seconds:02d}"

    # Add song details to the embed
    for index, (title, author, duration) in enumerate(entries):
        if index == 0:
            embed.add_field(name=f"**{index + 1}. {title} [Now Playing]**", value=f"By {author}.", inline=False)
        else:
            embed.add_field(name=f"**{index + 1}. {title}**", value=f" By {author}", inline=False)
    embed.add_field(name="Shuffle", value='On' if bot.players[interaction.guild.id].playlist.shuffle != False else 'Off', inline=True)
    embed.add_field(name="Loop", value=["Off","Queue","Song"][bot.players[interaction.guild.id].playlist.loop], inline=True)

    # Add total duration at the bottom
    embed.add_field(name="Total Duration", value=total_duration_str, inline=False)
    await interaction.response.send_message(embed=embed)



bot.tree.add_command(queue)



@discord.app_commands.command(name='shuffle', description='sets shuffle mode.')
async def shuffle(interaction: discord.Interaction, mode:bool):
    bot.players[interaction.guild.id].playlist.SetShuffle(mode)
    await interaction.response.send_message(f"Shuffle {'enabled' if mode else 'disabled'}.")
bot.tree.add_command(shuffle)

@discord.app_commands.command(name='loop', description='sets loop mode.')
async def loop(interaction: discord.Interaction, mode:str):
    if mode not in ["off", "queue", "song"]:
        await interaction.response.send_message("Invalid mode.")
        return
    bot.players[interaction.guild.id].playlist.SetLoop(["off", "queue", "song"].index(mode))
    await interaction.response.send_message(f"Loop set to {mode}.")
bot.tree.add_command(loop)
@loop.autocomplete('mode')
async def shuffle_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    statuses = ['off', 'song','queue']
    return [
        discord.app_commands.Choice(name=status, value=status)
        for status in statuses if current.lower() in status.lower()
    ]


@discord.app_commands.command(name='auth', description='Authorizes user for a platform')
async def auth(interaction: discord.Interaction, platform:str, username: str, key:str):
    if platform not in bot.backends:
        await interaction.response.send_message("Invalid platform.", ephemeral=True)
        return
    key = bot.backends[platform].auth(username, key)
    if key == None:
        await interaction.response.send_message("Invalid credentials.", ephemeral=True)
        return
    libTempo.setuserkey(interaction.user.id, platform, key)
    await interaction.response.send_message(f"Authorized {platform} account.", ephemeral=True)
@auth.autocomplete('platform')
async def shuffle_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    platforms = list(bot.backends.keys())
    return [
        discord.app_commands.Choice(name=platform, value=platform)
        for platform in platforms if current.lower() in platform.lower()
    ]
bot.tree.add_command(auth)


@discord.app_commands.command(name='deauth', description='Deauthorizes user for a platform')
async def deauth(interaction: discord.Interaction, platform:str):
    if platform not in bot.backends:
        await interaction.response.send_message("Invalid platform.")
        return
    libTempo.rmuserkey(interaction.user.id, platform)
    await interaction.response.send_message(f"Deauthorized {platform} account.", ephemeral=True)
@deauth.autocomplete('platform')
async def shuffle_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    platforms = list(bot.backends.keys())
    return [
        discord.app_commands.Choice(name=platform, value=platform)
        for platform in platforms if current.lower() in platform.lower()
    ]
bot.tree.add_command(deauth)

@discord.app_commands.command(name='setplatform', description='sets a users preferred platform')
async def setplatform(interaction: discord.Interaction, platform:str):
    if platform not in bot.backends and platform != "default":
        await interaction.response.send_message("Invalid platform.")
        return
    set = libTempo.setuserplatform(interaction.user.id, platform)
    if set:
        await interaction.response.send_message(f"Set preferred platform to {platform}.")
    else:
        await interaction.response.send_message(f"You do not have access to {platform}.", ephemeral=True)
@setplatform.autocomplete('platform')
async def shuffle_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    platforms = list(bot.backends.keys())
    platforms.insert(0, "default")
    return [
        discord.app_commands.Choice(name=platform, value=platform)
        for platform in platforms if current.lower() in platform.lower()
    ]
bot.tree.add_command(setplatform)



@discord.app_commands.command(name='settings', description='Shows the current settings')
@commands.has_permissions(administrator=True)
async def settings(interaction: discord.Interaction):
    embed = discord.Embed(title="Current Settings", color=0x00ff00)
    for key, value in bot.settings.items():
        if key not in ["Key"]: # don't show the key
            embed.add_field(name=key, value=value, inline=False)
    await interaction.response.send_message(embed=embed)
bot.tree.add_command(settings)


@discord.app_commands.command(name='setsetting', description='Sets a setting')
@commands.has_permissions(administrator=True)
async def setsetting(interaction: discord.Interaction, setting:str, value:str):
    if setting not in bot.settings or setting == "Key":
        await interaction.response.send_message("Invalid setting.")
        return
    if setting.lower() == "voice":
        await interaction.response.send_message("Voice is currently disabled, wait for a future update to enable it.")
        return
    try:
        if setting in ["Voice", "updateDM"]:
            value = bool(value)
    except:
        await interaction.response.send_message("Invalid value.")
        return
    bot.settings[setting] = value
    settings = bot.settings
    settings[setting] = value
    libTempo.saveuserdata(0, settings)
    await interaction.response.send_message(f"Set {setting} to {value}. A restart is required to apply changes.")
@setsetting.autocomplete('setting')
async def shuffle_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    settings = list(bot.settings.keys())
    settings.remove("Key")
    return [
        discord.app_commands.Choice(name=setting, value=setting)
        for setting in settings if current.lower() in setting.lower()
    ]

bot.tree.add_command(setsetting)


@discord.app_commands.command(name='queueplaylist', description='imports a playlist from spotify or youtube and adds to queue')
async def queueplaylist(interaction: discord.Interaction, url: str, platform: str = None):
    try:
        channel = interaction.user.voice.channel
    except:
        await interaction.response.send_message("you are not currently in a voice channel.")
        return
    permissions = channel.permissions_for(interaction.guild.me)
    if not permissions.connect or not permissions.speak:
        await interaction.response.send_message("I do not have permission to play music in that voice channel.")
        return
    
    # Determine platform from URL if not specified
    if platform is None:
        if "spotify.com" in url and "playlist/" in url:
            platform = "spotify"
        elif ("youtube.com" in url or "youtu.be" in url) and "playlist?list=" in url:
            platform = "youtube"
        else:
            await interaction.response.send_message("Could not determine platform from URL. Please ensure you're using a valid playlist URL and specify the platform parameter if needed.")
            return
    
    # Check user authorization for the platform
    userbackends = libTempo.getuserdata(interaction.user.id)
    if platform not in userbackends["keys"] and platform != "default":
        await interaction.response.send_message("You are not authorized to use that platform.")
        return
    
    # Check if backend supports playlists
    if not hasattr(bot.backends[platform], 'getplaylist'):
        await interaction.response.send_message(f"Platform {platform} does not support playlist importing.")
        return
    
    await interaction.response.send_message("Importing playlist to queue...")
    
    try:
        # Get user key for the platform
        if platform == "default":
            userbackend = libTempo.getuserbackend(interaction.user.id)
            platform = userbackend[0]
            key = userbackend[1]
        else:
            key = libTempo.getuserkey(interaction.user.id, platform)
        
        # Import the playlist
        songs, playlist_name = await bot.backends[platform].getplaylist(url, interaction.user, key=key)
        
        if not songs:
            await interaction.edit_original_response(content="Playlist is empty or could not be imported.")
            return
        
        # Join voice channel if not already connected
        if bot.players[interaction.guild.id].active == False:
            try:
                await bot.players[interaction.guild.id].join_channel(interaction.user.voice.channel) 
            except:
                await interaction.edit_original_response(content="Could not join voice channel.")
                return
        
        # Add all songs to the queue
        songs_added = 0
        for song in songs:
            bot.players[interaction.guild.id].add_song(song)
            songs_added += 1
        
        # Start playing if this is the first song in queue
        if len(bot.players[interaction.guild.id].playlist) == songs_added:
            await interaction.edit_original_response(content=f"Imported playlist '{playlist_name}' with {songs_added} songs to queue. Now playing first song.")
            bot.players[interaction.guild.id].play()
        else:
            await interaction.edit_original_response(content=f"Imported playlist '{playlist_name}' with {songs_added} songs. Added to queue.")
            
    except Exception as e:
        await interaction.edit_original_response(content=f"Failed to import playlist to queue: {str(e)}")

@queueplaylist.autocomplete('platform')
async def queueplaylist_platform_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    platforms = list(bot.backends.keys())
    platforms.insert(0, "default")
    return [
        discord.app_commands.Choice(name=platform, value=platform)
        for platform in platforms if current.lower() in platform.lower()
    ]

bot.tree.add_command(queueplaylist)


@discord.app_commands.command(name='importplaylist', description='imports a playlist from spotify or youtube to your personal playlists')
async def importplaylist(interaction: discord.Interaction, url: str, name: str = None, platform: str = None):
    # Determine platform from URL if not specified
    if platform is None:
        if "spotify.com" in url and "playlist/" in url:
            platform = "spotify"
        elif ("youtube.com" in url or "youtu.be" in url) and "playlist?list=" in url:
            platform = "youtube"
        else:
            await interaction.response.send_message("Could not determine platform from URL. Please ensure you're using a valid playlist URL and specify the platform parameter if needed.")
            return
    
    # Check user authorization for the platform
    userbackends = libTempo.getuserdata(interaction.user.id)
    if platform not in userbackends["keys"] and platform != "default":
        await interaction.response.send_message("You are not authorized to use that platform.")
        return
    
    # Check if backend supports playlists
    if not hasattr(bot.backends[platform], 'getplaylist'):
        await interaction.response.send_message(f"Platform {platform} does not support playlist importing.")
        return
    
    await interaction.response.send_message("Importing playlist to your library...")
    
    try:
        # Get user key for the platform
        if platform == "default":
            userbackend = libTempo.getuserbackend(interaction.user.id)
            platform = userbackend[0]
            key = userbackend[1]
        else:
            key = libTempo.getuserkey(interaction.user.id, platform)
        
        # Import the playlist
        songs, playlist_name = await bot.backends[platform].getplaylist(url, interaction.user, key=key)
        
        if not songs:
            await interaction.edit_original_response(content="Playlist is empty or could not be imported.")
            return
        
        # Use provided name or default to original playlist name
        saved_playlist_name = name if name else playlist_name
        
        # Check if playlist name already exists
        if libTempo.get_user_playlist(interaction.user.id, saved_playlist_name) is not None:
            await interaction.edit_original_response(content=f"You already have a playlist named '{saved_playlist_name}'. Please choose a different name.")
            return
        
        # Create the playlist
        libTempo.create_user_playlist(interaction.user.id, saved_playlist_name)
        
        # Add all songs to the user's playlist
        songs_added = 0
        for song in songs:
            song_dict = libTempo.song_to_dict(song)
            libTempo.add_song_to_user_playlist(interaction.user.id, saved_playlist_name, song_dict)
            songs_added += 1
        
        await interaction.edit_original_response(content=f"Imported playlist '{playlist_name}' as '{saved_playlist_name}' with {songs_added} songs to your library.")
            
    except Exception as e:
        await interaction.edit_original_response(content=f"Failed to import playlist: {str(e)}")

@importplaylist.autocomplete('platform')
async def importplaylist_platform_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    platforms = list(bot.backends.keys())
    platforms.insert(0, "default")
    return [
        discord.app_commands.Choice(name=platform, value=platform)
        for platform in platforms if current.lower() in platform.lower()
    ]

bot.tree.add_command(importplaylist)


@discord.app_commands.command(name='playlists', description='lists your saved playlists')
async def playlists(interaction: discord.Interaction):
    user_playlists = libTempo.get_user_playlists(interaction.user.id)
    
    if not user_playlists:
        await interaction.response.send_message("You don't have any saved playlists yet. Use `/importplaylist` to create one!")
        return
    
    embed = discord.Embed(title="Your Playlists", color=0x00ff00)
    
    for playlist_name, songs in user_playlists.items():
        song_count = len(songs)
        # Calculate total duration
        total_duration = sum(song.get('length', 0) for song in songs)
        total_minutes, total_seconds = divmod(total_duration, 60)
        duration_str = f"{total_minutes}:{total_seconds:02d}"
        
        embed.add_field(
            name=f"🎵 {playlist_name}", 
            value=f"{song_count} songs • {duration_str}", 
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

bot.tree.add_command(playlists)


@discord.app_commands.command(name='playplaylist', description='plays songs from one of your saved playlists')
async def playplaylist(interaction: discord.Interaction, playlist_name: str):
    try:
        channel = interaction.user.voice.channel
    except:
        await interaction.response.send_message("you are not currently in a voice channel.")
        return
    permissions = channel.permissions_for(interaction.guild.me)
    if not permissions.connect or not permissions.speak:
        await interaction.response.send_message("I do not have permission to play music in that voice channel.")
        return
    
    # Get the user's playlist
    user_playlist = libTempo.get_user_playlist(interaction.user.id, playlist_name)
    if user_playlist is None:
        await interaction.response.send_message(f"You don't have a playlist named '{playlist_name}'.")
        return
    
    if not user_playlist:
        await interaction.response.send_message(f"Playlist '{playlist_name}' is empty.")
        return
    
    await interaction.response.send_message(f"Loading playlist '{playlist_name}'...")
    
    try:
        # Join voice channel if not already connected
        if bot.players[interaction.guild.id].active == False:
            try:
                await bot.players[interaction.guild.id].join_channel(interaction.user.voice.channel) 
            except:
                await interaction.edit_original_response(content="Could not join voice channel.")
                return
        
        # Convert song dictionaries back to Song objects and add to queue
        songs_added = 0
        for song_dict in user_playlist:
            song = libTempo.dict_to_song(song_dict, bot)
            bot.players[interaction.guild.id].add_song(song)
            songs_added += 1
        
        # Start playing if this is the first song in queue
        if len(bot.players[interaction.guild.id].playlist) == songs_added:
            await interaction.edit_original_response(content=f"Playing playlist '{playlist_name}' with {songs_added} songs.")
            bot.players[interaction.guild.id].play()
        else:
            await interaction.edit_original_response(content=f"Added playlist '{playlist_name}' with {songs_added} songs to queue.")
            
    except Exception as e:
        await interaction.edit_original_response(content=f"Failed to play playlist: {str(e)}")

@playplaylist.autocomplete('playlist_name')
async def playplaylist_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    user_playlists = libTempo.get_user_playlists(interaction.user.id)
    playlist_names = list(user_playlists.keys())
    return [
        discord.app_commands.Choice(name=name, value=name)
        for name in playlist_names if current.lower() in name.lower()
    ][:25]  # Discord limit

bot.tree.add_command(playplaylist)


@discord.app_commands.command(name='deleteplaylist', description='deletes one of your saved playlists')
async def deleteplaylist(interaction: discord.Interaction, playlist_name: str):
    success = libTempo.delete_user_playlist(interaction.user.id, playlist_name)
    if success:
        await interaction.response.send_message(f"Deleted playlist '{playlist_name}'.")
    else:
        await interaction.response.send_message(f"You don't have a playlist named '{playlist_name}'.")

@deleteplaylist.autocomplete('playlist_name')
async def deleteplaylist_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> typing.List[discord.app_commands.Choice[str]]:
    user_playlists = libTempo.get_user_playlists(interaction.user.id)
    playlist_names = list(user_playlists.keys())
    return [
        discord.app_commands.Choice(name=name, value=name)
        for name in playlist_names if current.lower() in name.lower()
    ][:25]  # Discord limit

bot.tree.add_command(deleteplaylist)


@discord.app_commands.command(name='move', description='moves songs in the queue')
async def move(interaction: discord.Interaction, start:int, end:int):
    if bot.players[interaction.guild.id].active == False:
        await interaction.response.send_message("There is no music playing.")
        return
    if start < 1 or end < 1 or start > len(bot.players[interaction.guild.id].playlist) or end > len(bot.players[interaction.guild.id].playlist):
        await interaction.response.send_message("Invalid position.")
        return
    bot.players[interaction.guild.id].playlist.move(start-1, end-1)
    await interaction.response.send_message(f"Moved song from position {start} to {end}.")   
bot.tree.add_command(move)

dotenv.load_dotenv()
try:
    token = os.environ['token']
except:
    token = input("no token provided, Please input it here: ")
    with open('.env', 'w') as envfile:
        envfile.write('token = '+ token)


bot.run(token)
