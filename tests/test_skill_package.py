"""Tests for the fl-studio-producer Agent Skill package and packager."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.package_skill import SKILL_DIR, package_skill, validate_skill

pytestmark = pytest.mark.skipif(
    not SKILL_DIR.exists(),
    reason="Commercial skill directory is excluded from public repo",
)


def test_skill_frontmatter_and_links() -> None:
    fields = validate_skill(SKILL_DIR)
    assert fields["name"] == "fl-studio-producer"
    assert 20 <= len(fields["description"]) <= 1024
    assert len(fields.get("compatibility", "")) <= 500


def test_skill_references_exist() -> None:
    refs_dir = SKILL_DIR / "references"
    expected = {
        "setup-and-troubleshooting.md",
        "production-workflows.md",
        "mixing-and-dsp-audit.md",
    }
    actual = {p.name for p in refs_dir.glob("*.md")}
    assert expected.issubset(actual)


def test_package_skill_creates_valid_zip(tmp_path: Path) -> None:
    zip_path = package_skill(SKILL_DIR, tmp_path)
    assert zip_path.is_file()
    assert zip_path.name == "fl-studio-producer.zip"

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert "SKILL.md" in names
        assert "assets/mcp-config.json" in names
        assert "scripts/setup.ps1" in names
        assert "references/production-workflows.md" in names
        assert "references/mixing-and-dsp-audit.md" in names
        assert "references/setup-and-troubleshooting.md" in names
