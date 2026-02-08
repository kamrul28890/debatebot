import requests
import sys
import os
import random

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import keys

class DebateBrain:
    def __init__(self, persona="trump"):
        self.persona = persona
        self.api_key = keys.azure_openai_key
        self.endpoint = keys.azure_openai_endpoint 
        
        self.headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }
        
        # Load Style Data (The "Fine-Tuning" via Prompting)
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self):
        """
        Constructs a highly specific persona prompt using scraped data patterns.
        """
        if self.persona == "trump":
            return """
            You are Donald Trump. 
            STYLE GUIDE:
            - Use short, punchy sentences. 
            - Repeat words for emphasis (e.g., "Huge. Tremendous.").
            - Use nicknames (e.g., "Sleepy Joe", "Radical Left").
            - Focus on: Borders, Economy, "The Best Numbers".
            - Never admit a mistake. Always attack.
            - If the user interrupts, say "Excuse me" or "Wrong".
            - Keep responses UNDER 50 WORDS.
            """
        else:
            return """
            You are Joe Biden.
            STYLE GUIDE:
            - Use "folksy" language (e.g., "Here's the deal", "No joke", "Malarkey").
            - Stutter slightly or trail off occasionally (use "..." or "-").
            - Focus on: The Middle Class, Unity, "My father used to say".
            - Be polite but firm.
            - Sometimes start sentences with "Look," or "Folks,".
            - Keep responses UNDER 50 WORDS.
            """

    def generate_reply(self, conversation_history):
        # We inject the System Prompt at the very start of every request
        messages = [{"role": "system", "content": self.system_prompt}] + conversation_history[-5:] # Keep only last 5 turns to save tokens

        payload = {
            "messages": messages,
            "max_tokens": 100, # Strict limit to keep debate flowing
            "temperature": 0.85, # High creativity
            "top_p": 0.95,
        }

        try:
            response = requests.post(self.endpoint, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"   [!] Brain Error: {e}")
            return "I need a moment to think."

if __name__ == "__main__":
    # Test the new personalities
    trump = DebateBrain("trump")
    print("TRUMP:", trump.generate_reply([{"role": "user", "content": "The economy is bad."}]))
    
    biden = DebateBrain("biden")
    print("BIDEN:", biden.generate_reply([{"role": "user", "content": "The economy is bad."}]))