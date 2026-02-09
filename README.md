# music about you

Camera → GPT-4 (lyrics from image) → ElevenLabs (music). Uses your webcam to generate pop song lyrics from what it sees, then turns them into short songs.

## Setup

1. **Install dependencies:** `uv sync` (or `pip install -e .`)
2. **API keys:** Copy `.env.example` to `.env` and add your keys:
   - `OPENAI_API_KEY` — [platform.openai.com](https://platform.openai.com/api-keys)
   - `ELEVENLABS_API_KEY` — [elevenlabs.io](https://elevenlabs.io)

## Run

```bash
uv run python main.py
```

Or `python run.py`. Press **q** to quit. Optional: `brew install ffmpeg` to trim trailing silence from songs.
