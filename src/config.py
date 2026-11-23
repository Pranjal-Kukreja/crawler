"""Load config.yaml and merge in config.local.yaml (the private bits, like your email)."""
from pathlib import Path

import yaml


def load_config(path="config.yaml", local_path="config.local.yaml"):
    cfg = yaml.safe_load(Path(path).read_text())
    local = Path(local_path)
    if local.exists():
        cfg.update(yaml.safe_load(local.read_text()) or {})
    if not cfg.get("contact_email"):
        raise ValueError("contact_email missing: put it in config.local.yaml")
    # The user-agent tells the site who we are and how to reach us.
    cfg["user_agent"] = f"{cfg['user_agent_prefix']} (contact: {cfg['contact_email']})"
    return cfg
