"""Optional OS keyring for the model key. The key is never written to a project file."""

import json
from pathlib import Path

SERVICE = "match-trajectory"
ACCOUNT = "model-api-key"


def _keyring():
    import keyring
    return keyring


def save(data_dir: Path, provider: str, model: str, base_url: str, api_key: str) -> str:
    try:
        ring = _keyring()
        ring.set_password(SERVICE, ACCOUNT, api_key)
        if ring.get_password(SERVICE, ACCOUNT) != api_key:
            return "memory"
    except Exception:  # noqa: BLE001 -- missing or locked keyring means the key stays in memory
        return "memory"
    meta = {"provider": provider, "model": model, "base_url": base_url}
    path = data_dir / "model-remember.json"
    path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    if api_key and api_key in path.read_text(encoding="utf-8"):
        path.unlink(missing_ok=True)
        return "memory"
    return "keyring"


def load(data_dir: Path) -> dict | None:
    path = data_dir / "model-remember.json"
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        secret = _keyring().get_password(SERVICE, ACCOUNT)
    except Exception:  # noqa: BLE001 -- unreadable keyring must not surface the key
        return None
    if not secret or not meta.get("provider") or not meta.get("model"):
        return None
    return {"provider": meta["provider"], "model": meta["model"], "base_url": meta.get("base_url") or "", "api_key": secret}


def clear(data_dir: Path) -> None:
    (data_dir / "model-remember.json").unlink(missing_ok=True)
    try:
        _keyring().delete_password(SERVICE, ACCOUNT)
    except Exception:  # noqa: BLE001 -- clearing a missing keyring entry is still success
        return
