"""Global settings: one normalized model over the config entry's options.

The Settings tab edits this model. It is stored in the config entry's
options, but older installs stored a different shape (``persons`` with one
``notify`` + optional ``media_player`` each, plus a separate
``mobile_targets`` list). :func:`normalize` reads either shape, so the engine
works before and after the v3 migration; :func:`to_options` writes only the
new shape.

Model::

    people:          [{person: person.alex, phones: [notify.mobile_app_x, ...]}]
    other_phones:    [notify.mobile_app_tablet]   # not tied to a person
    tts_engine:      "" (automatic) | tts.<engine>
    tts_service:     tts.speak
    default_media_players: [media_player.kitchen]
    quiet_hours_enabled: true
    quiet_hours_start / quiet_hours_end / digest_time: "HH:MM:SS"
    debounce_ms:     300
    wall_sheets / wall_pages: names the ESP32 wall panels accept

Pure: no Home Assistant imports, so it is unit-testable.
"""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_DEBOUNCE_MS,
    CONF_DIGEST_TIME,
    CONF_MOBILE_TARGETS,
    CONF_PERSONS,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_TTS_DEFAULT_TARGETS,
    CONF_TTS_ENGINE,
    CONF_TTS_SERVICE,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_DIGEST_TIME,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_TTS_SERVICE,
)

CONF_PEOPLE = "people"
CONF_OTHER_PHONES = "other_phones"
CONF_DEFAULT_MEDIA_PLAYERS = "default_media_players"
CONF_QUIET_HOURS_ENABLED = "quiet_hours_enabled"
CONF_WALL_SHEETS = "wall_sheets"
CONF_WALL_PAGES = "wall_pages"

# Generic defaults; each install lists the names its own panels accept.
DEFAULT_WALL_SHEETS = ["notifications", "outage", "weather", "alarm"]
DEFAULT_WALL_PAGES = ["home", "security", "climate", "energy", "settings"]

# Keys only the legacy (pre-v3) shape used.
LEGACY_KEYS = (CONF_PERSONS, CONF_MOBILE_TARGETS, CONF_TTS_DEFAULT_TARGETS)


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    out: list[str] = []
    for item in value:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return out


def _time(value: Any, default: str) -> str:
    """Normalize "HH:MM" / "HH:MM:SS" to "HH:MM:SS" (bad input -> default)."""
    try:
        parts = [int(p) for p in str(value).split(":")]
    except (TypeError, ValueError):
        return default
    if not 2 <= len(parts) <= 3:
        return default
    while len(parts) < 3:
        parts.append(0)
    h, m, s = parts
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        return default
    return f"{h:02d}:{m:02d}:{s:02d}"


def _people_from_legacy(persons: list[dict]) -> list[dict]:
    """Merge legacy one-phone mappings into people with several phones.

    The per-person ``media_player`` is dropped: announcements go to a rule's
    speakers or the default speakers.
    """
    people: list[dict] = []
    by_person: dict[str, dict] = {}
    for mapping in persons or []:
        if not isinstance(mapping, dict):
            continue
        person = str(mapping.get("person") or "").strip()
        notify = str(mapping.get("notify") or "").strip()
        if not person:
            continue
        entry = by_person.get(person)
        if entry is None:
            entry = {"person": person, "phones": []}
            by_person[person] = entry
            people.append(entry)
        if notify and notify not in entry["phones"]:
            entry["phones"].append(notify)
    return people


def normalize(options: dict[str, Any] | None) -> dict[str, Any]:
    """The settings model from stored options (new or legacy shape)."""
    opts = dict(options or {})
    if CONF_PEOPLE in opts or CONF_OTHER_PHONES in opts:
        people = []
        for p in opts.get(CONF_PEOPLE) or []:
            if isinstance(p, dict) and p.get("person"):
                people.append({"person": str(p["person"]), "phones": _str_list(p.get("phones"))})
        other = _str_list(opts.get(CONF_OTHER_PHONES))
    else:
        people = _people_from_legacy(opts.get(CONF_PERSONS) or [])
        mapped = {ph for p in people for ph in p["phones"]}
        other = [s for s in _str_list(opts.get(CONF_MOBILE_TARGETS)) if s not in mapped]
    # A phone belongs to one place only: a person wins over "other phones".
    assigned = {ph for p in people for ph in p["phones"]}
    other = [s for s in other if s not in assigned]

    speakers = opts.get(CONF_DEFAULT_MEDIA_PLAYERS)
    if speakers is None:
        speakers = opts.get(CONF_TTS_DEFAULT_TARGETS)

    try:
        debounce = int(opts.get(CONF_DEBOUNCE_MS, DEFAULT_DEBOUNCE_MS))
    except (TypeError, ValueError):
        debounce = DEFAULT_DEBOUNCE_MS
    debounce = max(0, min(debounce, 5000))

    return {
        CONF_PEOPLE: people,
        CONF_OTHER_PHONES: other,
        CONF_TTS_ENGINE: str(opts.get(CONF_TTS_ENGINE) or ""),
        CONF_TTS_SERVICE: str(opts.get(CONF_TTS_SERVICE) or DEFAULT_TTS_SERVICE),
        CONF_DEFAULT_MEDIA_PLAYERS: _str_list(speakers),
        CONF_QUIET_HOURS_ENABLED: bool(opts.get(CONF_QUIET_HOURS_ENABLED, True)),
        CONF_QUIET_HOURS_START: _time(opts.get(CONF_QUIET_HOURS_START), DEFAULT_QUIET_HOURS_START),
        CONF_QUIET_HOURS_END: _time(opts.get(CONF_QUIET_HOURS_END), DEFAULT_QUIET_HOURS_END),
        CONF_DIGEST_TIME: _time(opts.get(CONF_DIGEST_TIME), DEFAULT_DIGEST_TIME),
        CONF_DEBOUNCE_MS: debounce,
        CONF_WALL_SHEETS: _str_list(opts.get(CONF_WALL_SHEETS)) or list(DEFAULT_WALL_SHEETS),
        CONF_WALL_PAGES: _str_list(opts.get(CONF_WALL_PAGES)) or list(DEFAULT_WALL_PAGES),
    }


def to_options(settings: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Options to store for a settings model (new shape only).

    Unknown keys already in ``previous`` are kept; the legacy keys are
    dropped because the new ones replace them.
    """
    out = {k: v for k, v in (previous or {}).items() if k not in LEGACY_KEYS}
    out.update(normalize(settings))
    return out


def all_phones(settings: dict[str, Any]) -> list[str]:
    """Every phone: people's phones first, then the other phones."""
    out: list[str] = []
    for p in settings.get(CONF_PEOPLE) or []:
        for ph in p.get("phones") or []:
            if ph not in out:
                out.append(ph)
    for ph in settings.get(CONF_OTHER_PHONES) or []:
        if ph not in out:
            out.append(ph)
    return out
