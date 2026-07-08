"""Utilitaires texte partagés — une seule implémentation pour tout le projet."""
import unicodedata


def normalize_text(text: str) -> str:
    """Lowercase + supprime les accents (unicode NFKD) + apostrophes → espaces."""
    nfkd = unicodedata.normalize("NFKD", str(text).lower().replace("'", " ").replace("’", " "))
    return "".join(c for c in nfkd if not unicodedata.combining(c))
