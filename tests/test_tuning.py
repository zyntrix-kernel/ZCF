"""Unit tests for ZCF Esports & Gaming Performance Tuning Engine."""

from __future__ import annotations

import unittest

from zcf.execution.tuning import (
    GamingTuningConfig,
    build_tuning_pipeline,
    check_tuning_tools_availability,
    get_tuning_preset,
)


class TestGamingTuning(unittest.TestCase):
    def test_default_config_disabled(self):
        cfg = GamingTuningConfig()
        self.assertFalse(cfg.enabled)
        base_cmd = ["wine", "game.exe"]
        cmd, env = build_tuning_pipeline(base_cmd, cfg)
        self.assertEqual(cmd, base_cmd)

    def test_gamemode_wrapper(self):
        cfg = GamingTuningConfig(enabled=True, use_gamemode=True, use_gamescope=False)
        base_cmd = ["wine", "game.exe"]
        cmd, env = build_tuning_pipeline(base_cmd, cfg)
        self.assertEqual(cmd[0], "gamemoderun")
        self.assertEqual(cmd[1:], base_cmd)

    def test_gamescope_and_fsr_pipeline(self):
        cfg = GamingTuningConfig(
            enabled=True,
            use_gamemode=True,
            use_gamescope=True,
            gamescope_render_res=(1280, 720),
            gamescope_output_res=(1920, 1080),
            upscaling_filter="fsr",
            fsr_sharpness=5,
            fps_limit=144,
            fullscreen=True,
            use_mangohud=True,
            low_latency_audio=True,
        )
        base_cmd = ["bwrap", "--ro-bind", "/", "/", "wine", "game.exe"]
        cmd, env = build_tuning_pipeline(base_cmd, cfg)

        # Gamemode outer wrapper
        self.assertEqual(cmd[0], "gamemoderun")
        self.assertEqual(cmd[1], "gamescope")

        # Check gamescope arguments
        self.assertIn("-w", cmd)
        self.assertIn("1280", cmd)
        self.assertIn("-h", cmd)
        self.assertIn("720", cmd)
        self.assertIn("-W", cmd)
        self.assertIn("1920", cmd)
        self.assertIn("-H", cmd)
        self.assertIn("1080", cmd)
        self.assertIn("-F", cmd)
        self.assertIn("fsr", cmd)
        self.assertIn("-S", cmd)
        self.assertIn("5", cmd)
        self.assertIn("-U", cmd)
        self.assertIn("-r", cmd)
        self.assertIn("144", cmd)
        self.assertIn("-f", cmd)
        # Inside Gamescope, MangoHud must be injected via --mangoapp
        self.assertIn("--mangoapp", cmd)
        self.assertIn("--", cmd)

        # Base command preserved at tail
        dash_dash_idx = cmd.index("--")
        self.assertEqual(cmd[dash_dash_idx + 1 :], base_cmd)

        # Low latency audio env vars
        self.assertEqual(env.get("PIPEWIRE_LATENCY"), "128/48000")
        self.assertEqual(env.get("PULSE_LATENCY_MSEC"), "15")

    def test_standalone_mangohud(self):
        cfg = GamingTuningConfig(enabled=True, use_gamescope=False, use_mangohud=True, mangohud_preset="compact")
        base_cmd = ["wine", "game.exe"]
        cmd, env = build_tuning_pipeline(base_cmd, cfg)
        self.assertEqual(cmd, ["mangohud", "wine", "game.exe"])
        self.assertEqual(env.get("MANGOHUD"), "1")
        self.assertIn("fps,frametime", env.get("MANGOHUD_CONFIG", ""))

    def test_presets(self):
        esports = get_tuning_preset("esports")
        self.assertTrue(esports.enabled)
        self.assertTrue(esports.use_gamemode)
        self.assertTrue(esports.use_gamescope)
        self.assertEqual(esports.fps_limit, 144)

        fidelity = get_tuning_preset("4k_fidelity")
        self.assertEqual(fidelity.gamescope_output_res, (3840, 2160))

        power = get_tuning_preset("power_saver")
        self.assertEqual(power.fps_limit, 60)

    def test_serialization(self):
        cfg = GamingTuningConfig(enabled=True, use_gamemode=True, fps_limit=120)
        d = cfg.to_dict()
        reconstituted = GamingTuningConfig.from_dict(d)
        self.assertEqual(reconstituted.enabled, cfg.enabled)
        self.assertEqual(reconstituted.fps_limit, 120)

    def test_check_tools_availability(self):
        tools = check_tuning_tools_availability()
        self.assertIn("gamescope", tools)
        self.assertIn("gamemode", tools)
        self.assertIn("mangohud", tools)
