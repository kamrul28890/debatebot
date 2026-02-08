import requests
import json
import sys
import os

# Add root directory to sys.path to find keys.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import keys

class DebateBrain:
    def __init__(self, persona="trump"):
        self.persona = persona
        self.api_key = keys.azure_openai_key
        # The endpoint provided includes the full path, so we use it directly
        self.endpoint = keys.azure_openai_endpoint 
        
        self.headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }

    def generate_reply(self, conversation_history):
        """
        Sends conversation history to Azure OpenAI and gets a reply.
        """
        
        # System prompt based on persona
        system_content = "You are Donald Trump." if self.persona == "trump" else "You are Joe Biden."
        system_content += " You are in a debate. Keep answers short (under 50 words). React to the last statement."

        messages = [{"role": "system", "content": system_content}] + conversation_history

        payload = {
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.9, # High temperature for more "creative/chaotic" responses
            "top_p": 0.95,
        }

        try:
            response = requests.post(self.endpoint, headers=self.headers, json=payload)
            response.raise_for_status() # Raise error for bad status codes
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
            
        except Exception as e:
            return f"[Error generating response: {e}]"

# Simple test to run directly
if __name__ == "__main__":
    brain = DebateBrain(persona="trump")
    print(brain.generate_reply([{"role": "user", "content": "What about the economy?"}]))