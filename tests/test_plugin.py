"""Offline packaging and entry-point regressions; Python 3.11+, no Azure calls."""

import ast
import json
import os
from pathlib import Path
import re
import tomllib
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "manage-ai-gateway",
    "use-ai-gateway",
    "migrate-ai-gateway",
    "feedback-ai-gateway",
}
COMMANDS = {"build", "create", "discover", "manage", "migrate", "feedback"}
HOST_MANIFESTS = (
    ".github/plugin/plugin.json",
    ".claude-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
    "gemini-extension.json",
)
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def load_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Missing frontmatter: {path}")
    return text.split("---\n", 2)[1]


def field(header, name):
    match = re.search(rf"^{re.escape(name)}: (.+)$", header, re.MULTILINE)
    if not match:
        raise ValueError(f"Missing {name}")
    return match.group(1)


class PluginTests(unittest.TestCase):
    def test_portable_manifest_closed_fields_and_identity(self):
        manifest = load_json("plugin.json")
        allowed = {
            "$schema", "name", "version", "description", "author", "homepage",
            "repository", "license", "keywords", "extensions",
        }
        self.assertLessEqual(set(manifest), allowed)
        self.assertEqual(manifest["$schema"], SCHEMA)
        self.assertRegex(manifest["name"], r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")
        self.assertEqual(manifest["name"], "aigateway")
        self.assertEqual(manifest["repository"], "https://github.com/Azure/aigateway")
        self.assertEqual(manifest["license"], "MIT")
        self.assertLessEqual(set(manifest["author"]), {"name", "email", "url"})
        self.assertTrue(all(isinstance(value, str) for value in manifest["author"].values()))
        self.assertTrue(all(isinstance(value, str) for value in manifest["keywords"]))
        self.assertNotIn("commands", manifest)
        self.assertNotIn("skills", manifest)

    def test_host_versions_and_paths(self):
        version = load_json("plugin.json")["version"]
        for path in HOST_MANIFESTS:
            with self.subTest(path=path):
                manifest = load_json(path)
                self.assertEqual(manifest["name"], "aigateway")
                self.assertEqual(manifest["version"], version)
                self.assertNotIn("Azure/ai-gateway", json.dumps(manifest))
                self.assertEqual(
                    {Path(p).name for p in manifest["skills"]}, SKILLS
                )
                for component in manifest["commands"] + manifest["skills"]:
                    target = (ROOT / component).resolve()
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.exists(), component)
                self.assertEqual(
                    {Path(p).stem for p in manifest["commands"]}, COMMANDS
                )

    def test_marketplaces_resolve_same_root_version(self):
        root = load_json("plugin.json")
        for path in (".github/plugin/marketplace.json", ".claude-plugin/marketplace.json"):
            with self.subTest(path=path):
                catalog = load_json(path)
                self.assertEqual(catalog["name"], "azure")
                self.assertEqual(len(catalog["plugins"]), 1)
                entry = catalog["plugins"][0]
                self.assertEqual(entry["name"], root["name"])
                self.assertEqual(entry["version"], root["version"])
                self.assertEqual(entry["source"], "./")

    def test_four_portable_skills_with_standard_frontmatter(self):
        paths = list((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual({path.parent.name for path in paths}, SKILLS)
        for path in paths:
            with self.subTest(path=path):
                header = frontmatter(path)
                self.assertEqual(field(header, "name"), path.parent.name)
                self.assertTrue(field(header, "description"))
                self.assertLessEqual(len(field(header, "description")), 1024)
                self.assertEqual(field(header, "license"), "MIT")
                self.assertIn("metadata:\n  author: Microsoft\n", header)
                self.assertRegex(header, r'\n  version: "\d+\.\d+\.\d+"\n')
                self.assertNotRegex(header, r"(?m)^version:")

    def test_thin_copilot_and_gemini_adapters(self):
        adapters = ROOT / "com.github.copilot/commands"
        self.assertEqual({p.stem for p in adapters.glob("*.md")}, COMMANDS)
        for name in COMMANDS:
            with self.subTest(command=name):
                canonical = ROOT / "commands" / f"{name}.md"
                adapter = (adapters / f"{name}.md").read_text(encoding="utf-8")
                self.assertIn(f"`commands/{name}.md`", adapter)
                self.assertIn("$ARGUMENTS", adapter)
                self.assertLess(len(adapter), 650)
                data = tomllib.loads(
                    (ROOT / "commands/aigateway" / f"{name}.toml").read_text(encoding="utf-8")
                )
                self.assertIn("{{args}}", data["prompt"])
                self.assertTrue(data["description"])
                if name in {"build", "create", "discover", "manage"}:
                    self.assertIn(f"commands/{name}.md", data["prompt"])
                    self.assertEqual(data["description"], field(frontmatter(canonical), "description"))
                    self.assertLess(len(data["prompt"]), 450)

    def test_entry_point_budgets_and_progressive_recipes(self):
        for name, byte_limit, line_limit in (
            ("manage-ai-gateway", 10000, 180),
            ("use-ai-gateway", 8000, 130),
        ):
            with self.subTest(skill=name):
                data = (ROOT / "skills" / name / "SKILL.md").read_bytes()
                self.assertLessEqual(len(data), byte_limit)
                self.assertLessEqual(len(data.splitlines()), line_limit)
                self.assertIn(b"references/", data)
                self.assertIn(b"not", data)

    def test_bundled_markdown_links_resolve(self):
        paths = [ROOT / "README.md", *ROOT.glob("skills/**/*.md")]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                with self.subTest(path=path.relative_to(ROOT), target=target):
                    resolved = (path.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(resolved.is_relative_to(ROOT), target)
                    self.assertTrue(resolved.exists(), target)

    def test_runtime_python_example_is_valid_and_bounded(self):
        text = (ROOT / "skills/use-ai-gateway/references/runtime-integration.md").read_text(
            encoding="utf-8"
        )
        examples = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)
        self.assertTrue(examples)
        for example in examples:
            ast.parse(example)
            self.assertNotIn("******", example)
        self.assertIn("max_retries=0", text)
        self.assertIn("timeout=30.0", text)
        self.assertIn("reply.choices", text)
        self.assertIn("runtime authentication contract", text)
        self.assertIn("az aigateway api-key list-secrets", text)

    def test_chat_example_checks_output_and_sanitizes_failures(self):
        text = (ROOT / "skills/use-ai-gateway/references/runtime-integration.md").read_text(
            encoding="utf-8"
        )
        example = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)[0]
        environment = {
            "AI_GATEWAY_AUTH": "key",
            "AI_GATEWAY_API_KEY": "synthetic-test-binding",
            "AI_GATEWAY_MODEL_BASE_URL": "https://gateway.example/default/models/openai/v1",
            "AI_GATEWAY_MODEL": "support/assistant",
        }
        module = ModuleType("openai")

        class StatusError(Exception):
            status_code = 403

        class ConnectionError(Exception):
            pass

        module.APIStatusError = StatusError
        module.APIConnectionError = ConnectionError
        good = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))]
        )
        for result, expected in (
            (good, None),
            (SimpleNamespace(choices=[]), "returned no text"),
            (StatusError("private response headers"), "HTTP 403"),
            (ConnectionError("private connection details"), "connection failed"),
        ):
            calls = []

            class Client:
                def __init__(self, **kwargs):
                    calls.append(kwargs)
                    self.chat = SimpleNamespace(completions=self)

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def create(self, **kwargs):
                    calls.append(kwargs)
                    if isinstance(result, Exception):
                        raise result
                    return result

            module.OpenAI = Client
            with self.subTest(result=expected), patch.dict("sys.modules", {"openai": module}), \
                    patch.dict(os.environ, environment, clear=True), patch("builtins.print") as output:
                if expected:
                    with self.assertRaises(SystemExit) as error:
                        exec(compile(example, "<bundled-chat-example>", "exec"), {})
                    self.assertIn(expected, str(error.exception))
                    self.assertNotIn("private", str(error.exception))
                    output.assert_not_called()
                else:
                    exec(compile(example, "<bundled-chat-example>", "exec"), {})
                    output.assert_called_once_with("hello")
                self.assertEqual(calls[0]["base_url"], environment["AI_GATEWAY_MODEL_BASE_URL"])
                self.assertEqual(calls[0]["max_retries"], 0)
                self.assertEqual(calls[0]["timeout"], 30.0)
                self.assertEqual(calls[1]["model"], "support/assistant")


if __name__ == "__main__":
    unittest.main()
