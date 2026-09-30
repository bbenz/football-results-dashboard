"""Keyless credentials for every environment.

- AKS: workload identity (the webhook injects AZURE_CLIENT_ID and a federated token file).
- ACA: the user-assigned managed identity named by AZURE_CLIENT_ID.
- Host: the operator's own Azure CLI sign-in.
- Docker Compose with live models: a short-lived token file written by
  demo/scripts/compose-up.ps1 -LiveModel, because containers cannot reuse the
  host's sign-in. The file holds access tokens per scope, refreshed by the
  script, and nothing ever prints its contents.

There is deliberately no API-key or connection-secret path anywhere.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from azure.core.credentials import AccessToken, AccessTokenInfo, TokenCredential
from azure.core.exceptions import ClientAuthenticationError

from .config import get_settings

FOUNDRY_SCOPE = "https://ai.azure.com/.default"
MONITOR_SCOPE = "https://monitor.azure.com/.default"


class FileTokenCredential:
    """Reads access tokens that a host-side helper keeps fresh in a JSON file."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def _load(self, scope: str) -> tuple[str, int]:
        try:
            tokens: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ClientAuthenticationError(f"token file unreadable at {self.path}") from exc
        entry = tokens.get(scope)
        if not entry:
            raise ClientAuthenticationError(f"token file has no token for scope {scope}")
        expires_on = int(entry["expires_on"])
        if expires_on <= time.time() + 60:
            raise ClientAuthenticationError(
                "token file is expired; run demo/scripts/compose-up.ps1 -LiveModel to refresh it"
            )
        return str(entry["token"]), expires_on

    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        token, expires_on = self._load(scopes[0])
        return AccessToken(token, expires_on)

    def get_token_info(self, *scopes: str, options: Any = None) -> AccessTokenInfo:
        token, expires_on = self._load(scopes[0])
        return AccessTokenInfo(token, expires_on)

    def close(self) -> None:
        return None


def azure_credential() -> TokenCredential:
    settings = get_settings()
    if settings.azure_token_file:
        return FileTokenCredential(settings.azure_token_file)
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(
        managed_identity_client_id=settings.azure_client_id or None,
        exclude_interactive_browser_credential=True,
    )
