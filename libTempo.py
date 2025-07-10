import os
import importlib
import sys
import asyncio
import sqlite3
import discord
import random
import numpy as np
try:
    from tts import generate
except ImportError:
    generate = None  # TTS is optional
try:
    from discord.ext import voice_recv
except ImportError:
    voice_recv = None  # Voice features are optional
try:
    import math
    from faster_whisper import WhisperModel
    import io
    import wave
    import array
except ImportError:
    WhisperModel = None  # Whisper is optional
from collections import defaultdict
import json

def load_settings(version):
    # create the database if it doesnt already exist
    with sqlite3.connect("tempo.db") as db:
        cursor = db.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, data TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS DBInfo (version TEXT)")
        # set version if databse was just created (first run)
        cursor.execute("SELECT * FROM DBInfo")
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO DBInfo(version) VALUES (?)", (version,))
        else:
            pass # handle version updates here
        db.commit()
        default = {
            "UpdateDM": True,
            "Default": "youtube",
            "Key": None,
            "Voice": False
        }
        cursor.execute("INSERT OR IGNORE INTO users (id, data) VALUES (?, ?)", (0, json.dumps(default)))
        rows = cursor.execute("SELECT * FROM users WHERE id=?", (0,)).fetchall()
        return json.loads(rows[0][1])


def getuserbackend(id):
        userdata = getuserdata(id)
        platform = userdata["platform"]
        key = userdata["keys"][userdata["platform"]]
        if platform == "default":
            settings = load_settings(None)
            platform = settings["Default"]
            key = settings["Key"]
        return platform, key



def getuserdata(id):
    with sqlite3.connect("tempo.db") as db:
        cursor = db.cursor()
        rows = cursor.execute("SELECT * FROM users WHERE id=?", (id,)).fetchall()
        if rows:
            return json.loads(rows[0][1])
        else:
            default = {
                "platform": "default",
                "keys": {"youtube": None}
            }
            cursor.execute("INSERT INTO users (id, data) VALUES (?, ?)", (id, json.dumps(default)))
            return default

def saveuserdata(id, data):
    with sqlite3.connect("tempo.db") as db:
        cursor = db.cursor()
        cursor.execute("UPDATE users SET data=? WHERE id=?", (json.dumps(data), id))
        db.commit()

def setuserplatform(id, platform):
    userdata = getuserdata(id)
    if platform not in userdata["keys"] and platform != "default":
        return False
    userdata["platform"] = platform
    saveuserdata(id, userdata)
    return True

def setuserkey(id, platform, key):
    userdata = getuserdata(id)
    userdata["keys"][platform] = key
    saveuserdata(id, userdata)

def rmuserkey(id, platform):
    userdata = getuserdata(id)
    userdata["keys"][platform] = None
    if platform == userdata["platform"]:
        userdata["platform"] = "youtube"
    saveuserdata(id, userdata)

def getuserkey(id, platform):
    userdata = getuserdata(id)
    return userdata["keys"][platform]



def import_backends(backends_folder: str):
    """Imports all valid backends from the Backends folder and returns a dictionary of them."""
    backends = {}

    sys.path.append(backends_folder)

    backend_files = [file for file in os.listdir(backends_folder) if file.endswith(".py") and file != "verify.py"]
    verify = importlib.import_module("verify", "Backends/Music/verify.py")
    for file in backend_files:
        module_name = os.path.splitext(file)[0]  
        module_path = os.path.join(backends_folder, file) 
        try:
            module = importlib.import_module(module_name)
            backendtype = verify.verify(module)
            if backendtype != 0:
                backends[module_name] = module
                backends[module_name].type = backendtype
            else:
                print(f"Failed to import backend {module_name}: Backend is missing 1 or more required functions.")
                continue
        except ImportError as e:
            print(f"Failed to import backend {module_name}: {e}")

    return backends    


