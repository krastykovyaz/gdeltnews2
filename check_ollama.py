import requests
import os
from dotenv import load_dotenv
import config

def is_ollama_alive(url=config.OLLAMA_URL, MODEL_NAME=config.MODEL_NAME) -> bool:
    try:
        payload = {
        "model": MODEL_NAME,
        "prompt": 'blabla',
        "stream": False
        }
        r = requests.post(f"{url}/api/generate",json=payload,timeout=300)
        return r.status_code == 200

    except Exception:
        return False

if __name__ == '__main__':
    if is_ollama_alive():
        print("Ollama is working")
    else:
        print("Ollama is NOT available")
