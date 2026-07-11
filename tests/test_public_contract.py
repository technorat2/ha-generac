"""Tests for the public repository contract that do not require Home Assistant."""
import ast
import base64
import binascii
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "generac_auth0_pkce"


class PublicContractTests(unittest.TestCase):
    """Validate files that HACS and Home Assistant consume directly."""

    def test_only_canonical_component_is_installable(self):
        components = sorted(
            path.name
            for path in (ROOT / "custom_components").iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        )
        self.assertEqual(components, ["generac_auth0_pkce"])

    def test_manifest(self):
        manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], COMPONENT.name)
        self.assertEqual(manifest["name"], "Generac Updated Login")
        self.assertEqual(manifest["version"], "0.3.2")
        self.assertEqual(manifest["integration_type"], "hub")
        self.assertIn("@technorat2", manifest["codeowners"])
        const_source = (COMPONENT / "const.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.3.2"', const_source)

    def test_auth_refresh_contract(self):
        source = (COMPONENT / "api.py").read_text(encoding="utf-8")
        self.assertIn("self._refresh_lock = asyncio.Lock()", source)
        self.assertIn("self._jwt_exp(self.access_token)", source)
        self.assertIn("await self.login_with_auth0_pkce()", source)
        self.assertLess(
            source.index("await self.login_with_auth0_pkce()"),
            source.index("await self.login_with_mobile_link_web()"),
        )

    def test_jwt_expiry_parser(self):
        source = (COMPONENT / "api.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_jwt_exp"
        )
        method.decorator_list = []
        namespace = {
            "base64": base64,
            "binascii": binascii,
            "json": json,
        }
        exec(
            compile(ast.Module(body=[method], type_ignores=[]), str(COMPONENT), "exec"),
            namespace,
        )
        jwt_exp = namespace["_jwt_exp"]
        payload = (
            base64.urlsafe_b64encode(json.dumps({"exp": 1234567890}).encode("utf-8"))
            .decode("ascii")
            .rstrip("=")
        )
        self.assertEqual(jwt_exp(f"header.{payload}.signature"), 1234567890.0)
        self.assertIsNone(jwt_exp("not-a-jwt"))
        self.assertIsNone(jwt_exp("header.!!!.signature"))

    def test_diagnostics_handles_unloaded_entry(self):
        source = (COMPONENT / "diagnostics.py").read_text(encoding="utf-8")
        self.assertIn('"status": "not_loaded"', source)
        self.assertIn("hass.data.get(DOMAIN, {})", source)

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
        namespace = {"DEFAULT_NAME": "generac_auth0_pkce", "re": re}
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
            parse_entity_name("generac_auth0_pkce_2413103_device_type"),
            "Device Type",
        )
        self.assertEqual(
            parse_entity_name("generac_auth0_pkce_2413103_panel_id"),
            "Panel ID",
        )

    def test_signal_strength_contract(self):
        source = (COMPONENT / "sensor.py").read_text(encoding="utf-8")
        self.assertIn("_attr_native_unit_of_measurement = PERCENTAGE", source)
        self.assertIn("_attr_state_class = SensorStateClass.MEASUREMENT", source)
        self.assertIn(
            'as_float(get_apparatus_property_value(self.item, "signalStrength"))',
            source,
        )


if __name__ == "__main__":
    unittest.main()
