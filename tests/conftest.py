"""Load the wire client independently of Home Assistant for portable tests."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("zota_wire")
package.__path__ = [str(ROOT / "custom_components/zota")]
sys.modules["zota_wire"] = package
for name in ("const", "protocol", "api"):
    spec = importlib.util.spec_from_file_location(
        f"zota_wire.{name}", ROOT / "custom_components/zota" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

# An anonymized telemetry capture; no serial, credentials, host or account data.
CAPTURE = bytes.fromhex(
    "010006320b003200c80200000f001e002d003c004b005a00000000000000b4000a00fe"
    "4850320a00134600011c190703010301140208144a01a80001000000000000c9281900"
    "0c00ae000140014001403a2401000200000000000000000000000e0b0e080a1a"
)
