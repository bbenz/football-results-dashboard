"""Where this process runs, as told by its deployment configuration.

The badge must be truthful, so nothing here guesses: the platform, region, and
image digest come from environment variables that Docker Compose, the AKS
manifests, and the ACA definitions set. A value that was not injected is shown
as missing rather than invented.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class RuntimeInfo:
    platform: str
    region: str
    image_digest: str

    @property
    def short_digest(self) -> str:
        digest = self.image_digest.split(":", 1)[-1]
        return digest[:12] if digest else "local build"

    def as_dict(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "region": self.region or "n/a",
            "image_digest": self.image_digest or "",
            "short_digest": self.short_digest,
        }


def describe(settings: Settings) -> RuntimeInfo:
    return RuntimeInfo(
        platform=settings.platform_name or "Local",
        region=settings.platform_region,
        image_digest=settings.image_digest,
    )
