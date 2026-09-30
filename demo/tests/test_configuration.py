"""Configuration agrees everywhere: every setting that code, scripts, Compose, Bicep, or the Kubernetes
manifests read is listed in .env.example, and nothing listed there goes unread."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from conftest import REPO_ROOT
from football_insights.config import Settings

DEMO = REPO_ROOT / "demo"


def example_names() -> set[str]:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))


def read(paths: list[Path]) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in paths if p.is_file())


def test_every_code_setting_is_documented() -> None:
    documented = example_names()
    missing = {name.upper() for name in Settings.model_fields} - documented
    assert not missing, f"settings the code reads but .env.example omits: {sorted(missing)}"


def test_every_infrastructure_variable_is_documented() -> None:
    documented = example_names()
    bicep = read(sorted((DEMO / "infra").glob("*.bicepparam")))
    manifests = read(sorted((DEMO / "k8s").glob("*.yaml")))
    compose = read(sorted((DEMO / "docker").glob("compose*.yaml")))
    used = set(re.findall(r"readEnvironmentVariable\('([A-Z0-9_]+)'", bicep))
    used |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", manifests + compose))
    scripts = read(sorted((DEMO / "scripts").glob("*.ps1")) + sorted((DEMO / "scripts").glob("*.sh")))
    used |= set(re.findall(r"(?:Get-RequiredEnv|Get-EnvOrDefault|require_env|env_or_default)\s+'?\"?([A-Z][A-Z0-9_]+)",
                           scripts))
    missing = used - documented
    assert not missing, f"variables read by infrastructure or scripts but missing from .env.example: {sorted(missing)}"


def test_nothing_documented_is_unread() -> None:
    corpus = read(sorted((DEMO / "src").rglob("*.py")) + sorted((DEMO / "scripts").glob("*.*"))
                  + sorted((DEMO / "infra").glob("*.*")) + sorted((DEMO / "k8s").glob("*.yaml"))
                  + sorted((DEMO / "docker").glob("compose*.yaml")))
    code_settings = {name.upper() for name in Settings.model_fields}
    unread = [name for name in sorted(example_names())
              if name not in code_settings and not re.search(rf"\b{name}\b", corpus)]
    assert not unread, f".env.example lists settings nothing reads: {unread}"


def aks_env() -> dict[str, set[str]]:
    env: dict[str, set[str]] = {}
    for path in sorted((DEMO / "k8s").glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if doc and doc["kind"] in ("Deployment", "Job"):
                for container in doc["spec"]["template"]["spec"]["containers"]:
                    env[container["name"]] = {item["name"] for item in container.get("env", [])}
    return env


def aca_env() -> dict[str, set[str]]:
    text = (DEMO / "infra" / "aca.bicep").read_text(encoding="utf-8")
    names = re.compile(r"name: '([A-Z][A-Z0-9_]*)'")
    shared = {m.group(1): set(names.findall(m.group(2)))
              for m in re.finditer(r"^var (\w+Env) = \[(.*?)^\]", text, flags=re.MULTILINE | re.DOTALL)}
    env: dict[str, set[str]] = {}
    for m in re.finditer(r"name: '(web|insights|ingest)'\n(?:(?!name: ').)*?env: concat\(([^\[]*)\[(.*?)\]\)",
                         text, flags=re.DOTALL):
        env[m.group(1)] = set(names.findall(m.group(3)))
        for var in re.findall(r"\w+Env", m.group(2)):
            env[m.group(1)] |= shared[var]
    return env


def test_both_platforms_give_each_service_the_same_settings() -> None:
    aks, aca = aks_env(), aca_env()
    assert set(aks) == set(aca) == {"web", "insights", "ingest"}
    for service in aks:
        assert aks[service] == aca[service], f"{service}: AKS-only {aks[service] - aca[service]}, " \
                                             f"ACA-only {aca[service] - aks[service]}"
    # web reaches data and the model only through insights, so it gets neither kind of setting.
    leaked = {n for n in aks["web"] if n.startswith(("CURATED_", "STORAGE_", "FOUNDRY_", "AI_", "RAW_"))}
    assert not leaked, f"web is given settings it never reads: {sorted(leaked)}"
