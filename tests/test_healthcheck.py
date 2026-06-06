import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import healthcheck as hc_module
from desktop_agent.healthcheck import (
    check_config,
    check_desktop_path,
    check_target_root,
    check_ollama_api,
    check_model_exists,
    check_openai_compatible_config,
    check_modules,
    run_healthcheck,
)
from desktop_agent import config as config_module


class CheckConfigTests(unittest.TestCase):
    def test_ok_with_none_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({"desktop_path": r"C:\Desktop", "normal_target_root": r"D:\S", "llm_provider": "none"}),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                ok, msg = check_config()
            self.assertTrue(ok)

    def test_ok_with_openai_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({
                    "desktop_path": r"C:\Desktop",
                    "normal_target_root": r"D:\S",
                    "llm_provider": "openai_compatible",
                    "api_model": "qwen-turbo",
                }),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                ok, msg = check_config()
            self.assertTrue(ok)
            self.assertIn("openai_compatible", msg)

    def test_fail_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "config.json"
            with mock.patch.object(config_module, "CONFIG_FILE", str(missing)):
                ok, msg = check_config()
            self.assertFalse(ok)
            self.assertIn("错误", msg)


class CheckDesktopPathTests(unittest.TestCase):
    def test_ok_when_path_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp) / "Desktop"
            desktop.mkdir()
            cfg = {
                "desktop_path": str(desktop),
                "_desktop_path_was_empty": False,
                "normal_target_root": str(tmp),
            }
            with mock.patch.object(hc_module, "load_config", return_value=cfg):
                ok, msg = check_desktop_path()
            self.assertTrue(ok)

    def test_fail_when_path_missing(self):
        cfg = {
            "desktop_path": r"C:\DoesNotExist\Desktop",
            "_desktop_path_was_empty": False,
            "normal_target_root": r"D:\Sorted",
        }
        with mock.patch.object(hc_module, "load_config", return_value=cfg):
            ok, msg = check_desktop_path()
        self.assertFalse(ok)
        self.assertIn("不存在", msg)


class CheckTargetRootTests(unittest.TestCase):
    def test_ok_creates_dir_and_writes_test_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Sorted"
            cfg = {"normal_target_root": str(target), "desktop_path": "", "_desktop_path_was_empty": True}
            with mock.patch.object(hc_module, "load_config", return_value=cfg):
                ok, msg = check_target_root()
            self.assertTrue(ok)
            self.assertTrue(target.exists())
            self.assertFalse((target / ".agent_write_test.tmp").exists())

    def test_fail_when_path_not_writable(self):
        cfg = {"normal_target_root": r"C:\Windows\System32\ProtectedFolder", "desktop_path": ""}
        with mock.patch.object(hc_module, "load_config", return_value=cfg):
            with mock.patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
                ok, msg = check_target_root()
            self.assertFalse(ok)


