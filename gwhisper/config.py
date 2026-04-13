import copy
import os
import yaml

DEFAULTS = {
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "block_size": 512,
        "device": None,
    },
    "vad": {
        "threshold": 0.5,
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 200,
        "min_speech_duration_ms": 250,
    },
    "transcriber": {
        "model_size": "base",
        "device": "cpu",
        "compute_type": "int8",
        "language": "pt",
        "beam_size": 5,
    },
    "hotkeys": {
        "push_to_talk": "f9",
        "toggle_mode": "ctrl+shift+m",
        "quit": "ctrl+shift+q",
    },
    "output": {
        "method": "clipboard",
        "add_trailing_space": True,
    },
}

VALID_OUTPUT_METHODS = {"clipboard", "typing"}
VALID_TRANSCRIBER_DEVICES = {"cpu", "cuda", "auto"}


def _deep_merge(base, override):
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_config(cfg):
    audio = cfg["audio"]
    if audio["sample_rate"] != 16000:
        raise ValueError(
            f"audio.sample_rate deve ser 16000 (faster-whisper e Silero VAD exigem). "
            f"Valor atual: {audio['sample_rate']}"
        )
    if audio["channels"] != 1:
        raise ValueError(
            f"audio.channels deve ser 1 (mono). Valor atual: {audio['channels']}"
        )
    if audio["block_size"] != 512:
        raise ValueError(
            f"audio.block_size deve ser 512 samples (exigido pelo Silero VAD a 16kHz). "
            f"Valor atual: {audio['block_size']}"
        )

    out_method = cfg["output"]["method"]
    if out_method not in VALID_OUTPUT_METHODS:
        raise ValueError(
            f"output.method deve ser um de {VALID_OUTPUT_METHODS}. "
            f"Valor atual: {out_method!r}"
        )

    t_device = cfg["transcriber"]["device"]
    if t_device not in VALID_TRANSCRIBER_DEVICES:
        raise ValueError(
            f"transcriber.device deve ser um de {VALID_TRANSCRIBER_DEVICES}. "
            f"Valor atual: {t_device!r}"
        )

    for field in ("push_to_talk", "toggle_mode", "quit"):
        key = cfg["hotkeys"][field]
        if not key or not isinstance(key, str) or key != key.strip():
            raise ValueError(
                f"hotkeys.{field} inválido: {key!r}. "
                f"Deve ser string sem espaços nas extremidades."
            )


def load_config(path="config.yaml", validate=True):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        cfg = _deep_merge(DEFAULTS, user_config)
    else:
        cfg = copy.deepcopy(DEFAULTS)
    if validate:
        validate_config(cfg)
    return cfg
