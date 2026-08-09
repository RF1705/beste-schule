"""Tests for release metadata and translation structure."""

import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "path",
    (
        ROOT / "custom_components/beste_schule/strings.json",
        ROOT / "custom_components/beste_schule/translations/de.json",
    ),
)
def test_reauth_translation_is_in_config_flow(path: Path) -> None:
    """Reauthentication text must live under the config-flow step namespace."""
    data = json.loads(path.read_text(encoding="utf-8"))

    assert "reauth_confirm" in data["config"]["step"]
    assert "reauth_confirm" not in data.get("options", {}).get("step", {})


def test_manifest_uses_semantic_version() -> None:
    """HACS releases should expose a complete semantic version."""
    manifest = json.loads(
        (ROOT / "custom_components/beste_schule/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
