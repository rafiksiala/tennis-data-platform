"""Coherence de render.yaml avec le depot (pas de validation Render: elle exige l'API Render)."""

import shlex
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVICES = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))["services"]
PYTHON_SERVICES = [s for s in SERVICES if s.get("runtime") == "python"]


def test_service_names_are_unique():
    names = [s["name"] for s in SERVICES]
    assert len(names) == len(set(names))


def test_no_database_is_declared():
    # un Blueprint pourrait creer une 2e base a cote de la base existante
    assert "databases" not in yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("service", PYTHON_SERVICES, ids=lambda s: s["name"])
def test_python_services_install_the_package(service):
    assert service["buildCommand"] == "pip install -r requirements.txt"
    assert "-e ." in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("service", [s for s in SERVICES if s["type"] == "cron"], ids=lambda s: s["name"])
def test_cron_jobs_run_existing_scripts(service):
    command = shlex.split(service["startCommand"])
    assert command[0] == "python"
    assert (ROOT / command[1]).is_file()


@pytest.mark.parametrize("service", PYTHON_SERVICES, ids=lambda s: s["name"])
def test_secrets_are_never_in_the_file(service):
    for var in service["envVars"]:
        if var["key"] in ("DATABASE_URL", "API_TENNIS_KEY"):
            assert var == {"key": var["key"], "sync": False}


def test_static_site_serves_the_spa_for_deep_links():
    (site,) = [s for s in SERVICES if s.get("runtime") == "static"]
    assert (ROOT / site["rootDir"] / "package.json").is_file()
    assert {"type": "rewrite", "source": "/*", "destination": "/index.html"} in site["routes"]
