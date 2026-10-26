"""Gaming and esports performance tuning pipeline for ZCF.

Provides zero-config integration for:
- Gamescope micro-compositor with resolution decoupling and AMD FSR / NIS upscaling
- Feral GameMode (gamemoderun) process and CPU governor prioritization
- MangoHud real-time performance overlay
- Low-latency audio fast-path for PipeWire and PulseAudio
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GamingTuningConfig:
    """Configuration for Linux gaming execution accelerators."""

    enabled: bool = False
    use_gamemode: bool = False
    use_gamescope: bool = False
    gamescope_render_res: Tuple[int, int] = (1920, 1080)
    gamescope_output_res: Tuple[int, int] = (1920, 1080)
    upscaling_filter: str = "fsr"  # fsr, nis, pixel, linear
    fsr_sharpness: int = 5         # 0 (max sharpness) to 10 (off) in FSR 1.0, or 0-10 scale
    fps_limit: Optional[int] = None
    fullscreen: bool = True
    borderless: bool = False
    use_mangohud: bool = False
    mangohud_preset: str = "compact"  # fps_only, compact, full
    low_latency_audio: bool = True
    custom_gamescope_args: List[str] = field(default_factory=list)
    custom_env: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "use_gamemode": self.use_gamemode,
            "use_gamescope": self.use_gamescope,
            "gamescope_render_res": list(self.gamescope_render_res),
            "gamescope_output_res": list(self.gamescope_output_res),
            "upscaling_filter": self.upscaling_filter,
            "fsr_sharpness": self.fsr_sharpness,
            "fps_limit": self.fps_limit,
            "fullscreen": self.fullscreen,
            "borderless": self.borderless,
            "use_mangohud": self.use_mangohud,
            "mangohud_preset": self.mangohud_preset,
            "low_latency_audio": self.low_latency_audio,
            "custom_gamescope_args": list(self.custom_gamescope_args),
            "custom_env": dict(self.custom_env),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GamingTuningConfig:
        render_res = data.get("gamescope_render_res", [1920, 1080])
        output_res = data.get("gamescope_output_res", [1920, 1080])
        return cls(
            enabled=bool(data.get("enabled", False)),
            use_gamemode=bool(data.get("use_gamemode", False)),
            use_gamescope=bool(data.get("use_gamescope", False)),
            gamescope_render_res=(int(render_res[0]), int(render_res[1])),
            gamescope_output_res=(int(output_res[0]), int(output_res[1])),
            upscaling_filter=str(data.get("upscaling_filter", "fsr")),
            fsr_sharpness=int(data.get("fsr_sharpness", 5)),
            fps_limit=int(data["fps_limit"]) if data.get("fps_limit") is not None else None,
            fullscreen=bool(data.get("fullscreen", True)),
            borderless=bool(data.get("borderless", False)),
            use_mangohud=bool(data.get("use_mangohud", False)),
            mangohud_preset=str(data.get("mangohud_preset", "compact")),
            low_latency_audio=bool(data.get("low_latency_audio", True)),
            custom_gamescope_args=list(data.get("custom_gamescope_args") or []),
            custom_env=dict(data.get("custom_env") or {}),
        )


def get_tuning_preset(name: str) -> GamingTuningConfig:
    """Return a pre-configured gaming tuning profile."""
    preset_lower = name.strip().lower()
    if preset_lower in ("esports", "competitive"):
        return GamingTuningConfig(
            enabled=True,
            use_gamemode=True,
            use_gamescope=True,
            gamescope_render_res=(1920, 1080),
            gamescope_output_res=(1920, 1080),
            upscaling_filter="fsr",
            fsr_sharpness=5,
            fps_limit=144,
            fullscreen=True,
            use_mangohud=True,
            mangohud_preset="compact",
            low_latency_audio=True,
        )
    elif preset_lower in ("4k_fidelity", "4k", "fidelity"):
        return GamingTuningConfig(
            enabled=True,
            use_gamemode=True,
            use_gamescope=True,
            gamescope_render_res=(1920, 1080),
            gamescope_output_res=(3840, 2160),
            upscaling_filter="fsr",
            fsr_sharpness=7,
            fps_limit=None,
            fullscreen=True,
            use_mangohud=False,
            low_latency_audio=True,
        )
    elif preset_lower in ("power_saver", "battery", "efficient"):
        return GamingTuningConfig(
            enabled=True,
            use_gamemode=False,
            use_gamescope=True,
            gamescope_render_res=(1280, 720),
            gamescope_output_res=(1920, 1080),
            upscaling_filter="fsr",
            fsr_sharpness=4,
            fps_limit=60,
            fullscreen=True,
            use_mangohud=False,
            low_latency_audio=True,
        )
    elif preset_lower in ("minimal_overlay", "overlay"):
        return GamingTuningConfig(
            enabled=True,
            use_gamemode=False,
            use_gamescope=False,
            use_mangohud=True,
            mangohud_preset="fps_only",
            low_latency_audio=True,
        )
    else:
        return GamingTuningConfig(enabled=False)


def check_tuning_tools_availability() -> Dict[str, bool]:
    """Check availability of gaming accelerator binaries on the host system."""
    return {
        "gamescope": shutil.which("gamescope") is not None,
        "gamemode": shutil.which("gamemoderun") is not None,
        "mangohud": shutil.which("mangohud") is not None,
        "mangoapp": shutil.which("mangoapp") is not None,
    }


def build_tuning_pipeline(
    base_cmd: List[str],
    tuning: Optional[GamingTuningConfig] = None,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """Assemble the execution command pipeline with gaming wrappers.

    Pipeline structure:
    [gamemoderun] [gamescope ... --mangoapp --] [mangohud] <base_cmd>
    """
    effective_env = dict(env or {})

    if not tuning or not tuning.enabled:
        return list(base_cmd), effective_env

    # 1. Audio low-latency environment variables
    if tuning.low_latency_audio:
        effective_env.setdefault("PIPEWIRE_LATENCY", "128/48000")
        effective_env.setdefault("PULSE_LATENCY_MSEC", "15")

    # 2. MangoHud environment variables if standalone
    if tuning.use_mangohud and not tuning.use_gamescope:
        effective_env.setdefault("MANGOHUD", "1")
        if tuning.mangohud_preset == "fps_only":
            effective_env.setdefault("MANGOHUD_CONFIG", "fps,frame_timing=0,cpu_stats=0,gpu_stats=0")
        elif tuning.mangohud_preset == "compact":
            effective_env.setdefault("MANGOHUD_CONFIG", "fps,frametime,cpu_stats,gpu_stats,ram,vram")

    # 3. Apply custom environment variables
    if tuning.custom_env:
        effective_env.update(tuning.custom_env)

    # 4. Gamescope wrapper construction
    current_cmd = list(base_cmd)

    if tuning.use_gamescope:
        gs_cmd = ["gamescope"]
        r_w, r_h = tuning.gamescope_render_res
        o_w, o_h = tuning.gamescope_output_res

        gs_cmd.extend(["-w", str(r_w), "-h", str(r_h)])
        gs_cmd.extend(["-W", str(o_w), "-H", str(o_h)])

        # Spatial upscaler selection
        valid_filters = {"fsr", "nis", "pixel", "linear"}
        upscaler = tuning.upscaling_filter.lower()
        if upscaler in valid_filters:
            gs_cmd.extend(["-F", upscaler])
            if upscaler == "fsr" and tuning.fsr_sharpness is not None:
                gs_cmd.extend(["-S", str(tuning.fsr_sharpness)])
            # If render resolution is smaller than output resolution, enable upscaling flag
            if r_w < o_w or r_h < o_h or upscaler in ("fsr", "nis"):
                gs_cmd.append("-U")

        if tuning.fps_limit and tuning.fps_limit > 0:
            gs_cmd.extend(["-r", str(tuning.fps_limit)])

        if tuning.fullscreen:
            gs_cmd.append("-f")
        elif tuning.borderless:
            gs_cmd.append("-b")

        # In Gamescope, MangoHud must be injected via --mangoapp
        if tuning.use_mangohud:
            gs_cmd.append("--mangoapp")

        if tuning.custom_gamescope_args:
            gs_cmd.extend(tuning.custom_gamescope_args)

        gs_cmd.append("--")
        current_cmd = gs_cmd + current_cmd
    elif tuning.use_mangohud:
        # Standalone MangoHud wrapper outside gamescope
        current_cmd = ["mangohud"] + current_cmd

    # 5. Feral GameMode outer wrapper
    if tuning.use_gamemode:
        current_cmd = ["gamemoderun"] + current_cmd

    return current_cmd, effective_env
