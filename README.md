# AI_Presidential_Debate

Two-laptop, turn-based debate demo that uses Azure Speech (STT/TTS) and Azure OpenAI chat completions to generate Trump/Biden-style replies.

## What’s in here
- `src/main.py`: entrypoint that runs the debate loop.
- `src/audio/listener.py`: microphone input with Azure Speech recognition.
- `src/audio/speaker.py`: speaker output with Azure Speech synthesis.
- `src/brain/model.py`: Azure OpenAI prompt + response generator.
- `src/utils/scraper_trump.py`: downloads Trump speech data to `data/raw_trump/`.
- `src/utils/scraper_biden.py`: scrapes Biden speech data to `data/raw_biden/`.
- `data/`: speech data outputs.
- `logs/`: runtime artifacts (if you add logging).

## Setup
1. Create a virtual environment and install dependencies:
   `pip install -r requirements.txt`
2. Create or update `keys.py` with your Azure credentials:
   - `azure_openai_key`
   - `azure_openai_endpoint` (full REST URL to your deployment)
   - `azure_openai_region`
   - `azure_openai_api_version`
   - `azure_key` (Speech key)
   - `azure_endpoint`
   - `azure_region`
3. (Optional) Run scrapers to collect reference speech text:
   - `python src/utils/scraper_trump.py`
   - `python src/utils/scraper_biden.py`

## Run
1. Open `src/main.py` and set `PERSONA = "trump"` on Laptop A, `PERSONA = "biden"` on Laptop B.
2. Start the first speaker by letting only one side speak first.
3. Run:
   `python src/main.py`

## Notes
- The debate loop is capped at 4 minutes by `DEBATE_DURATION`.
- Replies are limited to ~50 words via the prompt and token cap.
- Do not commit real keys to source control.
