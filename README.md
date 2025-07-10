# Tempo
 Rythm clone, a bot for streaming music.

## Info on V2

V2 of this bot is a complete rewrite of the bot. The following is planned:

- [X] Plugins
    - Each platform will be a plugin
          - This means more platforms can be supported easily
    - There will be a plugin API for custom plugins
- [ ] Speech recognition (allows you to skip/add songs/etc using your voice while the bot is playing)
    - Bot will listen for a keyword, then once it hears it will respond to the user 
    - I plan on doing this with a combo between whisper and an LLM (release will likely use phi3-mini)
    - User will be able to configure which models are in use
    - Fully disableable
    - Must be runnable on a Rasberry pi 5 with 8GB of ram
- [X] Native playlist support
- [X] Platform playlist support (spotify, youtube, etc)
- [ ] Update utility within the bot (will require owner to press a button)
- [X] Nicer UX

## Useage 

To use this bot, first install [miniconda](https://docs.anaconda.com/miniconda/) and espeak, then run the following commands:

```sh
$ conda env create -f /path/to/Tempo/environment.yml
$ conda activate Tempo
$ python bot.py
```
The bot will then prompt you for a token. Supply your bot token to it and it will run. Add it to your servers, then run `$sync` to enable the slash commands within discords UI. More detailed setup information will be included with each release.

## Updating

The bot will notify you if there is an update available. It is recommended that git is used to keep the bot up to date with the latest release on github. The bot will give you the update command when it discovers an update.

## Features

While additional platforms can be easily added, this bot features the following OOTB:

- [X] Slash commands
- [X] Youtube search
- [X] Youtube Playback
- [X] Song queue 
- [X] A way to stop all playback
- [X] A way to manipulate the queue
- [X] Shuffle playback
- [X] yt-dlp (greatly improves audio quality, however as of now randomly drops in connection)
- [X] Spotify support (search, playback, accounts)
- [X] Update notifications
- [X] Pause support
- [X] Loop support
- [X] Inbuilt playlists
- [X] Platform playlists (Spotify and YouTube)
- [X] Personal playlist library with import/save functionality
- [ ] Voice commands
- [ ] account sharing for paid platforms

## Commands

### Music Commands
- `/play <song> [platform]` - Search and play a song from the specified platform (defaults to user's preferred platform)
- `/queueplaylist <url> [platform]` - Import an entire playlist from Spotify or YouTube and add directly to queue
- `/importplaylist <url> [name] [platform]` - Import an entire playlist from Spotify or YouTube to your personal library
- `/playlists` - Show all your saved playlists
- `/playplaylist <playlist_name>` - Play songs from one of your saved playlists
- `/deleteplaylist <playlist_name>` - Delete one of your saved playlists
- `/stop` - Stop the current session
- `/pause` - Pause the current song
- `/resume` - Resume the current song
- `/skip` - Skip the current song
- `/queue` - Show the current queue
- `/shuffle <true/false>` - Enable or disable shuffle mode
- `/loop <off/queue/song>` - Set loop mode
- `/move <start> <end>` - Move a song in the queue

### Account Management
- `/auth <platform> <username> <password>` - Authorize your account for a platform (Spotify)
- `/deauth <platform>` - Remove authorization for a platform
- `/setplatform <platform>` - Set your preferred platform for searches

known issues:
 - freeze on search
