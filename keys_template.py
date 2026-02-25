# keys_template.py
# Backward-compatible local config file.
# Preferred production setup is environment variables:
#   AZURE_OPENAI_KEY
#   AZURE_OPENAI_ENDPOINT
#   AZURE_OPENAI_API_VERSION
#   AZURE_OPENAI_DEPLOYMENT
#   AZURE_OPENAI_FAST_DEPLOYMENT (optional)
#   AZURE_SPEECH_KEY
#   AZURE_SPEECH_REGION
#
# Copy this file to keys.py only for local development.
# NEVER commit keys.py to source control.

# --- Azure OpenAI (GPT-4) ---
azure_openai_key      = "YOUR_AZURE_OPENAI_KEY"
azure_openai_endpoint = "YOUR_AZURE_OPENAI_ENDPOINT"   # e.g. https://xxxxx.openai.azure.com/openai/deployments/gpt-4/chat/completions?api-version=2024-08-01-preview
azure_openai_region   = "eastus"
azure_openai_api_version = "2024-08-01-preview"
azure_openai_deployment  = "gpt-4"                     # your deployment name
azure_openai_fast_deployment = "gpt-4o-mini"           # optional, used by fact-checker

# --- Azure Speech (STT + TTS) ---
azure_key    = "YOUR_AZURE_SPEECH_KEY"
azure_region = "eastus"                                # e.g. "eastus", "westus2"
azure_endpoint = "https://YOUR_REGION.api.cognitive.microsoft.com/"
