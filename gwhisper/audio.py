import time
import queue
import numpy as np
import sounddevice as sd


class AudioRecorder:
    def __init__(self, config):
        cfg = config["audio"]
        self.sample_rate = cfg["sample_rate"]
        self.channels = cfg["channels"]
        self.block_size = cfg.get("block_size", 512)
        self.device = cfg.get("device")

    def record_until_released(self, stop_event):
        audio_queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[audio] {status}")
            audio_queue.put(indata.copy())

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            device=self.device,
            callback=callback,
        ):
            stop_event.wait()
            time.sleep(0.05)
            chunks = []
            while not audio_queue.empty():
                chunks.append(audio_queue.get())

        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks, axis=0).flatten()

    def create_stream(self, callback):
        return sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            device=self.device,
            blocksize=self.block_size,
            callback=callback,
        )
