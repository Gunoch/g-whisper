import numpy as np
import torch
from silero_vad import load_silero_vad, VADIterator


class VoiceActivityDetector:
    CHUNK_SIZE = 512

    def __init__(self, config):
        cfg = config["vad"]
        sample_rate = config["audio"]["sample_rate"]
        self.model = load_silero_vad()
        self.iterator = VADIterator(
            self.model,
            threshold=cfg["threshold"],
            sampling_rate=sample_rate,
            min_silence_duration_ms=cfg["min_silence_duration_ms"],
            speech_pad_ms=cfg["speech_pad_ms"],
        )
        self.is_speaking = False

    def process_chunk(self, audio_chunk):
        """Process exactly CHUNK_SIZE samples. Returns 'start', 'end', or None."""
        tensor = torch.from_numpy(audio_chunk).float()
        speech_dict = self.iterator(tensor, return_seconds=False)
        if speech_dict:
            if "start" in speech_dict:
                self.is_speaking = True
                return "start"
            elif "end" in speech_dict:
                self.is_speaking = False
                return "end"
        return None

    def reset(self):
        self.iterator.reset_states()
        self.is_speaking = False
