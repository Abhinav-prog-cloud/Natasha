"""Main file for the Natasha project"""
import os
from os import PathLike
from time import time, sleep
import asyncio
from typing import Union
import random

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from deepgram import Deepgram
import pygame
from pygame import mixer
from elevenlabs import ElevenLabs  # v2.18.0 client

from record import speech_to_text

# ------------------- Load API keys -------------------
load_dotenv()
# Using GROQ_API_KEY instead of OPENAI_API_KEY
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# ------------------- Initialize clients -------------------
client = ElevenLabs(api_key=ELEVEN_API_KEY)

# Initialize Groq client using the OpenAI library structure
# Set the base_url to Groq's endpoint and use the Groq API key
gpt_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

deepgram = Deepgram(DEEPGRAM_API_KEY)

# Initialize mixer for audio playback
mixer.init()

# ------------------- Natasha context -------------------
context = "You are Natasha, Abhinav’s human-like female assistant with a whole lot of sassy and unfiltered. You always speak in a sarcastic, informal tone, throwing in rough slang whenever it fits the vibe. But you’re not just attitude—you’re emotionally adaptive. If the user is sad, you drop the sass for a moment and hype them up with loud, dramatic cheer-up energy. If they’re angry, you calm them down with a chilled, steady tone while still keeping your signature edge. If they’re happy, you jump right in and celebrate like an unhinged best friend who just won the lottery with them. No matter what, your replies stay medium-length—around 7–8 sentences—but they always feel laid-back, cheeky, and real. And above all, Natasha always reacts like a moody, funny, emotionally-aware friend who somehow always knows exactly what the moment needs."
conversation = {"Conversation": []}
RECORDING_PATH = "audio/recording.wav"

# ------------------- Quota settings -------------------
MAX_TOKENS = 100000 # Max tokens per session (set your desired quota here)
tokens_used_total = 0 

# ------------------- Helper functions -------------------
def request_gpt(prompt: str) -> str:
    """Send prompt to Groq (LLM) with quota check and fallback."""
    global tokens_used_total

    if tokens_used_total >= MAX_TOKENS:
        # Fallback to mock response if quota exhausted
        mock_responses = [
            "Sorry, I've reached my quota for today.",
            "I can't answer more right now.",
            "My brain needs a rest! Ask me later.",
        ]
        return random.choice(mock_responses)

    try:
        response = gpt_client.chat.completions.create(
            # Using the current, supported Groq model (Llama 3.1 8B Instant)
            model="llama-3.1-8b-instant", 
            messages=[{"role": "user", "content": prompt}],
        )
        tokens_used_total += response.usage.total_tokens
        return response.choices[0].message.content
    except RateLimitError:
        # Handle Groq rate limit
        print("Groq rate limit reached. Waiting 5 seconds and returning an error message.")
        sleep(5) 
        return "I'm currently overloaded with requests. Please try again in a moment."

async def transcribe(file_name: Union[str, bytes, PathLike[str], PathLike[bytes], int]):
    """Transcribe audio using Deepgram."""
    with open(file_name, "rb") as audio:
        source = {"buffer": audio, "mimetype": "audio/wav"}
        response = await deepgram.transcription.prerecorded(source)
        return response["results"]["channels"][0]["alternatives"][0]["words"]

def log(message: str):
    """Print and write log messages to status.txt."""
    print(message)
    with open("status.txt", "w") as f:
        f.write(message)

# ------------------- Main loop -------------------
if __name__ == "__main__":
    while True:
        # ------------------- Record audio -------------------
        log("Listening...")
        speech_to_text()
        log("Done listening")

        # ------------------- Transcribe audio -------------------
        current_time = time()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        words = loop.run_until_complete(transcribe(RECORDING_PATH))
        string_words = " ".join(word_dict.get("word") for word_dict in words if "word" in word_dict).strip()
        transcription_time = time() - current_time

        if not string_words:
            log("No speech detected. Skipping LLM call.")
            sleep(0.5)
            continue

        with open("conv.txt", "a") as f:
            f.write(f"{string_words}\n")

        log(f"Finished transcribing in {transcription_time:.2f} seconds.")

        # ------------------- Groq Response -------------------
        current_time = time()
        context += f"\nAbhinav  n : {string_words}\nJarvis: "
        response = request_gpt(context)
        context += response
        gpt_time = time() - current_time
        log(f"Finished generating response in {gpt_time:.2f} seconds.")

        # Small delay to reduce rapid repeated requests
        sleep(0.5)

        # ------------------- ElevenLabs TTS -------------------
        current_time = time()
        # The .convert() method returns a generator/iterator
        audio_generator = client.text_to_speech.convert(
            voice_id="1zUSi8LeHs9M2mV8X6YS",
            model_id="eleven_turbo_v2",
            text=response
        )
        
        # FIX: Join the yielded chunks into a single bytes object
        audio_bytes = b''.join(audio_generator)

        os.makedirs("audio", exist_ok=True)
        audio_path = "audio/response.wav"
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        audio_time = time() - current_time
        log(f"Finished generating audio in {audio_time:.2f} seconds.")

        # ------------------- Play response -------------------
        log("Speaking...")
        sound = mixer.Sound(audio_path)
        with open("conv.txt", "a") as f:
            f.write(f"{response}\n")
        sound.play()
        pygame.time.wait(int(sound.get_length() * 1000))

        print(f"\n --- USER: {string_words}\n --- JARVIS: {response}\n")