class Song:
    def __init__(self, user, title, author, backend, length, url):
        self.user = user
        self.title = title
        self.author = author
        self.backend = backend
        self.length = length
        self.url = url
        
class Playlist:
    def __init__(self, title:str, entries:list):
        self.title = title
        self.entries = [[i,entry] for i,entry in enumerate(entries)]
        self.shuffle = False
        self.loop = 0 # 0 is off, 1 is full queue, 2 is song

    def __len__(self):
        return len(self.entries)
    
    def delete(self, index):
        self.entries.pop(index)

    def add(self, entry):
        self.entries.append([max([i[0] for i in self.entries])+1 if len(self.entries) > 0 else 0, entry])

    def move(self, index, newindex):
        self.entries.insert(newindex, self.entries.pop(index))

    def GetCurrentEntry(self):
        return self.entries[0][1]
    
    def next(self):
        if self.loop == 1:
            self.entries.append(self.entries[0])
        if len(self.entries) > 0 and self.loop!=2:
            self.entries.pop(0)

    def getAll(self):
        return [entry[1] for entry in self.entries]
    def SetShuffle(self, mode: bool):
        if not self.shuffle and mode == True:
            currentsong = self.entries.pop(0)
            random.shuffle(self.entries)
            self.entries.insert(0,currentsong)
        if mode == False:
            currentsong = self.entries.pop(0)
            self.entries.sort()
            self.entries.insert(0,currentsong)
    def SetLoop(self, mode:int):
        if mode not in [0,1,2]:
            raise ValueError("Loop mode must be [0,1,2]")
        self.loop = mode

class MusicPlayer:
    def __init__(self, backends, voice:bool = False):
        self.playlist = Playlist("queue", [])
        self.vc = None
        self.active = False
        self.backends = backends

        self.mixer = Mixer()

        self._voice = voice and voice_recv is not None
        self._textassistant = TextAssistant() if self._voice else None  
        self._sink = WhisperSink() if self._voice and WhisperModel is not None else None
        self._commands = ["play", "resume", "pause", "stop"]
        self._is_listening = False
        self._results = []
        self._skip = False
        self._paused = False 
        self._stop = False
    async def listen(self):
        if self.vc != None :
            if self.active == False:
                asyncio.create_task(self._listen())
            else:
                raise RuntimeError("MusicPlayer.listen() cannot be run twice concurrently.")
        else:
            raise RuntimeError("MusicPlayer must be bound to a vc to listen.")
    async def _listen(self):
        if self._voice and self._sink is not None:
            self.vc.listen(self._sink)
    async def _play(self):
        self.active = True
        while len(self.playlist) > 0:
            song = self.playlist.GetCurrentEntry()
            stream = await self.backends[song.backend].getstream(song.url, song.user.id)
            self.mixer.set_source1(stream)
            self.vc.play(self.mixer)
            while self.vc.is_playing() or self.mixer.is_paused():
                if self._stop:
                    self.mixer.stop()
                    self._stop = False
                if self._skip == True:
                    self.mixer.stop()
                    self._skip = False
                if self._paused == True:
                    if not self.mixer.is_paused():
                        self.mixer.pause()
                else:
                    if self.mixer.is_paused():
                        self.mixer.resume()
                if self._voice and False: # disable this for now
                    text = self._sink.getupdate()
                    if text is not None:
                        text = text.split(":")
                        id = text[0]
                        text = "".join(text[1:])
                        command, output = self._textassistant.run(text)
                        if command == None and output == None:
                            if generate is not None:
                                speech = generate("Sorry, I didnt quite get that,") 
                                source2 = discord.FFmpegPCMAudio(speech, pipe=True)
                                self.mixer.set_source2(source2)
                        if command == "play" and output != None:
                            if not self._is_listening:
                                self._results = self.backends["youtube"].search(output) # placeholder, look up users prefered backend + add User object
                                self._sink.lock(id)
                                if generate is not None:
                                    speech = generate("which would you like to play. " + " ".join([f"{num}. {self._results[i].title} by {self._results[i].author}" for i in range(len(self._results))])) 
                                    source2 = discord.FFmpegPCMAudio(speech, pipe=True)
                                    self.mixer.set_source2(source2)
                                self._is_listening = True
                        else:
                            num = self._commands.index(command)
                            if num == 0 or num == 1:
                                self.resume()
                            if num == 2:
                                self.pause()
                            if num == 3:
                                self.stop()
                    if self._is_listening == True:
                        update = self._sink.getupdate()
                        if update != None:
                            key = [i in update for i in ["one","two","three","four","five"]]
                            if True in key:
                                num = key.index(True)
                                self.add_song(self._results[num])
                                self._is_listening = False
                await asyncio.sleep(0.1)
            self.playlist.next()
        await self.leave_channel()
        self.active = False
    async def join_channel(self, vc:discord.VoiceChannel):
        if voice_recv is not None:
            self.vc = await vc.connect(cls=voice_recv.VoiceRecvClient)
        else:
            self.vc = await vc.connect()
        await self.listen()
    async def leave_channel(self):
        await self.vc.disconnect()
        self.vc = None
    def add_song(self, song:Song):
        self.playlist.add(song)
    def play(self):
        if self.vc != None :
            if self.active == False:
                asyncio.create_task(self._play())
            else:
                raise RuntimeError("MusicPlayer.play() cannot be run twice concurrently.")
        else:
            raise RuntimeError("MusicPlayer must be bound to a vc to play.")
    def pause(self):
        if self.active:
            self._paused = True
        else:
            raise RuntimeError("Nothing is playing.")
    def resume(self):
        if self.active:
            self._paused = False
        else:
            raise RuntimeError("Nothing is playing.")
    def stop(self):
        self.playlist = Playlist("queue", [])
        self._stop = True
    def getQueue(self):
        entries = self.playlist.getAll()
        return [[entry.title, entry.author, entry.length] for entry in entries]
    def skip(self):
        self._skip = True
        


