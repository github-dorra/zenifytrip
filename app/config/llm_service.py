import os
import requests
from typing import Any, Optional

from ollama import Client
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")



# Initialisation client Groq + Ollama
groq_client = Groq(api_key=GROQ_API_KEY)

ollama_client = Client(
    host=OLLAMA_BASE_URL,
    headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"})

def call_groq_llm(
    prompt: str,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 1024
):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY manquante dans le fichier .env")

    response = groq_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=temperature
    )

    return {
        "provider": "groq",
        "model": model,
        "content": response.choices[0].message.content,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
    }


def call_ollama_llm(
    prompt: str,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    response_format: Optional[Any] = None
):
    if not OLLAMA_API_KEY:
        raise ValueError("OLLAMA_API_KEY manquante dans le fichier .env")
    
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if response_format == "json":
        kwargs["format"] = "json"

    response = ollama_client.chat(**kwargs)
    
    return {
        "provider": "ollama",
        "model": model,
        "content": response["message"]["content"],
        "usage": {}
        
    }


def call_llm(
    prompt: str,
    model: str,
    provider: str = "groq",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    response_format: Optional[Any] = None
):
    provider = provider.lower()

    if provider == "groq":
        return call_groq_llm(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

    if provider == "ollama":
        return call_ollama_llm(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format
        )

    raise ValueError("Provider invalide. Utilise 'groq' ou 'ollama'.")