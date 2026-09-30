"""Configuration agrees everywhere: every setting that code, scripts, Compose, Bicep, or the Kubernetes
manifests read is listed in .env.example, and nothing listed there goes unread."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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


def k8s_docs() -> list[dict[str, Any]]:
    return [doc for path in sorted((DEMO / "k8s").glob("*.yaml"))
            for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")) if doc]


def test_aks_pods_opt_out_of_service_link_variables() -> None:
    # Unless a pod opts out, Kubernetes gives it <SERVICE>_PORT=tcp://<ip>:<port> and similar variables for every
    # Service in its namespace. The web and insights Services would override the WEB_PORT and INSIGHTS_PORT
    # settings, and every service would fail at startup.
    docs = k8s_docs()
    services = {doc["metadata"]["name"].upper().replace("-", "_") for doc in docs if doc["kind"] == "Service"}
    injected = {f"{svc}_{suffix}" for svc in services for suffix in ("PORT", "SERVICE_HOST", "SERVICE_PORT")}
    collisions = sorted(injected & {name.upper() for name in Settings.model_fields})
    pods = [doc for doc in docs if doc["kind"] in ("Deployment", "Job")]
    assert {doc["metadata"]["name"] for doc in pods} == {"web", "insights", "ingest"}
    for doc in pods:
        assert doc["spec"]["template"]["spec"].get("enableServiceLinks") is False, \
            f"{doc['metadata']['name']} must set enableServiceLinks: false, or Services override {collisions}"


def test_aks_gateway_keeps_the_callers_address() -> None:
    # web's rate limits key on the caller's address. With externalTrafficPolicy "Cluster", the gateway would see node
    # addresses, and a caller spread across nodes would get several allowances.
    docs = {(doc["kind"], doc["metadata"]["name"]): doc for doc in k8s_docs()}
    ref = docs[("Gateway", "football-web")]["spec"]["infrastructure"]["parametersRef"]
    assert (ref["group"], ref["kind"]) == ("", "ConfigMap")
    service = yaml.safe_load(docs[("ConfigMap", ref["name"])]["data"]["service"])
    assert service["spec"]["externalTrafficPolicy"] == "Local"
    # The add-on's port 80 health-probe annotations suit "Cluster" only; the overlay must unset them.
    probes = ("port", "protocol", "request-path")
    assert service["metadata"]["annotations"] == {
        f"service.beta.kubernetes.io/port_80_health-probe_{name}": None for name in probes}

def test_image_changes_also_update_the_badge_digest() -> None:
    # The badge reports IMAGE_DIGEST. An image change that leaves it behind makes the badge name the wrong image.
    for name in ("azure.ps1", "azure.sh"):
        text = (DEMO / "scripts" / name).read_text(encoding="utf-8")
        assert "set image" not in text, f"{name}: change images with the helper that also sets IMAGE_DIGEST"
        updates = [line for line in text.splitlines() if "containerapp update" in line and "--image" in line]
        assert updates, f"{name}: no image updates found; update this test"
        for line in updates:
            assert "IMAGE_DIGEST=" in line, f"{name}: {line.strip()}"

def test_powershell_passes_az_queries_that_survive_cmd() -> None:
    # az is a batch file on Windows. PowerShell passes an argument without spaces unquoted, and cmd.exe then
    # mangles ( ) @ & | < > ^ and double quotes in it. Filter or count JSON in PowerShell instead.
    text = (DEMO / "scripts" / "azure.ps1").read_text(encoding="utf-8")
    risky = [q for q in re.findall(r"--query\s+'([^']*)'", text) if " " not in q and re.search(r'[()@&|<>^"]', q)]
    assert not risky, f"queries cmd.exe would mangle: {risky}"

def test_local_compose_is_live_only_with_the_token_overlay() -> None:
    # A container can't use the host's sign-in, so plain `demo up` must report the narrative as off even when .env
    # holds a Foundry endpoint; only the -LiveModel overlay, which mounts the token file, turns it on.
    base = yaml.safe_load((DEMO / "docker" / "compose.yaml").read_text(encoding="utf-8"))
    live = yaml.safe_load((DEMO / "docker" / "compose.live.yaml").read_text(encoding="utf-8"))
    assert base["services"]["insights"]["environment"]["AI_NARRATIVE_MODE"] == "${AI_NARRATIVE_MODE:-off}"
    assert "AZURE_TOKEN_FILE" not in base["services"]["insights"]["environment"]
    overlay = live["services"]["insights"]["environment"]
    assert overlay["AI_NARRATIVE_MODE"] == "live" and overlay["AZURE_TOKEN_FILE"]
