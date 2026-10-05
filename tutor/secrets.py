"""Load one provider's credential at runtime without logging secret values."""

import json
import os
from pathlib import Path


KEY_NAMES = {
    "openai": ("OPENAI_API_KEY", "openai_api_key", "openai"),
    "brave": ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "brave_api_key", "brave"),
}


def _valid_key(value) -> str:
    if not isinstance(value, str):
        raise ValueError("The selected API key must be a single text value.")
    value = value.strip().strip('"\'')
    if not value or len(value) > 2048 or any(char.isspace() for char in value):
        raise ValueError("The selected API key is empty or malformed. Check local configuration.")
    return value


def load_key(provider: str, key_path: str | Path | None = None) -> str:
    if provider not in KEY_NAMES:
        raise ValueError("Unknown credential provider.")
    if key_path is None:
        for name in KEY_NAMES[provider]:
            value = os.environ.get(name)
            if value:
                return _valid_key(value)
    path = Path(key_path) if key_path is not None else Path(__file__).resolve().parents[1] / "api_key.txt"
    try:
        if path.stat().st_size > 16_384:
            raise ValueError("The local key file is too large. Check its format.")
        text = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        raise ValueError("Cannot read the local key configuration. Check api_key.txt or use an environment variable.") from None
    names = {name.casefold() for name in KEY_NAMES[provider]}
    try:
        if text.startswith("{"):
            values = json.loads(text)
            if not isinstance(values, dict):
                raise ValueError
            matches = [value for name, value in values.items() if name.casefold() in names]
        else:
            lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
            # Backward compatibility for the original explicitly OpenAI-only file.
            if len(lines) == 1 and "=" not in lines[0] and ":" not in lines[0] and provider == "openai":
                return _valid_key(lines[0])
            matches = []
            for line in lines:
                separator = "=" if "=" in line else ":" if ":" in line else None
                if separator is None:
                    raise ValueError
                name, value = line.split(separator, 1)
                if name.strip().casefold() in names:
                    matches.append(value.strip())
        if len(matches) != 1:
            raise ValueError
        return _valid_key(matches[0])
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Configure exactly one named {provider} key in api_key.txt or its environment variable.") from None
