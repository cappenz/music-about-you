"""
Camera → GPT-4 (lyrics from image) → ElevenLabs (music).

Captures from the webcam every 3 seconds, sends a frame to GPT-4 for lyrics.
A background thread keeps generating and playing songs from the latest lyrics;
when one song ends, the next one starts automatically. Press 'q' to quit.
"""

import base64
import os
import pathlib
import subprocess
import sys
import threading
import time

import cv2
from elevenlabs.client import ElevenLabs
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Set OPENAI_API_KEY in your environment or .env file.")
if not ELEVENLABS_API_KEY:
    raise ValueError("Set ELEVENLABS_API_KEY in your environment or .env file.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

PROJECT_DIR = pathlib.Path(__file__).resolve().parent
PHOTO_PATH = PROJECT_DIR / "photo.jpg"
VIDEO_PATH = PROJECT_DIR / "output.mp4"
MUSIC_PATH = PROJECT_DIR / "output_music.mp3"
CAPTURE_INTERVAL_SEC = 3.0
MUSIC_LENGTH_MS = 20_000  # 20 seconds so full lyrics (verses + chorus) can finish

_last_lyrics: str | None = None
_lyrics_lock = threading.Lock()
_music_playing = False
_music_lock = threading.Lock()


def _trim_trailing_silence(path: pathlib.Path) -> None:
    """Remove silence at the end of the audio file so the song doesn't drag after lyrics end."""
    path = path.resolve()
    if not path.exists():
        return
    tmp = path.with_suffix(".tmp.mp3")
    # ffmpeg: remove trailing silence (1 segment of 0.3s+ at -35dB)
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(path),
            "-af", "silenceremove=start_periods=0:stop_periods=1:stop_duration=0.3:stop_threshold=-35dB",
            "-y", str(tmp),
        ],
        capture_output=True,
        timeout=30,
    )
    if result.returncode == 0 and tmp.exists():
        tmp.replace(path)
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass


def _play_audio(path: pathlib.Path) -> None:
    path = path.resolve()
    if not path.exists():
        return
    if sys.platform == "darwin":
        subprocess.run(["afplay", str(path)], check=False, capture_output=True)
    elif sys.platform == "linux":
        subprocess.run(["ffplay", "-nodisp", "-autoexit", str(path)], check=False, capture_output=True)
    else:
        print(f"[Play] {path} (play manually if needed)")


def _music_loop() -> None:
    global _last_lyrics, _music_playing
    while True:
        with _lyrics_lock:
            lyrics = _last_lyrics
            if lyrics is not None:
                _last_lyrics = None  # consume so we don't regenerate the same song
        if not lyrics:
            time.sleep(0.5)
            continue
        try:
            with _music_lock:
                _music_playing = True
            print("Generating song...")
            track = elevenlabs_client.music.compose(
                prompt=lyrics,
                music_length_ms=MUSIC_LENGTH_MS,
            )
            with open(MUSIC_PATH, "wb") as f:
                for chunk in track:
                    f.write(chunk)
            try:
                _trim_trailing_silence(MUSIC_PATH)
            except Exception:
                pass  # play untrimmed if ffmpeg missing or fails
            print("Playing...")
            _play_audio(MUSIC_PATH)
        except Exception as e:
            print(f"Music error: {e}")
            time.sleep(2)
        finally:
            with _music_lock:
                _music_playing = False


# On macOS use AVFoundation so we get the built-in MacBook camera
if sys.platform == "darwin":
    cam = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
else:
    cam = cv2.VideoCapture(0)
if not cam.isOpened():
    raise RuntimeError("Could not open camera (on Mac this is usually the built-in FaceTime camera).")

frame_width = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(str(VIDEO_PATH), fourcc, 20.0, (frame_width, frame_height))
last_capture_time = time.time() - CAPTURE_INTERVAL_SEC

music_thread = threading.Thread(target=_music_loop, daemon=True)
music_thread.start()

try:
    while True:
        ret, frame = cam.read()
        if not ret:
            break
        cv2.imshow("Camera", frame)
        out.write(frame)
        # Only ask GPT for new lyrics after the current song has finished
        with _music_lock:
            music_busy = _music_playing
        if not music_busy and time.time() - last_capture_time >= CAPTURE_INTERVAL_SEC:
            cv2.imwrite(str(PHOTO_PATH), frame)
            img_bytes = PHOTO_PATH.read_bytes()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            response = openai_client.responses.create(
                model="gpt-4o",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Write COMPLETE pop song lyrics from start to finish. Do NOT stop after the first verse. Include: verse 1, then chorus, then verse 2 (and verse 3 if you like), then chorus again—so the full song is on the page. Base it on this image (the person's appearance, vibe, style). Memorable hook, simple rhymes, chorus that repeats. Output every line of the song; never truncate or end early after a verse."},
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"},
                        ],
                    }
                ],
            )
            with _lyrics_lock:
                _last_lyrics = response.output_text
            print(_last_lyrics)
            last_capture_time = time.time()
        if cv2.waitKey(1) == ord("q"):
            break
finally:
    cam.release()
    out.release()
    cv2.destroyAllWindows()
