import azure.cognitiveservices.speech as speechsdk
import sys
import os

# Add root directory to sys.path to find keys.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import keys

class Mouth:
    def __init__(self, persona="trump"):
        self.speech_config = speechsdk.SpeechConfig(
            subscription=keys.azure_key, 
            region=keys.azure_region
        )
        
        # Select voice based on persona (Approximations available in Azure)
        # en-US-DavisNeural is a deep male voice (good for Trump-ish)
        # en-US-GuyNeural is generic male (okay for Biden)
        if persona == "trump":
            self.speech_config.speech_synthesis_voice_name = "en-US-DavisNeural"
        else:
            self.speech_config.speech_synthesis_voice_name = "en-US-GuyNeural"
            
        self.synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config, 
            audio_config=speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        )

    def speak(self, text):
        print(f"🗣️ Speaking: {text}")
        result = self.synthesizer.speak_text_async(text).get()
        
        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print(f"   [!] TTS Error: {cancellation.error_details}")

if __name__ == "__main__":
    bot = Mouth(persona="trump")
    bot.speak("We are going to have a tremendous victory.")