class Mixer(discord.AudioSource):
    def __init__(self, source1: discord.AudioSource = None, source2: discord.AudioSource = None):
        self.source1 = source1
        self.source2 = source2
        self._paused = False

    def overlay_audio(self, audio1_bytes, audio2_bytes, sample_width=2, num_channels=2, sample_rate=48000, volume:int = 0.3):
        # Number of samples per 20ms for stereo audio
        num_samples = int(0.02 * sample_rate * num_channels)
        
        # Convert bytes-like objects to numpy arrays
        audio1 = np.frombuffer(audio1_bytes, dtype=np.int16).reshape(-1, num_channels).copy().astype(float)
        audio2 = np.frombuffer(audio2_bytes, dtype=np.int16).reshape(-1, num_channels)

        #lower audio so you can hear the DJ
        audio1 *= volume

        # Ensure both audio samples have the same length
        min_length = min(len(audio1), len(audio2))
        audio1 = audio1[:min_length]
        audio2 = audio2[:min_length]
        
        # Overlay the audio by summing the samples
        combined_audio = audio1 + audio2
        
        # Prevent clipping by scaling the combined audio
        max_val = np.iinfo(np.int16).max
        min_val = np.iinfo(np.int16).min
        combined_audio = np.clip(combined_audio, min_val, max_val)
        
        # Convert the combined audio back to bytes
        combined_audio_bytes = combined_audio.astype(np.int16).tobytes()
        
        return combined_audio_bytes


    def read(self):
        if self.source1 is not None and self._paused == False:
            a = self.source1.read()
        else:
            a = None
            
        if self.source2 is not None:
            b = self.source2.read()
        else:
            b = None
        
        if a and b:  
            return self.overlay_audio(a, b)
        elif a:  
            return a
        elif b:  
            return b
        else:  
            return b''
    
    def pause(self):
        self._paused = True
    
    def resume(self):
        self._paused = False
    
    def stop(self):
        self.source1 = None

    def is_paused(self):
        return self._paused

    def set_source1(self, new_source: discord.AudioSource):
        # Set the new source1
        self.source1 = new_source
    def set_source2(self, new_source: discord.AudioSource):
        # Set the new source1
        self.source2 = new_source

