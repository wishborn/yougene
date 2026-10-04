import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "guard", ROOT / "scripts/check_no_private_data.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
FORBIDDEN = {"socket", "urllib", "http.client", "requests", "httpx", "aiohttp"}


def network_imports(source):
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
            modules += [f"{node.module}.{alias.name}" for alias in node.names]
        else:
            continue
        bad += [
            module
            for module in modules
            if any(
                module == forbidden or module.startswith(forbidden + ".")
                for forbidden in FORBIDDEN
            )
        ]
    return bad


def test_offline_packages():
    for package in ["analysis", "annotate", "importers"]:
        files = list((ROOT / "backend/yougene" / package).rglob("*.py"))
        assert files
        for path in files:
            assert not network_imports(path.read_text(encoding="utf-8")), path


@pytest.mark.parametrize(
    "source",
    [
        "import socket as s",
        "from urllib import request",
        "from http import client",
        "import http.client",
        "from httpx import Client",
        "import requests",
        "import aiohttp",
    ],
)
def test_network_guard_detects_imports(source):
    assert network_imports(source)


@pytest.mark.parametrize(
    "location,marked,allowed",
    [
        ("backend/tests/fixtures/synthetic/sample.txt", True, True),
        ("backend/tests/fixtures/synthetic/sample.txt", False, False),
        ("elsewhere/sample.txt", True, False),
    ],
)
def test_private_data_guard(tmp_path, location, marked, allowed):
    path = tmp_path / location
    path.parent.mkdir(parents=True)
    content = "# rsid\tchromosome\tposition\tgenotype\nrs123\t1\t100\tAG\n"
    if marked:
        content = guard.MARKER.decode() + "\n" + content
    path.write_text(content, encoding="utf-8")
    assert (guard.check_file(path, tmp_path) is None) == allowed


def test_guard_cli_on_staged_files(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    fixture = tmp_path / "backend/tests/fixtures/synthetic/demo.txt"
    fixture.parent.mkdir(parents=True)
    content = "i7000001\t1\t1000\tDI\n"
    fixture.write_text(guard.MARKER.decode() + "\n" + content)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    command = [sys.executable, str(ROOT / "scripts/check_no_private_data.py")]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0 and "passed" in result.stdout
    fixture.write_text(content)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1 and "missing exact marker" in result.stdout


def test_guard_scans_beyond_old_limit(tmp_path):
    path = tmp_path / "large.txt"
    path.write_bytes(b"# comment\n" * 510000 + b"i7000001\t1\t1000\tAG\n")
    assert guard.check_file(path, tmp_path) == "contains raw genotype rows"
