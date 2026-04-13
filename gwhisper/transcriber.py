import numpy as np
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, config):
        cfg = config["transcriber"]
        self.language = cfg["language"]
        self.beam_size = cfg["beam_size"]
        try:
            self.model = WhisperModel(
                cfg["model_size"],
                device=cfg["device"],
                compute_type=cfg["compute_type"],
            )
        except Exception as e:
            raise RuntimeError(
                f"Falha ao carregar modelo '{cfg['model_size']}': {e}"
            ) from e

    def warmup(self):
        silence = np.zeros(16000, dtype=np.float32)
        self.transcribe(silence)

    def transcribe(self, audio):
        if len(audio) == 0:
            return ""
        segments, _ = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
