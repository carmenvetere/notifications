"""YAML-managed rules: inline (`rules:`) and file (`rules_file:`) modes.

Two ways to keep rules in YAML (#47):

* ``notification_center: rules: [...]`` (typically an ``!include``) — the
  rules are part of configuration.yaml, so Home Assistant owns the file and
  the panel is **read-only**.
* ``notification_center: rules_file: notification_center/rules.yaml`` — the
  integration owns that one file: it reads it at startup, re-reads it when it
  changes on disk (git pull, an editor, Claude Code…) or on
  ``notification_center.reload``, and the **panel edits it in place**, so the
  same rules can be managed from the UI and from the file.

In both modes nothing is stored in config subentries.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import slugify
from homeassistant.util.yaml import dump as yaml_dump
from homeassistant.util.yaml import load_yaml

from .const import (
    CONF_RULES,
    CONF_RULES_FILE,
    DATA_YAML_CONF,
    DATA_YAML_MTIME,
    DATA_YAML_RULES,
    DATA_YAML_RULES_FILE,
    DATA_YAML_SOURCE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

FILE_HEADER = (
    "# Notification Center rules — the single source of truth for your rules.\n"
    "# Edit this file (and run notification_center.reload, or just wait a few\n"
    "# seconds: changes are picked up automatically) OR edit in the Notifications\n"
    "# panel, which saves back here. Saving from the panel rewrites the file, so\n"
    "# keep notes in git commit messages rather than as comments here.\n"
)


def normalize_rules(value: Any) -> list[dict]:
    """Coerce a configured rules value into a bare list of rule dicts.

    Tolerates the two common file-shape mistakes instead of loading junk:
    - the file wraps the list in a ``rules:`` key, and
    - a pasted ``export_rules`` response (``count`` / ``rules`` / ``yaml``).
    """
    if isinstance(value, dict):
        value = value.get(CONF_RULES) or []
    if (
        isinstance(value, list)
        and len(value) == 1
        and isinstance(value[0], dict)
        and "name" not in value[0]
        and isinstance(value[0].get(CONF_RULES), list)
    ):
        value = value[0][CONF_RULES]
    if not isinstance(value, list):
        return []
    return [r for r in value if isinstance(r, dict)]


def rule_id_for(rule: dict[str, Any]) -> str:
    """The stable id the engine/panel use for a YAML rule: ``yaml_<tag>``."""
    tag = rule.get("dedup_tag") or slugify(str(rule.get("name") or ""))
    return f"yaml_{tag}"


def resolve_rules_file(hass: HomeAssistant, rel_path: str) -> str:
    """Absolute path of the rules file; must live inside the config dir."""
    path = os.path.realpath(hass.config.path(rel_path))
    root = os.path.realpath(hass.config.config_dir) + os.sep
    if not path.startswith(root):
        raise HomeAssistantError(
            f"rules_file must be inside the configuration directory: {rel_path}"
        )
    return path


def _read_file(path: str) -> tuple[list[dict], float | None]:
    """Read + normalize the rules file (executor). Missing file -> ([], None)."""
    if not os.path.exists(path):
        return [], None
    data = load_yaml(path)  # raises HomeAssistantError on bad YAML
    return normalize_rules(data), os.stat(path).st_mtime


def _write_file(path: str, rules: list[dict]) -> float:
    """Atomically write the rules file (executor); returns its new mtime."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = yaml_dump([dict(r) for r in rules]) if rules else "[]\n"
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".rules-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(FILE_HEADER + body)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return os.stat(path).st_mtime


def _stat_mtime(path: str) -> float | None:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


@callback
def yaml_source(hass: HomeAssistant) -> str | None:
    """'inline', 'file' or None (rules live in config subentries)."""
    return hass.data.get(DATA_YAML_SOURCE)


@callback
def rules_file_rel(hass: HomeAssistant) -> str | None:
    """The configured rules_file (relative, for display) or None."""
    conf = hass.data.get(DATA_YAML_CONF) or {}
    return conf.get(CONF_RULES_FILE) or None


async def async_load_yaml_rules(hass: HomeAssistant, conf: dict[str, Any] | None) -> None:
    """Load rules per the `notification_center:` config block into hass.data.

    File mode: a missing file is an empty rule set (the panel's first save
    creates it); a file that fails to parse keeps the last-good rules and
    raises a repair issue instead of wiping everything.
    """
    conf = dict(conf or {})
    hass.data[DATA_YAML_CONF] = conf
    rel = conf.get(CONF_RULES_FILE)
    if rel:
        path = resolve_rules_file(hass, rel)
        hass.data[DATA_YAML_SOURCE] = "file"
        hass.data[DATA_YAML_RULES_FILE] = path
        try:
            rules, mtime = await hass.async_add_executor_job(_read_file, path)
        except HomeAssistantError as err:
            _LOGGER.error("notification_center: can't read %s: %s", rel, err)
            ir.async_create_issue(
                hass,
                DOMAIN,
                "yaml_rules_file_error",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="yaml_rules_file_error",
                translation_placeholders={"file": rel, "error": str(err)},
            )
            hass.data.setdefault(DATA_YAML_RULES, [])  # keep last-good
            hass.data[DATA_YAML_MTIME] = await hass.async_add_executor_job(_stat_mtime, path)
            return
        ir.async_delete_issue(hass, DOMAIN, "yaml_rules_file_error")
        hass.data[DATA_YAML_RULES] = rules
        hass.data[DATA_YAML_MTIME] = mtime
        return
    hass.data[DATA_YAML_RULES_FILE] = None
    hass.data[DATA_YAML_MTIME] = None
    if conf.get(CONF_RULES):
        hass.data[DATA_YAML_SOURCE] = "inline"
        hass.data[DATA_YAML_RULES] = normalize_rules(conf.get(CONF_RULES))
        return
    hass.data[DATA_YAML_SOURCE] = None
    hass.data[DATA_YAML_RULES] = []


async def async_save_yaml_rules(hass: HomeAssistant, rules: list[dict]) -> None:
    """File mode: write the rules to the file and make them live."""
    path = hass.data.get(DATA_YAML_RULES_FILE)
    if not path:
        raise HomeAssistantError("Rules are not stored in a file (no rules_file configured)")
    mtime = await hass.async_add_executor_job(_write_file, path, rules)
    hass.data[DATA_YAML_RULES] = [dict(r) for r in rules]
    hass.data[DATA_YAML_MTIME] = mtime
    await _async_reload_engines(hass)


async def async_check_rules_file(hass: HomeAssistant) -> bool:
    """File mode: if the file changed on disk since we last loaded/saved it,
    re-read it and reload the engine. Returns True when a reload happened."""
    path = hass.data.get(DATA_YAML_RULES_FILE)
    if not path:
        return False
    mtime = await hass.async_add_executor_job(_stat_mtime, path)
    if mtime == hass.data.get(DATA_YAML_MTIME):
        return False
    _LOGGER.info("notification_center: rules file changed on disk — reloading")
    await async_load_yaml_rules(hass, hass.data.get(DATA_YAML_CONF))
    await _async_reload_engines(hass)
    return True


async def _async_reload_engines(hass: HomeAssistant) -> None:
    for engine in list(hass.data.get(DOMAIN, {}).values()):
        await engine.async_reload()
