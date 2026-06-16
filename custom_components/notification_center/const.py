"""Constants for the Notification Center integration."""

from __future__ import annotations

DOMAIN = "notification_center"
PARENT_TITLE = "Notification Center"

# Config entry / subentry types
SUBENTRY_TYPE_RULE = "rule"

# --- Priorities -------------------------------------------------------------
PRIORITY_CRITICAL = "critical"
PRIORITY_WARNING = "warning"
PRIORITY_INFO = "info"
PRIORITY_DIGEST = "digest"

PRIORITIES = [PRIORITY_CRITICAL, PRIORITY_WARNING, PRIORITY_INFO, PRIORITY_DIGEST]

# Higher number == more important. Used to pick the "highest" active priority.
PRIORITY_ORDER = {
    PRIORITY_CRITICAL: 3,
    PRIORITY_WARNING: 2,
    PRIORITY_INFO: 1,
    PRIORITY_DIGEST: 0,
}

PRIORITY_NONE = "none"

# Default colors per the priority matrix in the design.
PRIORITY_COLORS = {
    PRIORITY_CRITICAL: "#EA4D3D",
    PRIORITY_WARNING: "#EF8C00",
    PRIORITY_INFO: "#7295B2",
    PRIORITY_DIGEST: "#9A988F",
}

PRIORITY_ICONS = {
    PRIORITY_CRITICAL: "mdi:alert-octagon",
    PRIORITY_WARNING: "mdi:alert",
    PRIORITY_INFO: "mdi:information",
    PRIORITY_DIGEST: "mdi:format-list-bulleted",
}

# iOS interruption-level (push) per priority.
PRIORITY_INTERRUPTION_LEVEL = {
    PRIORITY_CRITICAL: "critical",
    PRIORITY_WARNING: "time-sensitive",
    PRIORITY_INFO: "passive",
    PRIORITY_DIGEST: "passive",
}

# Default per-priority cooldown (minutes); 0 == no cooldown.
PRIORITY_COOLDOWN = {
    PRIORITY_CRITICAL: 0,
    PRIORITY_WARNING: 15,
    PRIORITY_INFO: 60,
    PRIORITY_DIGEST: 720,
}

# --- Channels ---------------------------------------------------------------
CHANNEL_MOBILE = "mobile"
CHANNEL_BELL = "bell"
CHANNEL_WALL = "wall"
CHANNEL_TTS = "tts"
CHANNEL_NAVIGATE = "navigate"

CHANNELS = [
    CHANNEL_MOBILE,
    CHANNEL_BELL,
    CHANNEL_WALL,
    CHANNEL_TTS,
    CHANNEL_NAVIGATE,
]

# --- Source types -----------------------------------------------------------
SOURCE_STATE = "state"
SOURCE_NUMERIC = "numeric"
SOURCE_TEMPLATE = "template"

SOURCE_TYPES = [SOURCE_STATE, SOURCE_NUMERIC, SOURCE_TEMPLATE]

# Operators
OP_EQ = "=="
OP_NE = "!="
OP_GT = ">"
OP_LT = "<"
OP_GE = ">="
OP_LE = "<="

STATE_OPERATORS = [OP_EQ, OP_NE]
NUMERIC_OPERATORS = [OP_GT, OP_LT, OP_GE, OP_LE, OP_EQ, OP_NE]

# --- Quiet hours behaviors --------------------------------------------------
QH_IGNORE = "ignore"  # deliver as-is (critical default)
QH_DOWNGRADE = "downgrade"  # drop one priority level
QH_SUPPRESS = "suppress"  # do not push, still show on wall/bell
QH_BATCH = "batch"  # hold push until quiet hours end / next digest window

QUIET_HOURS_BEHAVIORS = [QH_IGNORE, QH_DOWNGRADE, QH_SUPPRESS, QH_BATCH]

# --- Presence routing -------------------------------------------------------
PRESENCE_ALL = "all"
PRESENCE_AWAY_ONLY = "away_only"
PRESENCE_PER_PERSON = "per_person"

PRESENCE_ROUTING = [PRESENCE_ALL, PRESENCE_AWAY_ONLY, PRESENCE_PER_PERSON]

# --- Rule config keys -------------------------------------------------------
CONF_NAME = "name"
CONF_ENABLED = "enabled"
CONF_SOURCE_TYPE = "source_type"
CONF_ENTITY_ID = "entity_id"
CONF_OPERATOR = "operator"
CONF_VALUE = "value"
CONF_CONDITION_TEMPLATE = "condition_template"
CONF_PRIORITY = "priority"
CONF_CHANNELS = "channels"
CONF_ICON = "icon"
CONF_COLOR = "color"
CONF_TITLE_TEMPLATE = "title_template"
CONF_MESSAGE_TEMPLATE = "message_template"
CONF_NAVIGATION_TARGET = "navigation_target"
CONF_DEDUP_TAG = "dedup_tag"
CONF_COOLDOWN = "cooldown"
CONF_AUTO_CLEAR = "auto_clear"
CONF_QUIET_HOURS_BEHAVIOR = "quiet_hours_behavior"
CONF_PRESENCE_ROUTING = "presence_routing"
CONF_ESCALATION_AFTER = "escalation_after"
CONF_TTS_TARGETS = "tts_targets"
CONF_DIGEST_GROUP = "digest_group"

# --- Parent (options) config keys -------------------------------------------
CONF_MOBILE_TARGETS = "mobile_targets"  # list[str] of notify service names
CONF_PERSONS = "persons"  # list[dict]: person/notify/media_player
CONF_TTS_SERVICE = "tts_service"
CONF_TTS_DEFAULT_TARGETS = "tts_default_targets"
CONF_FULLY_KIOSK_DEVICES = "fully_kiosk_devices"
CONF_QUIET_HOURS_START = "quiet_hours_start"
CONF_QUIET_HOURS_END = "quiet_hours_end"
CONF_DEBOUNCE_MS = "debounce_ms"

DEFAULT_TTS_SERVICE = "tts.speak"
DEFAULT_DEBOUNCE_MS = 300
DEFAULT_QUIET_HOURS_START = "22:00:00"
DEFAULT_QUIET_HOURS_END = "07:00:00"

# --- Platforms & services ---------------------------------------------------
PLATFORMS = ["sensor", "binary_sensor"]

SERVICE_SEND = "send"
SERVICE_ACKNOWLEDGE = "acknowledge"
SERVICE_SNOOZE = "snooze"
SERVICE_DISMISS = "dismiss"
SERVICE_RELOAD = "reload"

# Dispatcher signal used to tell entities the active-alert set changed.
SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"

# Manual-send default cooldown bookkeeping uses this prefix as the tag source.
MANUAL_TAG_PREFIX = "manual"
