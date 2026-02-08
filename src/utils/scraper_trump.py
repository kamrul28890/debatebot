import requests
import os

# --- Configuration ---
SOURCE_URL = "https://raw.githubusercontent.com/ryanmcdermott/trump-speeches/master/speeches.txt"
OUTPUT_DIR = os.path.join("data", "raw_trump")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "speeches.txt")

def scrape_trump():
    print("🦅 Starting Trump Data Extraction...")
    
    try:
        response = requests.get(SOURCE_URL)
        response.raise_for_status()
        
        # Ensure directory exists
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Write Data
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(response.text)
            
        print(f"   [+] Successfully downloaded {len(response.text) / 1024:.2f} KB of data.")
        print(f"   [+] Saved to: {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"   [!] Error: {e}")

if __name__ == "__main__":
    scrape_trump()