import os
from ollama import Client
from dotenv import load_dotenv

load_dotenv()

client = Client(
    host="https://ollama.com",
    headers={'Authorization': f"Bearer {os.getenv('OLLAMA_API_KEY')}"}
)

try:
    models_info = client.list()
    print("--- Modèles disponibles sur ton compte Cloud Pro ---")
    for model in models_info['models']:
        print(f"Nom à utiliser : {model['model']}")
except Exception as e:
    print(f"Erreur lors de la récupération : {e}")
    
    