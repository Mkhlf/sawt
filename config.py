import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", 10))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

MODELS = {
    "greeting": "openai/gpt-4o-mini", 
    "location": "openai/gpt-4o-mini", 
    "order": "openai/gpt-4o",  
    "checkout": "openai/gpt-4o", 
}

# Context token thresholds per agent (for truncation decisions)
CONTEXT_THRESHOLDS = {
    "greeting": 4000,   
    "location": 6000,   
    "order": 12000,     
    "checkout": 8000,   
}


# Menu generation uses fastest model (used in scripts/generate_menu.py)
MENU_GENERATION_MODEL = "openai/gpt-oss-120b:free"
