import sys
import os
import asyncio
import discord
# Add the parent directory to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import libTempo
import yt_dlp as youtube_dl

async def search(query:str, user: discord.User, count:int=5, key = None):
    ydl_opts = {
        'default_search': 'ytsearch',  # Use YouTube search
        'ignoreerrors': True,  # Ignore any errors during extraction
        'quiet': True  # Suppress console output
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        search_results = ydl.extract_info(f"ytsearch5:{query}", download=False)
    results = []
    # Process the search results
    for result in search_results['entries'][:count]:
        video_title = result['title']
        video_url = result['webpage_url']
        length = result['duration']
        author = result["channel"]
        results.append(libTempo.Song(None or user, video_title, author, "youtube", length, video_url))
    return results

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.url = data.get('url')
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        youtube_dl.utils.bug_reports_message = lambda: ''
        ydl_opts = {
            'format': 'bestaudio/best',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0'
        }
        ffmpeg_options = {
            'options': '-vn',
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        }
        ytdl = youtube_dl.YoutubeDL(ydl_opts)
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.sanitize_info(ytdl.extract_info(url, download=not stream)))
        if 'entries' in data:
            # take first item from a youtube playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


async def getstream(url: str, user: discord.User = None):
    return await YTDLSource.from_url(url, loop=asyncio.get_event_loop(), stream=True)


async def getplaylist(url: str, user: discord.User, key = None):
    """
    Extract songs from a YouTube playlist URL
    Expected URL format: https://www.youtube.com/playlist?list={playlist_id}
    """
    ydl_opts = {
        'extract_flat': True,  # Don't download, just extract metadata
        'ignoreerrors': True,  # Ignore any errors during extraction
        'quiet': True,  # Suppress console output
        'no_warnings': True,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            playlist_info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise ValueError(f"Failed to extract YouTube playlist: {str(e)}")
    
    if not playlist_info or 'entries' not in playlist_info:
        raise ValueError("Invalid YouTube playlist URL or playlist is empty")
    
    songs = []
    playlist_title = playlist_info.get('title', 'Unknown Playlist')
    
    # Process each entry in the playlist
    for entry in playlist_info['entries']:
        if entry is not None:  # Sometimes entries can be None if removed/private
            video_title = entry.get('title', 'Unknown Title')
            video_id = entry.get('id', '')
            video_url = entry.get('url') or f"https://www.youtube.com/watch?v={video_id}"
            duration = entry.get('duration', 0) or 0  # Handle None duration
            uploader = entry.get('uploader', 'Unknown Artist')
            
            songs.append(libTempo.Song(user, video_title, uploader, "youtube", duration, video_url))
    
    return songs, playlist_title


def auth(username, key):
    return ""