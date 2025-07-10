import sys
import os
import asyncio
import discord
# Add the parent directory to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import libTempo
import librespot.core as lbc
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
import spotipy

async def search(query:str, user: discord.User, count:int=5, key = None):
    session = lbc.Session.Builder().stored(key).create()
    oauth_token = session.tokens().get("playlist-read")
    sp = spotipy.Spotify(auth=oauth_token)
    results = sp.search(q=query, type='track', limit=count)["tracks"]["items"]
    
    songs = []
    for result in results[:count]:
        video_title = result['name']
        video_url = result['uri']
        length = int(result['duration_ms']/1000)
        author = ", ".join([result["artists"][i]["name"] for i in range(len(result["artists"]))])
        songs.append(libTempo.Song(None or user, video_title, author, "spotify", length, video_url))

    return songs

class ByteAudioSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, stream,volume=0.5):
        super().__init__(source,volume)
        self.stream = stream
    @classmethod
    async def get_stream(cls, stream):
        ffmpeg_options = {
            'options': '-vn',
        }
        return cls(discord.FFmpegPCMAudio(stream, **ffmpeg_options, pipe=True), stream=stream)


async def getstream(url: str, user: discord.User):
    key = libTempo.getuserdata(user)["keys"]["spotify"]
    session = lbc.Session.Builder().stored(key).create()
    track_id = TrackId.from_uri(url)
    stream = session.content_feeder().load(track_id, VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH), False, None)
    audio = stream.input_stream
    song = await ByteAudioSource.get_stream(stream=audio.stream())
    return song



async def getplaylist(url: str, user: discord.User, key = None):
    """
    Extract songs from a Spotify playlist URL
    Expected URL format: https://open.spotify.com/playlist/{playlist_id}
    """
    try:
        session = lbc.Session.Builder().stored(key).create()
        oauth_token = session.tokens().get("playlist-read")
        sp = spotipy.Spotify(auth=oauth_token)
    except Exception as e:
        raise ValueError(f"Failed to authenticate with Spotify: {str(e)}")
    
    # Extract playlist ID from URL
    if "playlist/" in url:
        playlist_id = url.split("playlist/")[1].split("?")[0]
    else:
        raise ValueError("Invalid Spotify playlist URL")
    
    try:
        # Get playlist info and tracks
        playlist = sp.playlist(playlist_id)
        tracks = sp.playlist_tracks(playlist_id)
    except Exception as e:
        raise ValueError(f"Failed to fetch Spotify playlist: {str(e)}")
    
    songs = []
    
    # Process all tracks (handle pagination)
    while tracks:
        for item in tracks['items']:
            if item['track'] is not None:  # Sometimes tracks can be None if removed
                track = item['track']
                video_title = track['name']
                video_url = track['uri']
                length = int(track['duration_ms']/1000)
                author = ", ".join([artist["name"] for artist in track["artists"]])
                songs.append(libTempo.Song(user, video_title, author, "spotify", length, video_url))
        
        # Check if there are more tracks
        if tracks['next']:
            tracks = sp.next(tracks)
        else:
            break
    
    return songs, playlist['name']


def auth(username, key):
    try:
        session = lbc.Session.Builder() \
        .user_pass(username,key) \
        .create()
    except:
        return None
    return session.stored()