class BytesAudioSource(discord.AudioSource):
    def __init__(self, byte_io):
        self.byte_io = byte_io

    def read(self):
        # Read 20ms worth of audio (3840 bytes)
        return self.byte_io.read(3840)

    def cleanup(self):
        # Cleanup when the source is no longer needed
        self.byte_io.close()




if WhisperModel is not None and voice_recv is not None:
    class WhisperSink(voice_recv.AudioSink):
        def __init__(self,triggerwords=None):
            super().__init__()
            self.user_packets = defaultdict(lambda: array.array("B"))
            model = "base" # hardcoded, should be configurable
            self.whisper = WhisperModel(model, device="auto", compute_type="int8")
            self.latest_text = None
            self.triggerwords = triggerwords or ["tempo","play","stop","pause"]
            self._lock = None
        def wants_opus(self) -> bool:
            return False
        def write(self, user: discord.User | discord.Member | None, data: voice_recv.VoiceData):
            if isinstance(data.packet, voice_recv.rtp.SilencePacket):
                return

            if user is None:
                return
            

            user_id = user.id
            self.user_packets[user_id].extend(data.pcm)

            speaking_length = len(self.user_packets[user_id]) / (48000 * 2 * 2)  # assuming PCM format with 48kHz, stereo, 16-bit audio

            if math.floor(speaking_length) == 5:
                self._transcribe(user_id)
                self.user_packets[user_id] = array.array("B")
        def _transcribe(self, user_id):
            if self._lock != None and self._lock != user_id:
                return
            pcm_data = self.user_packets[user_id]
            audio_data = np.array(pcm_data, dtype="B")
            audio_buffer = io.BytesIO()
            with wave.open(audio_buffer, "wb") as wav_file:
                wav_file.setnchannels(2)  # Stereo
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(48000)  # 48 kHz
                wav_file.writeframes(audio_data.tobytes())
            audio_buffer.seek(0)
            segments, info = self.whisper.transcribe(audio_buffer, beam_size=5)
            text = "".join([segment.text for segment in segments])
            if True in [i in text.lower() for i in self.triggerwords] or self._lock != None:
                if text.startswith(self.triggerwords[0]):
                    text = text[len(self.triggerwords[0])+1:] # get rid of tempo wake word as it isnt a command
                self.latest_text = str(user_id) + ":" + text
        def getupdate(self):
            if self.latest_text != None:
                text = self.latest_text
                self.latest_text = None
                return text
        def lock(self, id):
            self._lock = id
        def unlock(self):
            self._lock = None
        def cleanup(self):
            return

        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_start(self, member: discord.Member):
            self.user_packets[member.id] = array.array("B")

        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_stop(self, member: discord.Member):
            self._transcribe(member.id)
            self.user_packets[member.id] = array.array("B")
else:
    class WhisperSink:
        def __init__(self, *args, **kwargs):
            pass



class TextAssistant:
    def __init__(self):
        pass
    def _classify_and_extract_song(self, text):
        # Define the possible commands and their corresponding keywords
        commands = {"play": ["play", "play song"],
                    "stop": ["stop"],
                    "pause": ["pause"],
                    "resume": ["resume"]}

        # Initialize song name as None
        song_name = None

        # Classify the input text
        for command, keywords in commands.items():
            if any(keyword in text.lower() for keyword in keywords):
                if command == "play":
                    # Split the text to separate the song name from the "play" command
                    words = text.split()
                    if len(words) > 1:
                        song_name = ' '.join(words[1:])
                return command, song_name

        return None, None
    def run(self,text):
        return self._classify_and_extract_song(text)