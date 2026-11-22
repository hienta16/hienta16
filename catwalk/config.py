"""Where things live, and the few settings that are not toy rules (those are in catwalk/toys/rules.py).

Edit config/catwalk.json, not this file. Two switches there decide what visitors can do:
* hub_public: this repository is public, so the website may read its JSON live and visitors can open issues.
* toys_live: the toy box accepts gifts (the README shows "Give" buttons, the website opens real issues).
Both stay false until Hien approves going public. See docs/ACTIVATION.md.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .jsonio import read_json

LOGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")  # older accounts may have double or trailing hyphens
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}/[A-Za-z0-9._-]{1,100}$")


@dataclass(frozen=True)
class Paths:
    """Every file the automation reads or writes, relative to one root (the repository checkout)."""

    root: Path

    @classmethod
    def default(cls) -> "Paths":
        env = os.environ.get("CATWALK_ROOT")
        return cls(Path(env).resolve() if env else Path(__file__).resolve().parent.parent)

    @property
    def site_config(self) -> Path:
        return self.root / "config" / "catwalk.json"

    @property
    def toy_rules(self) -> Path:
        return self.root / "config" / "toys.json"

    @property
    def github_data(self) -> Path:
        return self.root / "data" / "github.json"

    @property
    def toy_state(self) -> Path:
        return self.root / "data" / "toys.json"

    @property
    def toy_demo_state(self) -> Path:
        return self.root / "data" / "toys.demo.json"

    @property
    def generated(self) -> Path:
        return self.root / "assets" / "generated"

    @property
    def art(self) -> Path:
        return self.root / "assets" / "art"

    @property
    def fonts(self) -> Path:
        return self.root / "assets" / "fonts"

    @property
    def readme(self) -> Path:
        return self.root / "README.md"


@dataclass(frozen=True)
class SiteConfig:
    login: str
    display_name: str
    role: str
    hub_repo: str
    site_url: str
    linkedin_url: str
    hub_public: bool
    toys_live: bool

    @classmethod
    def from_dict(cls, raw: dict) -> "SiteConfig":
        if not isinstance(raw, dict):
            raise ValueError("config/catwalk.json must hold an object")
        cfg = cls(
            login=_text(raw, "login"),
            display_name=_text(raw, "display_name"),
            role=_text(raw, "role"),
            hub_repo=_text(raw, "hub_repo"),
            site_url=_text(raw, "site_url"),
            linkedin_url=_text(raw, "linkedin_url"),
            hub_public=_flag(raw, "hub_public"),
            toys_live=_flag(raw, "toys_live"),
        )
        if not LOGIN_RE.fullmatch(cfg.login):
            raise ValueError(f"login {cfg.login!r} is not a GitHub login")
        if not REPO_RE.fullmatch(cfg.hub_repo):
            raise ValueError(f"hub_repo {cfg.hub_repo!r} is not owner/name")
        for key in ("site_url", "linkedin_url"):
            if not getattr(cfg, key).startswith("https://"):
                raise ValueError(f"{key} must be an https:// link")
        if cfg.toys_live and not cfg.hub_public:
            raise ValueError("toys_live needs hub_public: visitors cannot open issues on a private repository")
        return cfg

    @property
    def issues_url(self) -> str:
        return f"https://github.com/{self.hub_repo}/issues"


def load_site_config(paths: Paths) -> SiteConfig:
    return SiteConfig.from_dict(read_json(paths.site_config))


def _text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"config value {key!r} must be a non-empty string")
    return value.strip()


def _flag(raw: dict, key: str) -> bool:
    value = raw.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"config value {key!r} must be true or false")
    return value
