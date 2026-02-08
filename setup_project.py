import os

# --- Configuration ---
PROJECT_NAME = "AI_Presidential_Debate"
DIRECTORIES = [
    "data/raw_trump", "data/raw_biden", "data/processed",
    "src", "src/audio", "src/brain", "src/utils",
    "tests", "logs"
]

FILES = {
    "requirements.txt": """openai
azure-cognitiveservices-speech
requests
beautifulsoup4
tiktoken
pydub
pyttsx3
colorama
numpy
pandas
""",
    "README.md": f"# {PROJECT_NAME}\n\n## Setup\n1. Install dependencies: `pip install -r requirements.txt`\n2. Run scrapers.\n",
    ".gitignore": """__pycache__/
*.pyc
keys.py
data/
logs/
.vscode/
"""
}

def create_structure():
    print(f"🚀 Initializing {PROJECT_NAME}...")
    
    # 1. Create Directories
    for folder in DIRECTORIES:
        os.makedirs(folder, exist_ok=True)
        # Add __init__.py to src subfolders
        if folder.startswith("src"):
            with open(os.path.join(folder, "__init__.py"), "w") as f:
                pass

    # 2. Create Files
    for filename, content in FILES.items():
        with open(filename, "w") as f:
            f.write(content.strip())
        print(f"   [+] Created file: {filename}")

    print("\n✅ Setup complete! Make sure 'keys.py' is in the root folder.")

if __name__ == "__main__":
    create_structure()