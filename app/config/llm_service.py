import os
from typing import Any, Optional

from ollama import Client
from groq import Groq
from dotenv import load_dotenv
from google import genai
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# Initialisation des clients — garde contre crash si clé absente
groq_client   = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ollama_client = Client(
    host=OLLAMA_BASE_URL,
    headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"}
) if OLLAMA_API_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def call_groq_llm(
    prompt: str,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 1024
):
    if not groq_client:
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
    if not ollama_client:
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

def call_gemini_llm(
    prompt: str,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    response_format: Optional[Any] = None,
):
    if not gemini_client:
        raise ValueError("GEMINI_API_KEY manquante dans le fichier .env")

    config: dict = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if response_format == "json":
        config["response_mime_type"] = "application/json"

    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    usage = {}
    um = getattr(response, "usage_metadata", None)
    if um:
        usage = {
            "prompt_tokens":     getattr(um, "prompt_token_count",     0) or 0,
            "completion_tokens": getattr(um, "candidates_token_count", 0) or 0,
            "total_tokens":      getattr(um, "total_token_count",      0) or 0,
        }

    return {
        "provider": "gemini",
        "model": model,
        "content": response.text,
        "usage": usage,
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
        
    if provider == "gemini":
        try:
            return call_gemini_llm(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        except Exception as e:
            # Quota épuisé ou clé invalide → fallback Groq automatique
            if ("429" in str(e) or "quota" in str(e).lower()) and GROQ_API_KEY:
                import logging
                logging.getLogger("llm_service").warning(
                    f"[Gemini] quota dépassé — fallback Groq (llama-3.3-70b-versatile) | {str(e)[:80]}"
                )
                return call_groq_llm(
                    prompt=prompt,
                    model="llama-3.3-70b-versatile",
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            raise

    raise ValueError("Provider invalide. Utilise 'groq' ou 'ollama' ou 'gemini'.")