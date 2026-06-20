import os
from ollama import Client
from dotenv import load_dotenv

# Charger les variables du fichier .env
load_dotenv()

# Initialisation du client Cloud
client = Client(
    host="https://ollama.com",
    headers={'Authorization': f"Bearer {os.environ.get('OLLAMA_API_KEY')}"}
)

try:
    print("--- Test de génération ---")
    response = client.chat(
        model='deepseek-v4-flash', # Teste avec le nom de base sans le :1.5b
        messages=[{'role': 'user', 'content': 'Bonjour, es-tu prêt pour ZenifyTrip ?'}],
    )
    print("Réponse du modèle :")
    print(response['message']['content'])

except Exception as e:
    print(f"Erreur lors du test : {e}")