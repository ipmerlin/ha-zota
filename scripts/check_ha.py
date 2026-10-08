"""Smoke-check entity API compatibility with real Home Assistant."""

import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.zota.api import Boiler  # noqa: E402
from custom_components.zota.protocol import BoilerState  # noqa: E402

for name in (
    "__init__",
    "config_flow",
    "climate",
    "sensor",
    "binary_sensor",
    "number",
    "select",
    "switch",
    "diagnostics",
):
    import_module(f"custom_components.zota.{name}")

# Import test telemetry without installing a fake HA package or executing tests.
namespace = {}
source = (Path(__file__).resolve().parents[1] / "tests/conftest.py").read_text()
exec(source[source.index("CAPTURE =") :], namespace)
state = BoilerState.parse(namespace["CAPTURE"])
coordinator = SimpleNamespace(
    data=state,
    client=SimpleNamespace(boiler=Boiler(1234, "Test", "unused.invalid", 0)),
    last_update_success=True,
)
climate = import_module("custom_components.zota.climate").ZotaClimate(coordinator)
assert climate.hvac_mode.value == "heat"
assert climate.current_temperature == 17.4
assert climate.target_temperature == 18
water = import_module("custom_components.zota.number").ZotaWaterTarget(coordinator)
assert (water.native_min_value, water.native_max_value, water.native_value) == (50, 80, 72)
power = import_module("custom_components.zota.select").ZotaPower(coordinator)
assert power.current_option == "3: 4.5 kW"
assert len(power.options) == 8
print("Home Assistant module imports and entity API smoke checks passed")
