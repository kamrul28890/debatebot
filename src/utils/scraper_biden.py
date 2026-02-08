import requests
from bs4 import BeautifulSoup
import os
import time

# --- Configuration ---
# Targeting specific recent major speeches for clean data
URLS = [
    "https://www.presidency.ucsb.edu/documents/address-before-joint-session-the-congress-the-state-the-union-28", # 2022 SOTU
    "https://www.presidency.ucsb.edu/documents/address-before-joint-session-the-congress-the-state-the-union-29", # 2023 SOTU
    "https://www.presidency.ucsb.edu/documents/remarks-exchange-with-reporters-arrival-from-wilmington-delaware-10" # Candid remarks
]
OUTPUT_DIR = os.path.join("data", "raw_biden")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "speeches_compiled.txt")

def scrape_biden():
    print("🍦 Starting Biden Data Extraction...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    full_text = ""
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    for i, url in enumerate(URLS):
        try:
            print(f"   [...] Fetching source {i+1}...")
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # UCSB stores speech text in <div class="field-docs-content">
            content_div = soup.find('div', class_='field-docs-content')
            
            if content_div:
                text = content_div.get_text(separator="\n")
                full_text += f"\n--- SOURCE {url} ---\n"
                full_text += text
                print(f"       [+] Extracted {len(text)} chars.")
            else:
                print("       [!] Could not find speech content on page.")
                
            time.sleep(1) # Be polite to the server
            
        except Exception as e:
            print(f"   [!] Error fetching {url}: {e}")

    # Write Data
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"   [+] Saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    scrape_biden()