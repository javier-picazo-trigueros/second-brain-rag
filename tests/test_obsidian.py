from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from secondbrain.config import Settings
from secondbrain.obsidian import obsidian_url


def test_it_builds_an_open_link_with_the_vault_and_the_path_without_extension() -> None:
    url = obsidian_url("Cerebro", "3º/Discretas/Tema 5.md")
    assert url == "obsidian://open?vault=Cerebro&file=3%C2%BA%2FDiscretas%2FTema%205"


@pytest.mark.parametrize(
    "path",
    [
        "3º/Discretas/Tema 5 Teoría de grafos [MD].md",
        "a&b/#hash/100% +más?.md",
        "carpeta con espacios/ñandú (1).md",
        "x/y/z.v2.md",
    ],
)
def test_every_special_character_survives_a_round_trip(path: str) -> None:
    query = parse_qs(urlparse(obsidian_url("Mi vault & más", path)).query)
    assert query["vault"] == ["Mi vault & más"]
    assert query["file"] == [path.removesuffix(".md")]


def test_only_a_final_md_extension_is_dropped() -> None:
    assert parse_qs(urlparse(obsidian_url("V", "a/b.md.md")).query)["file"] == ["a/b.md"]
    assert parse_qs(urlparse(obsidian_url("V", "a/b.txt")).query)["file"] == ["a/b.txt"]


def test_nothing_in_the_link_can_break_out_of_its_parameters() -> None:
    url = obsidian_url("V", "x&vault=otro/y.md")
    assert url.count("&") == 1 and "vault=otro" not in url.split("&file=")[0]


def test_the_vault_name_is_the_folder_name_unless_configured(tmp_path: Path) -> None:
    vault = tmp_path / "Cerebro"
    vault.mkdir()
    default = Settings(_env_file=None, vault_path=vault)  # type: ignore[call-arg]
    assert default.obsidian_vault_name == "Cerebro"
    named = Settings(_env_file=None, vault_path=vault, obsidian_vault="Otro nombre")  # type: ignore[call-arg]
    assert named.obsidian_vault_name == "Otro nombre"