class CheckOllamaApiTests(unittest.TestCase):
    def test_skips_for_none_provider(self):
        with mock.patch.object(hc_module, "get_provider", return_value="none"):
            ok, msg = check_ollama_api()
        self.assertTrue(ok)
        self.assertIn("none", msg)

    def test_skips_for_openai_compatible(self):
        with mock.patch.object(hc_module, "get_provider", return_value="openai_compatible"):
            ok, msg = check_ollama_api()
        self.assertTrue(ok)

    def test_skips_for_builtin(self):
        with mock.patch.object(hc_module, "get_provider", return_value="builtin"):
            ok, msg = check_ollama_api()
        self.assertTrue(ok)

    def test_fails_for_unknown_provider(self):
        with mock.patch.object(hc_module, "get_provider", return_value="unknown_provider"):
            ok, msg = check_ollama_api()
        self.assertFalse(ok)

    def test_ollama_connection_ok(self):
        fake_response = mock.MagicMock()
        fake_response.json.return_value = {"models": [{"name": "qwen"}]}
        cfg = {"ollama_url": "http://localhost:11434/api/generate"}
        with mock.patch.object(hc_module, "get_provider", return_value="ollama"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch("requests.get", return_value=fake_response):
            ok, msg = check_ollama_api()
        self.assertTrue(ok)
        self.assertIn("1", msg)

    def test_ollama_connection_fail(self):
        cfg = {"ollama_url": "http://localhost:11434/api/generate"}
        with mock.patch.object(hc_module, "get_provider", return_value="ollama"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch("requests.get", side_effect=Exception("connection refused")):
            ok, msg = check_ollama_api()
        self.assertFalse(ok)


class CheckModelExistsTests(unittest.TestCase):
    def test_skips_for_none(self):
        with mock.patch.object(hc_module, "get_provider", return_value="none"):
            ok, _ = check_model_exists()
        self.assertTrue(ok)

    def test_skips_for_openai_compatible(self):
        with mock.patch.object(hc_module, "get_provider", return_value="openai_compatible"):
            ok, _ = check_model_exists()
        self.assertTrue(ok)

    def test_skips_for_builtin(self):
        with mock.patch.object(hc_module, "get_provider", return_value="builtin"):
            ok, _ = check_model_exists()
        self.assertTrue(ok)

    def test_model_found(self):
        cfg = {"model": "qwen2.5:7b", "ollama_url": "http://localhost:11434/api/generate"}
        fake_response = mock.MagicMock()
        fake_response.json.return_value = {"models": [{"name": "qwen2.5:7b"}]}
        with mock.patch.object(hc_module, "get_provider", return_value="ollama"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch("requests.get", return_value=fake_response):
            ok, msg = check_model_exists()
        self.assertTrue(ok)

    def test_model_not_found(self):
        cfg = {"model": "missing_model:7b", "ollama_url": "http://localhost:11434/api/generate"}
        fake_response = mock.MagicMock()
        fake_response.json.return_value = {"models": [{"name": "other_model:7b"}]}
        with mock.patch.object(hc_module, "get_provider", return_value="ollama"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch("requests.get", return_value=fake_response):
            ok, msg = check_model_exists()
        self.assertFalse(ok)
        self.assertIn("不存在", msg)


class CheckOpenAICompatibleConfigTests(unittest.TestCase):
    def test_skips_for_non_openai_provider(self):
        with mock.patch.object(hc_module, "get_provider", return_value="none"):
            ok, _ = check_openai_compatible_config()
        self.assertTrue(ok)

    def test_ok_when_all_fields_present(self):
        cfg = {
            "api_base_url": "https://api.example.com/v1",
            "api_model": "qwen-turbo",
            "api_key": "sk-test",
        }
        with mock.patch.object(hc_module, "get_provider", return_value="openai_compatible"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch.dict("os.environ", {}, clear=True):
            ok, msg = check_openai_compatible_config()
        self.assertTrue(ok)

    def test_fail_when_api_base_url_missing(self):
        cfg = {"api_base_url": "", "api_model": "qwen", "api_key": "sk-test"}
        with mock.patch.object(hc_module, "get_provider", return_value="openai_compatible"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch.dict("os.environ", {}, clear=True):
            ok, msg = check_openai_compatible_config()
        self.assertFalse(ok)
        self.assertIn("api_base_url", msg)

    def test_fail_when_api_key_missing(self):
        cfg = {"api_base_url": "https://api.example.com", "api_model": "qwen", "api_key": ""}
        with mock.patch.object(hc_module, "get_provider", return_value="openai_compatible"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch.dict("os.environ", {"DESKTOP_AGENT_API_KEY": ""}, clear=False):
            ok, msg = check_openai_compatible_config()
        self.assertFalse(ok)

    def test_env_var_provides_api_key(self):
        cfg = {"api_base_url": "https://api.example.com", "api_model": "qwen", "api_key": ""}
        with mock.patch.object(hc_module, "get_provider", return_value="openai_compatible"), \
             mock.patch.object(hc_module, "load_config", return_value=cfg), \
             mock.patch.dict("os.environ", {"DESKTOP_AGENT_API_KEY": "sk-from-env"}):
            ok, msg = check_openai_compatible_config()
        self.assertTrue(ok)


class CheckModulesTests(unittest.TestCase):
    def test_all_modules_importable(self):
        ok, msg = check_modules()
        self.assertTrue(ok)
        self.assertIn("正常", msg)


class RunHealthcheckTests(unittest.TestCase):
    def test_returns_list_of_check_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp) / "Desktop"
            desktop.mkdir()
            target = Path(tmp) / "Sorted"
            target.mkdir()
            cfg = {
                "desktop_path": str(desktop),
                "_desktop_path_was_empty": False,
                "normal_target_root": str(target),
                "llm_provider": "none",
            }
            with mock.patch.object(hc_module, "load_config", return_value=cfg), \
                 mock.patch.object(config_module, "load_config", return_value=cfg):
                results = run_healthcheck()
            self.assertIsInstance(results, list)
            for r in results:
                self.assertIn("name", r)
                self.assertIn("ok", r)
                self.assertIn("message", r)
