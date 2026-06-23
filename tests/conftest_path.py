"""Make the pure-logic modules importable without Home Assistant.

These tests exercise only modules with no top-level ``homeassistant`` imports
(const, rule's ``match_value`` + dataclass, router, quiet_hours). Importing
them normally would execute ``custom_components/notification_center/__init__.py``
which pulls in voluptuous/Home Assistant. We register lightweight stub package
objects (with ``__path__`` set) so submodule imports resolve directly to the
source files without running that package init.
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Only stub the package when Home Assistant isn't installed (the dev sandbox).
# In CI/HA, voluptuous + homeassistant are present, so the real package imports
# fine and stubbing would actually get in the way of the HA integration tests.
try:
    import voluptuous  # noqa: F401

    _HA_PRESENT = True
except ImportError:
    _HA_PRESENT = False

_CC = os.path.join(ROOT, "custom_components")
_NC = os.path.join(_CC, "notification_center")

if not _HA_PRESENT:
    if "custom_components" not in sys.modules:
        _m = types.ModuleType("custom_components")
        _m.__path__ = [_CC]
        sys.modules["custom_components"] = _m

    if "custom_components.notification_center" not in sys.modules:
        _m = types.ModuleType("custom_components.notification_center")
        _m.__path__ = [_NC]
        sys.modules["custom_components.notification_center"] = _m
