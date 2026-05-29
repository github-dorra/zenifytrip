"""
Base async HTTP client for all API services.

Used by:
- internal agency APIs
- weather APIs
- Google Maps / Places APIs
- fallback providers

Rule:
API services should not crash the LangGraph workflow.
If an API fails, return None and let the service/fallback logic decide.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Union

import httpx

logger = logging.getLogger(__name__)


JsonResponse = Union[Dict[str, Any], list]


class BaseAPIClient:
    """
    Shared async HTTP client with:
    - timeout
    - retry
    - safe error handling
    - GET / POST helpers

    Important:
    This class does not contain business logic.
    Business parsing should stay inside each service.
    """

    def __init__(
        self,
        base_url: str,
        headers: Optional[dict] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_delay: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _build_url(self, endpoint: str) -> str:
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _merge_headers(self, headers: Optional[dict] = None) -> dict:
        return {
            **self.headers,
            **(headers or {}),
        }

    async def _get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> Optional[JsonResponse]:

        url = self._build_url(endpoint)

        return await self._request(
            method="GET",
            url=url,
            params=params,
            headers=headers,
        )

    async def _post(
        self,
        endpoint: str,
        data: Optional[dict] = None,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> Optional[JsonResponse]:

        url = self._build_url(endpoint)

        return await self._request(
            method="POST",
            url=url,
            params=params,
            data=data,
            json_body=json_body,
            headers=headers,
        )

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        json_body: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> Optional[JsonResponse]:

        request_headers = self._merge_headers(headers)

        request_kwargs = {
            "params": params,
            "headers": request_headers,
        }

        if data is not None:
            request_kwargs["data"] = data

        if json_body is not None:
            request_kwargs["json"] = json_body

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        **request_kwargs,
                    )

                    if response.status_code in [400, 401, 403, 404]:
                        logger.warning(
                            f"API client error | "
                            f"method={method} | "
                            f"url={url} | "
                            f"status={response.status_code} | "
                            f"body={response.text[:300]}"
                        )
                        return None

                    if response.status_code in [408, 429, 500, 502, 503, 504]:
                        logger.warning(
                            f"Retryable API error | "
                            f"method={method} | "
                            f"url={url} | "
                            f"status={response.status_code} | "
                            f"attempt={attempt + 1}/{self.max_retries + 1}"
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(self.retry_delay * (2 ** attempt))
                            continue
                        return None

                    response.raise_for_status()

                    if not response.content:
                        return None

                    return response.json()

            except httpx.TimeoutException as e:
                logger.warning(
                    f"API timeout | "
                    f"method={method} | "
                    f"url={url} | "
                    f"attempt={attempt + 1}/{self.max_retries + 1} | "
                    f"error={e}"
                )

            except httpx.RequestError as e:
                logger.warning(
                    f"API request failed | "
                    f"method={method} | "
                    f"url={url} | "
                    f"attempt={attempt + 1}/{self.max_retries + 1} | "
                    f"error={e}"
                )

            except ValueError as e:
                logger.error(
                    f"Invalid JSON response | "
                    f"method={method} | "
                    f"url={url} | "
                    f"error={e}"
                )
                return None

            except Exception as e:
                logger.exception(
                    f"Unexpected API error | "
                    f"method={method} | "
                    f"url={url} | "
                    f"error={type(e).__name__}: {e}"
                )
                return None

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2 ** attempt))

        return None
    
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass