import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.audio.listener import Ear
from src.audio.speaker import Mouth
from src.brain.model import DebateBrain

def main():
    # --- CONFIGURATION ---
    # CHANGE THIS: "trump" for Laptop A, "biden" for Laptop B
    PERSONA = "trump" 
    OPPONENT_NAME = "Joe" if PERSONA == "trump" else "Donald"
    
    # TIMING CONFIG
    DEBATE_DURATION = 240 # 4 minutes in seconds
    start_time = time.time()
    
    print(f"🇺🇸 INITIALIZING {PERSONA.upper()} BOT 🇺🇸")
    
    ear = Ear()
    mouth = Mouth(persona=PERSONA)
    brain = DebateBrain(persona=PERSONA)
    
    # Initial 'Wake Up' phrase to start the loop if you are the first speaker
    # On Laptop A (Trump), you might want to uncomment this line to START the debate.
    # On Laptop B (Biden), keep it commented out (he waits).
    if PERSONA == "trump":
         mouth.speak(f"Hello {OPPONENT_NAME}, are you ready to lose?")

    history = []

    try:
        while True:
            # --- 1. THE MODERATOR CHECK ---
            elapsed = time.time() - start_time
            if elapsed > DEBATE_DURATION:
                print("\n🚨 TIME LIMIT REACHED!")
                mouth.speak("The moderator is cutting me off. Thank you, everybody.")
                break

            print("\n👂 Listening...")
            
            # --- 2. LISTEN ---
            heard_text = ear.listen()
            
            if heard_text:
                print(f"   [Heard]: {heard_text}")
                
                # --- 3. THINK ---
                # Add what we heard to history
                history.append({"role": "user", "content": heard_text})
                
                print("🧠 Thinking...")
                reply_text = brain.generate_reply(history)
                
                # Add what we are about to say to history
                history.append({"role": "assistant", "content": reply_text})
                
                # --- 4. SPEAK ---
                mouth.speak(reply_text)
                
                # Optional: Add a small delay so they don't talk over each other instantly
                time.sleep(1.5)

    except KeyboardInterrupt:
        print("\n🛑 Debate Terminated.")

if __name__ == "__main__":
    main()