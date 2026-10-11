# Pip: the desktop penguin that makes you touch grass

Pip is a small, chronically online penguin who lives on your Windows desktop. His one mission is to get you off the screen.

He tracks how long you've really been at your computer. At 30 minutes he raises a hand and nudges you. At 60 minutes he turns red and starts steaming. Five minutes later he **locks your screen** until you pick a quest and prove you did it.

Everything runs locally: the language model, the vision model, speech recognition and the camera checks.

## Features

- **Quests:** outdoor (bring Pip a leaf, flower, pebble or grass, walk around the block, sit in the sun) and indoor (dance, cook, stretch, tidy, call someone).
- **Weather-aware:** if it's raining, snowing, too hot or freezing, Pip swaps outdoor quests for indoor ones.
- **Proof of quest:**
  - Item quests: hold the object up to the camera and a local vision model checks it. Screens and printed pictures are rejected, and old photos can't be reused.
  - Activity quests: you must really be away from the screen, then Pip asks a specific question and a judge model checks your answer against the question, the real weather and the time of day.
- **Growth:** Pip gets bigger and levels up with every quest, and unlocks a scarf, party hat, cape and crown.
- **Health reminders:** 20-20-20 eye rests, blink-rate and posture nudges from the webcam.
- **Extras:** to-do list Pip checks in on, a journal in Pip's own voice, a stats dashboard with streaks, voice chat, and color themes.

## Requirements

- **Windows 10 or 11** (uses Windows APIs for idle detection, the screen lock and sound)
- **Python 3.10+** (Tkinter comes with the standard installer)
- **[Ollama](https://ollama.com)** with the Gemma 3 model
- A **webcam** and a **microphone** (optional, but needed for photo proof, presence checks and voice input)

## Setup

1. Install [Ollama](https://ollama.com), then pull the model:
   ```
   ollama pull gemma3:4b
   ```
2. Install the Python packages:
   ```
   pip install -r requirements.txt
   ```
3. Run Pip (replace the file name with the name of the script in this repo):
   ```
   python pip.py
   ```
4. On first launch, Pip asks your name and what you like doing away from the screen.

The first time you use voice input, Vosk downloads a small offline speech model (about 40 MB).

## Configure it for your PC

Open the script and change these near the top:

| Setting | What it does |
|---|---|
| `PLACE`, `LAT`, `LON` | Your city, used for the weather (Open-Meteo, free, no API key) |
| `MIC_DEVICE` | Microphone index. Use `None` for the Windows default |
| `CAM_INDEX` | Camera index. `0` is usually the built-in webcam |
| `GEMMA` / `VERIFY_MODEL` | Models used. Try `gemma3:12b` for `VERIFY_MODEL` if the photo check is sloppy |
| `DEMO` | `True` gives fast timers so you can test everything quickly. Set `False` for real use |
| `CAM_MONITOR` | Turn the background camera monitoring on or off |
| `NEURAL_VOICE` | Voice used if `edge-tts` is installed |

## Testing quickly

- Set `DEMO = True` at the top of the script.
- Right-click Pip for a menu with test options: raised hand, fuming, lock now, grow a level, and the reminders.

## Emergency exit

While the screen is locked, press **Ctrl+Shift+Q** to unlock. You can disable this by setting `ALLOW_ESCAPE = False`.

## Privacy

- The language model, vision model, speech recognition and face/blink/posture analysis all run on your machine.
- The background camera monitor analyzes frames in memory and never saves them.
- Photos you capture as quest proof are saved to a local `captures/` folder.
- Your name, diary, to-do list and stats are stored locally in `pip_data.json`.
- Network use: weather (Open-Meteo), and the optional neural voice (`edge-tts`, Microsoft's cloud service). Without `edge-tts`, Pip uses the offline Windows voice.

## Files Pip creates

`pip_data.json`, `attempts.jsonl`, `crash.log` and the `captures/` folder. These are personal and are listed in `.gitignore`, so they don't get uploaded.

## How it works

The main idea: **code decides, the model talks.** A small 4B model is a great character but a bad referee, so the timers, the lock, sound effects, grant limits and the weather sanity check are plain code. Gemma only writes Pip's lines and judges answers inside strict JSON prompts.

## Built with

[Gemma 3](https://ai.google.dev/gemma) via [Ollama](https://ollama.com) · [Vosk](https://alphacephei.com/vosk/) · [OpenCV](https://opencv.org) · [pyttsx3](https://github.com/nateshmbhat/pyttsx3) · [edge-tts](https://github.com/rany2/edge-tts) (optional) · [Open-Meteo](https://open-meteo.com) · Tkinter

Made for the Hacktoberfest Open-Source AI Challenge: Touch Grass.
