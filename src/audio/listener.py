import azure.cognitiveservices.speech as speechsdk
import sys
import os

# Add root directory to sys.path to find keys.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import keys

class Ear:
    def __init__(self):
        self.speech_config = speechsdk.SpeechConfig(
            subscription=keys.azure_key, 
            region=keys.azure_region
        )
        self.speech_config.speech_recognition_language = "en-US"
        
        # Setup audio input (default microphone)
        self.audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        self.recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config, 
            audio_config=self.audio_config
        )

    def listen(self):
        print("🎤 Listening...")
        
        # 'recognize_once' listens for a single utterance (good for turn-taking)
        # For continuous listening (interruption), we will need 'start_continuous_recognition' later.
        result = self.recognizer.recognize_once_async().get()
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            print(f"   [Heard]: {result.text}")
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            print("   [!] No speech recognized.")
            return None
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print(f"   [!] Error: {cancellation.reason}")
            if cancellation.reason == speechsdk.CancellationReason.Error:
                print(f"   [!] Error Details: {cancellation.error_details}")
            return None

if __name__ == "__main__":
    ear = Ear()
    ear.listen()