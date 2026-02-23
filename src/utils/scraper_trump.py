"""
src/utils/scraper_trump.py

Collects Trump speech data from public domain sources.
Saves to data/raw_trump/speeches.txt

Sources:
- Rev.com debate transcripts (2020, 2024)
- Public presidential records
"""

import os
import sys
import time
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "raw_trump", "speeches.txt"
)

# Public debate transcript URLs (Rev.com)
SOURCES = [
    # 2020 First Presidential Debate — Trump vs Biden
    {
        "url": "https://www.rev.com/blog/transcripts/donald-trump-joe-biden-1st-presidential-debate-transcript-2020",
        "label": "2020 First Presidential Debate",
        "speaker_marker": "Donald Trump:",
    },
    # 2024 Presidential Debate
    {
        "url": "https://www.rev.com/blog/transcripts/biden-trump-presidential-debate-transcript-june-27-2024",
        "label": "2024 Presidential Debate",
        "speaker_marker": "Donald Trump:",
    },
]

# Curated Trump phrases for persona prompt enrichment (manually collected from public records)
CURATED_TRUMP_LINES = [
    "Nobody knew healthcare could be so complicated.",
    "I know more about ISIS than the generals do, believe me.",
    "We're going to win so much, you're going to get tired of winning.",
    "I've done more for the Black community than any other president since Abraham Lincoln.",
    "The fake news media is the enemy of the people.",
    "When Mexico sends its people, they're not sending their best.",
    "I alone can fix it.",
    "I could stand in the middle of Fifth Avenue and shoot somebody and I wouldn't lose any voters.",
    "Make America Great Again.",
    "You're fired.",
    "It's a disaster. A total disaster.",
    "Tremendous. Just tremendous.",
    "Many people are saying...",
    "Believe me.",
    "That I can tell you.",
    "We had the greatest economy in the history of our country.",
    "Wrong.",
    "Excuse me, I'm talking.",
    "The most unfair witch hunt in the history of our country.",
    "We're going to build a wall, and Mexico is going to pay for it.",
    "Frankly, they should be ashamed of themselves.",
    "China. China is the problem.",
    "Nobody's ever done what we've done.",
    "I know the best people.",
    "The failing New York Times.",
    "Crooked Hillary.",
    "Sleepy Joe.",
    "Lyin' Ted.",
    "Little Marco.",
    "Low Energy Jeb.",
]


def scrape_transcript(url: str, speaker_marker: str, label: str) -> list[str]:
    """Scrape a transcript page and extract only the target speaker's lines."""
    print(f"  Scraping: {label}")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (academic research)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    
    # Rev.com transcript pages have <p> tags with speaker names
    paragraphs = soup.find_all("p")
    lines = []
    current_speaker_speaking = False

    for p in paragraphs:
        text = p.get_text(separator=" ").strip()
        if not text:
            continue

        if text.startswith(speaker_marker):
            current_speaker_speaking = True
            # Extract the speech after the speaker name
            speech = text[len(speaker_marker):].strip()
            if speech:
                lines.append(speech)
        elif any(f"{name}:" in text for name in ["Joe Biden", "Moderator", "Chris Wallace", "Jake Tapper", "Dana Bash"]):
            current_speaker_speaking = False
        elif current_speaker_speaking and len(text) > 20:
            lines.append(text)

    print(f"  ✅ Extracted {len(lines)} Trump lines from {label}")
    return lines


def save_speeches(all_lines: list[str]):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Trump Speech Data — Collected for AI Debate System\n")
        f.write("# Sources: Rev.com debate transcripts (public) + curated phrases\n")
        f.write("# Purdue ECE49595NL / ECE59500NL — Spring 2026\n\n")
        
        f.write("## CURATED SIGNATURE PHRASES\n")
        for line in CURATED_TRUMP_LINES:
            f.write(line + "\n")
        
        f.write("\n## DEBATE TRANSCRIPTS\n")
        for line in all_lines:
            f.write(line + "\n")

    print(f"\n✅ Saved {len(all_lines) + len(CURATED_TRUMP_LINES)} lines to {OUTPUT_FILE}")


if __name__ == "__main__":
    print("🔍 Scraping Trump speech data...\n")
    
    all_lines = []
    for source in SOURCES:
        lines = scrape_transcript(source["url"], source["speaker_marker"], source["label"])
        all_lines.extend(lines)
        time.sleep(1)  # be polite to the server

    save_speeches(all_lines)
    
    print("\n📝 Data collection complete!")
    print(f"   File: {OUTPUT_FILE}")
    print("   Use this data to enrich the persona prompt in src/brain/personas/trump.txt")
