"""The model client: the Responses API, called through the Foundry project, keyless.

AIProjectClient.get_openai_client() returns an OpenAI client bound to the
project endpoint and authenticated with a Microsoft Entra credential (workload
identity on AKS, managed identity on ACA, the operator's sign-in on a laptop, or
a short-lived token file under Docker Compose). There is no API-key path.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..identity import azure_credential


def openai_client(settings: Settings) -> Any:
    from azure.ai.projects import AIProjectClient

    project = AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=azure_credential())
    client = project.get_openai_client()
    return client.with_options(timeout=settings.ai_timeout_seconds, max_retries=2)
