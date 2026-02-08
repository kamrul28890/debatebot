import azure.cognitiveservices.speech as speechsdk
import sys
import os

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import keys

class Mouth:
    def __init__(self, persona="trump"):
        self.speech_config = speechsdk.SpeechConfig(
            subscription=keys.azure_key, 
            region=keys.azure_region
        )
        
        # Select voice
        if persona == "trump":
            self.speech_config.speech_synthesis_voice_name = "en-US-DavisNeural"
        else:
            self.speech_config.speech_synthesis_voice_name = "en-US-GuyNeural"
            
        # LIVE OUTPUT (Real Speakers)
        self.audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)

        self.synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config, 
            audio_config=self.audio_config
        )

    def speak(self, text):
        print(f"🗣️  {text}")
        # 'speak_text_async' sends the data to Azure. 
        # '.get()' waits for it to finish playing.
        try:
            self.synthesizer.speak_text_async(text).get()
        except Exception as e:
            print(f"   [!] TTS Error: {e}")

if __name__ == "__main__":
    bot = Mouth(persona="trump")
    bot.speak("We are back live. No more files.")