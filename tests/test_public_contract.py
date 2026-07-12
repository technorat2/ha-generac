"""Tests for the public repository contract that do not require Home Assistant."""
import ast
import base64
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "generac"


class PublicContractTests(unittest.TestCase):
    """Validate files that HACS and Home Assistant consume directly."""

    def test_only_canonical_component_is_installable(self):
        components = sorted(
            path.name
            for path in (ROOT / "custom_components").iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        )
        self.assertEqual(components, ["generac"])

    def test_manifest(self):
        manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], COMPONENT.name)
        self.assertEqual(manifest["name"], "Generac MobileLink")
        self.assertEqual(manifest["version"], "0.5.0")
        self.assertEqual(manifest["integration_type"], "hub")
        self.assertIn("@technorat2", manifest["codeowners"])
        const_source = (COMPONENT / "const.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.5.0"', const_source)
        self.assertIn('CONF_DPOP_PEM = "dpop_pem"', const_source)
        self.assertIn("DEFAULT_SCAN_INTERVAL = 900", const_source)

    def test_auth_refresh_contract(self):
        source = (COMPONENT / "auth.py").read_text(encoding="utf-8")
        self.assertIn("class DPoPKey", source)
        self.assertIn('"dpop_jkt"', source)
        self.assertIn('"dpop-nonce"', source)
        self.assertIn("self._refresh_lock = asyncio.Lock()", source)
        self.assertIn("timeout=REQUEST_TIMEOUT", source)
        self.assertIn("async def force_refresh", source)

        api_source = (COMPONENT / "api.py").read_text(encoding="utf-8")
        self.assertIn("Authorization", api_source)
        self.assertIn("REQUEST_TIMEOUT", api_source)
        self.assertIn("forcing one DPoP refresh", api_source)
        self.assertNotIn("session_cookie", api_source)

    def test_dpop_key_round_trip_and_proof(self):
        source_path = COMPONENT / "auth.py"
        spec = importlib.util.spec_from_file_location("generac_auth_test", source_path)
        auth_module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = auth_module
        spec.loader.exec_module(auth_module)

        key = auth_module.DPoPKey.generate()
        restored = auth_module.DPoPKey.from_pem_str(key.to_pem_str())
        proof = restored.sign_proof(
            "POST", "https://auth.ecobee.com/oauth/token", access_token="token"
        )
        header, payload, signature = proof.split(".")

        def decode(value):
            return json.loads(
                base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            )

        self.assertTrue(signature)
        self.assertEqual(decode(header)["typ"], "dpop+jwt")
        self.assertEqual(decode(payload)["htm"], "POST")
        self.assertEqual(decode(payload)["htu"], "https://auth.ecobee.com/oauth/token")
        self.assertIn("ath", decode(payload))

    def test_diagnostics_handles_unloaded_entry(self):
        source = (COMPONENT / "diagnostics.py").read_text(encoding="utf-8")
        self.assertIn('"status": "not_loaded"', source)
        self.assertIn("hass.data.get(DOMAIN, {})", source)

    def test_reauth_removes_discarded_credentials(self):
        source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        self.assertIn("_replace_auth_data", source)
        self.assertIn('"password"', source)

    def test_json_files_are_valid(self):
        for path in COMPONENT.rglob("*.json"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))

    def test_python_files_compile(self):
        for path in COMPONENT.rglob("*.py"):
            with self.subTest(path=path):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_brand_icon_is_png(self):
        icon = COMPONENT / "brand" / "icon.png"
        self.assertTrue(icon.is_file())
        self.assertEqual(icon.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_entity_name_parser(self):
        source = (COMPONENT / "entity.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        nodes = [
            node
            for node in tree.body
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "_ENTITY_WORDS"
                    for target in node.targets
                )
            )
            or (
                isinstance(node, ast.FunctionDef)
                and node.name in {"_camel_to_snake", "parse_entity_name"}
            )
        ]
        namespace = {"DEFAULT_NAME": "generac", "re": re}
        source_path = COMPONENT / "entity.py"
        exec(
            compile(
                ast.Module(body=nodes, type_ignores=[]),
                str(source_path),
                "exec",
            ),
            namespace,
        )
        parse_entity_name = namespace["parse_entity_name"]
        self.assertEqual(
            parse_entity_name("generac_2413103_device_type"),
            "Device Type",
        )
        self.assertEqual(
            parse_entity_name("generac_2413103_panel_id"),
            "Panel ID",
        )
        self.assertEqual(
            parse_entity_name("generac_2413103_device_ssid"),
            "Device SSID",
        )

    def test_signal_strength_contract(self):
        source = (COMPONENT / "sensor.py").read_text(encoding="utf-8")
        self.assertIn("_attr_native_unit_of_measurement = PERCENTAGE", source)
        self.assertIn("_attr_state_class = SensorStateClass.MEASUREMENT", source)
        self.assertIn(
            'get_apparatus_property_value(self.item, "signalStrength")',
            source,
        )
        self.assertIn("SensorStateClass.MEASUREMENT", source)


if __name__ == "__main__":
    unittest.main()
