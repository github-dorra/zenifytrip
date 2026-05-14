"""
Classe abstraite BaseNode — socle obligatoire pour tous les nœuds du projet.
Chaque nœud doit hériter de BaseNode et implémenter la méthode run(state: dict) -> dict.

ce que herite chaque node : 
- logging
- erreurs
- métriques
- cache optionnel
- appel LLM centralisé
- validation Pydantic optionnelle
- parsing JSON robuste
- score de confiance 

"""
# next amélioration : 
#gestion de cache integre pour éviter appel d'API en cas de requetes similaires
#une formule mathematique pour calculer la degre de certitude chez un agent


# app/nodes/core/base_node.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type
import hashlib
import json
import logging
import re
import time

from pydantic import BaseModel, ValidationError

from app.services.llm_service import call_llm
from app.services.cache_service import cache


def build_logger(name: str):
    logger = logging.getLogger(f"nodes.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


# node description 
@dataclass
class NodeConfig:
    name: str
    node_type: str = "technical"  # technical | llm_agent | tool_node | conversation
    provider: str = "groq"  # groq | ollama
    model: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 2048
    response_format: Optional[Any] = None  #model ollmama avec output json 
    cache_enabled: bool = False
    cache_ttl_seconds: int = 3000
    
    
class BaseNode(ABC):
    
    input_schema: Optional[Type[BaseModel]] = None
    output_schema: Optional[Type[BaseModel]] = None

    def __init__(self, config: NodeConfig):
        self.config = config
        self.name = config.name
        self.node_type = config.node_type
        self.provider = config.provider
        self.model = config.model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
        self.cache_enabled = config.cache_enabled
        self.cache_ttl_seconds = config.cache_ttl_seconds

        self.logger = build_logger(self.name)

        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
    

    #  méthode appelée par LangGraph
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        
        # reset a chaque appel 
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

        try:
            self.logger.info("START")

            self._validate_input_if_needed(state)

            result = self.run(state)

            result = self._validate_output_if_needed(result)

            duration_ms = int((time.time() - start_time) * 1000)

            metrics_patch = self._build_metrics_patch(
                status="success",
                duration_ms=duration_ms,
            )

            self.logger.info(f"SUCCESS ({duration_ms}ms)")

            return {
                
                **result,
            }

        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)

            self.logger.error(f"ERROR: {type(exc).__name__}: {exc}")

            return self.fallback(
                state=state,
                error=str(exc),
                error_type=type(exc).__name__,
                duration_ms=duration_ms,
            )
            
    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    
    
    def call_llm( self,  prompt: str,  cache_key_extra: Optional[str] = None, ) -> Dict[str, Any]:
        
        if not self.model:
            raise ValueError(f"Node {self.name} has no model configured.")

        cache_key = self._build_cache_key(prompt, cache_key_extra)

        if self.cache_enabled:
            cached = cache.get(cache_key)
            if cached:
                self.logger.info("LLM CACHE HIT")
                return {
                    **cached,
                    "cache_hit": True,
                }

        # CALL LLM (Groq ou Ollama via service central)
        response = call_llm(
            prompt=prompt,
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format = self.config.response_format if self.config.response_format else None,
        )


        content = response.get("content", "")

        usage = response.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
            
            
        result = {
            "content": content,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "cache_hit": False,
        }

        if self.cache_enabled:
            cache.set(
                key=cache_key,
                value=result,
                ttl_seconds=self.cache_ttl_seconds,
            )
        return result


    def parse_json(self, text: str) -> Dict[str, Any]:
        if not text:
            raise ValueError("Empty LLM response")

        # remove markdown fences
        text = text.replace("```json", "").replace("```", "").strip()

        # extract first valid JSON block
        match = re.search(r"\{.*\}", text, re.DOTALL)

        if not match:
            raise ValueError(f"No JSON found in response: {text}")

        json_str = match.group(0)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format: {json_str}")


    def _validate_input_if_needed(self, state: Dict[str, Any]) -> None:
        if self.input_schema is None:
            return

        self.input_schema(**state)

    def _validate_output_if_needed(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if self.output_schema is None:
            return result

        try:
            validated = self.output_schema(**result)
            return validated.model_dump()
        except ValidationError as exc:
            raise ValueError(
                f"Invalid output format for node {self.name}: {exc}"
            )


    def calculate_confidence(
        self,
        model_confidence: float = 0.0,
        required_fields_score: float = 1.0,
        schema_validation_score: float = 1.0,
        source_reliability_score: float = 1.0,
    ) -> float:
        """
        Formule simple de confiance.

        model_confidence:
            score retourné par le LLM si disponible.

        required_fields_score:
            pourcentage des champs obligatoires correctement remplis.

        schema_validation_score:
            1 si Pydantic valide, 0 sinon.

        source_reliability_score:
            score de confiance de la source/API.
        """

        confidence = (
            0.40 * model_confidence
            + 0.25 * required_fields_score
            + 0.20 * schema_validation_score
            + 0.15 * source_reliability_score
        )

        return round(max(0.0, min(confidence, 1.0)), 3)

    def _build_metrics_patch(
        self,
        status: str,
        duration_ms: int,
    ) -> Dict[str, Any]:
        return {
            "node_metrics": [
                {
                    "node": self.name,
                    "node_type": self.node_type,
                    "status": status,
                    "duration_ms": duration_ms,
                    "model": self.model,
                    "provider": self.provider,
                    "prompt_tokens": self.prompt_tokens,
                    "completion_tokens": self.completion_tokens,
                    "total_tokens": self.total_tokens,
                }
            ]
        }


    def _build_cache_key(
        self,
        prompt: str,
        cache_key_extra: Optional[str] = None,
    ) -> str:
        raw = {
            "node": self.name,
            "model": self.model,
            "temperature": self.temperature,
            "prompt": prompt,
            "provider": self.provider,
            "extra": cache_key_extra,
        }

        raw_text = json.dumps(raw, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        return f"node_cache:{self.name}:{digest}"

    
    
    # Fallback
    def fallback(
        self,
        state: Dict[str, Any],
        error: str,
        error_type: str,
        duration_ms: int,
    ) -> Dict[str, Any]:
        previous_errors = state.get("errors", [])

        return { 
            **state, 
            "errors": previous_errors + [
                {
                    "node": self.name,
                    "error_type": error_type,
                    "message": error,
                    "duration_ms": duration_ms,
                }
            ],
            "next_action": "error",
            "final_answer": "Une erreur est survenue. Veuillez réessayer.",
            "node_metrics": [
                {
                    "node": self.name,
                    "node_type": self.node_type,
                    "status": "error",
                    "duration_ms": duration_ms,
                    "provider": self.provider,
                    "model": self.model,
                }
            ],
        }