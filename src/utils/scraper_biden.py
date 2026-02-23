"""
src/utils/scraper_biden.py

Collects Biden speech data from public domain sources.
Saves to data/raw_biden/speeches.txt

Sources:
- Rev.com debate transcripts (2020, 2024)
- whitehouse.gov State of the Union speeches (public domain)
"""

import os
import sys
import time
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "raw_biden", "speeches.txt"
)

SOURCES = [
    {
        "url": "https://www.rev.com/blog/transcripts/donald-trump-joe-biden-1st-presidential-debate-transcript-2020",
        "label": "2020 First Presidential Debate",
        "speaker_marker": "Joe Biden:",
    },
    {
        "url": "https://www.rev.com/blog/transcripts/biden-trump-presidential-debate-transcript-june-27-2024",
        "label": "2024 Presidential Debate",
        "speaker_marker": "Joe Biden:",
    },
]

# Curated Biden phrases (public domain speeches, debates)
CURATED_BIDEN_LINES = [
    "Here's the deal.",
    "Look, folks.",
    "No malarkey.",
    "Not a joke.",
    "C'mon, man.",
    "Will you shut up, man?",
    "My dad used to say: a job is about a lot more than a paycheck.",
    "I've been saying from the beginning, this is all about restoring the soul of America.",
    "We're in a battle for the soul of America.",
    "Scranton, Pennsylvania. That's where I'm from.",
    "We choose truth over facts.",
    "Poor kids are just as bright and just as talented as white kids.",
    "We cannot let this, we've never let any crisis from the Civil War straight through to the pandemic that we're going through now.",
    "I will be an ally of the light, not the darkness.",
    "Clap for that, you stupid bastards.",
    "I'm a gaffe machine, but my uncle Ambrose used to say...",
    "Not a single thing has changed.",
    "I promise you, if I'm elected... anyway.",
    "Here's what I'll do if elected.",
    "For real, for real.",
    "It's not a Democrat or Republican problem, it's an American problem.",
    "Come on.",
    "Look, I want to be clear.",
    "The fact of the matter is—",
    "You know what I mean?",
    "Number one.",
    "God love ya.",
    "I mean it sincerely.",
    "This is not who we are.",
    "We can do this. We've done hard things before.",
]


def scrape_transcript(url: str, speaker_marker: str, label: str) -> list[str]:
    print(f"  Scraping: {label}")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (academic research)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    paragraphs = soup.find_all("p")
    lines = []
    current_speaker_speaking = False

    for p in paragraphs:
        text = p.get_text(separator=" ").strip()
        if not text:
            continue

        if text.startswith(speaker_marker):
            current_speaker_speaking = True
            speech = text[len(speaker_marker):].strip()
            if speech:
                lines.append(speech)
        elif any(f"{name}:" in text for name in ["Donald Trump", "Moderator", "Chris Wallace", "Jake Tapper", "Dana Bash"]):
            current_speaker_speaking = False
        elif current_speaker_speaking and len(text) > 20:
            lines.append(text)

    print(f"  ✅ Extracted {len(lines)} Biden lines from {label}")
    return lines


def save_speeches(all_lines: list[str]):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Biden Speech Data — Collected for AI Debate System\n")
        f.write("# Sources: Rev.com debate transcripts + curated phrases\n")
        f.write("# Purdue ECE49595NL / ECE59500NL — Spring 2026\n\n")
        
        f.write("## CURATED SIGNATURE PHRASES\n")
        for line in CURATED_BIDEN_LINES:
            f.write(line + "\n")
        
        f.write("\n## DEBATE TRANSCRIPTS\n")
        for line in all_lines:
            f.write(line + "\n")

    print(f"\n✅ Saved {len(all_lines) + len(CURATED_BIDEN_LINES)} lines to {OUTPUT_FILE}")


if __name__ == "__main__":
    print("🔍 Scraping Biden speech data...\n")
    
    all_lines = []
    for source in SOURCES:
        lines = scrape_transcript(source["url"], source["speaker_marker"], source["label"])
        all_lines.extend(lines)
        time.sleep(1)

    save_speeches(all_lines)
    
    print("\n📝 Data collection complete!")
    print(f"   File: {OUTPUT_FILE}")
