from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from secondbrain.config import Settings
from secondbrain.obsidian import obsidian_link, obsidian_path_url, obsidian_url


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


# --- enlace por ruta absoluta: no depende del nombre del vault -----------------------------


def test_the_path_link_encodes_the_absolute_path_of_the_file() -> None:
    url = obsidian_path_url("C:\\Users\\yo y tú\\Cerebro/3º/Discretas/Tema 5 [MD].md")
    assert url == (
        "obsidian://open?path=C%3A%2FUsers%2Fyo%20y%20t%C3%BA%2FCerebro%2F3%C2%BA%2FDiscretas"
        "%2FTema%205%20%5BMD%5D.md"
    )


@pytest.mark.parametrize("path", ["/home/yo/vault/a&b/#x/100% +má?.md", "D:/v/x=1&vault=otro.md"])
def test_nothing_in_the_path_link_can_break_out_of_its_parameter(path: str) -> None:
    url = obsidian_path_url(path)
    assert url.count("&") == 0 and url.count("?") == 1
    assert parse_qs(urlparse(url).query)["path"] == [path]


def test_without_a_configured_name_the_link_uses_the_absolute_path(tmp_path: Path) -> None:
    vault = tmp_path / "Cerebro"
    vault.mkdir()
    s = Settings(_env_file=None, vault_path=vault)  # type: ignore[call-arg]
    url = obsidian_link(s, "3º/Discretas/Tema 5.md")
    assert url.startswith("obsidian://open?path=") and "vault=" not in url
    decoded = parse_qs(urlparse(url).query)["path"][0]
    assert decoded == (vault.resolve() / "3º/Discretas/Tema 5.md").as_posix()


def test_with_BRAIN_OBSIDIAN_VAULT_the_link_uses_the_vault_name(tmp_path: Path) -> None:
    s = Settings(_env_file=None, vault_path=tmp_path, obsidian_vault="Mi bóveda")  # type: ignore[call-arg]
    assert obsidian_link(s, "a/b.md") == "obsidian://open?vault=Mi%20b%C3%B3veda&file=a%2Fb"
