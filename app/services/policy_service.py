"""Policy business logic: load and list YAML policy files."""

from pathlib import Path

import yaml

from app.config import settings
from app.schemas.policy import PolicyRead


def _load_policy(path: Path) -> dict:
    """Load and parse a YAML policy file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_policies() -> list[PolicyRead]:
    """Return all YAML policy files as PolicyRead objects."""
    policy_dir = settings.policy_dir
    if not policy_dir.is_dir():
        return []
    policies: list[PolicyRead] = []
    for path in sorted(policy_dir.glob("*.yaml")):
        policies.append(PolicyRead(name=path.stem, content=_load_policy(path)))
    return policies


def get_policy(policy_name: str) -> PolicyRead | None:
    """Return PolicyRead or None if not found."""
    path = settings.policy_dir / f"{policy_name}.yaml"
    if not path.is_file():
        return None
    return PolicyRead(name=policy_name, content=_load_policy(path))
