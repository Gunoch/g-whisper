import os
import sys
import queue
import threading
import traceback
import numpy as np

from gwhisper.config import load_config
from gwhisper.transcriber import Transcriber
from gwhisper.audio import AudioRecorder
from gwhisper.hotkeys import HotkeyManager
from gwhisper.output import type_text


class GWhisperApp:
    def __init__(self, config_path="config.yaml", status_callback=None):
        self.config = load_config(config_path)
        self.mode = "push_to_talk"
        self.status = "idle"
        self._status_callback = status_callback
        self._recording = False
        self._stop_event = None
        self._record_thread = None
        self._vad = None
        self._stream = None
        self._speech_buffer = []
        self._audio_queue = None
        self._transcribe_queue = None
        self._vad_thread = None
        self._worker_thread = None
        self._toggle_lock = threading.Lock()

        self._set_status("loading")
        print("Carregando modelo de transcrição (primeiro uso pode baixar ~150MB)...")
        self.transcriber = Transcriber(self.config)
        print("Aquecendo modelo...")
        self.transcriber.warmup()

        self.audio = AudioRecorder(self.config)
        self.hotkeys = HotkeyManager(self.config)
        self._set_status("idle")
        print("Pronto!")

    def _set_status(self, status):
        self.status = status
        if self._status_callback:
            try:
                self._status_callback(status, self.mode)
            except Exception as e:
                print(f"[!] Erro no status callback: {e}")

    def start(self):
        """Register hotkeys but don't block. For embedding (e.g. tray)."""
        self._setup_hotkeys()
        print(f"\ng-whisper rodando em modo: {self.mode}")
        print(f"  Push-to-talk: {self.config['hotkeys']['push_to_talk']}")
        print(f"  Alternar modo: {self.config['hotkeys']['toggle_mode']}")
        print(f"  Sair: {self.config['hotkeys']['quit']}")
        print()

    def run(self):
        """Start and block the current thread."""
        self.start()
        self.hotkeys.wait()

    def _setup_hotkeys(self):
        self.hotkeys.setup_push_to_talk(self._on_ptt_press, self._on_ptt_release)
        self.hotkeys.setup_toggle(self._on_toggle_mode)
        self.hotkeys.setup_quit(self._on_quit)

    # -- Push-to-talk --

    def _on_ptt_press(self):
        if self.mode != "push_to_talk":
            return
        if self._recording:
            return
        if self._record_thread and self._record_thread.is_alive():
            print("[!] Aguarde transcrição anterior terminar")
            return
        self._recording = True
        self._stop_event = threading.Event()
        print("[*] Gravando...")
        self._set_status("recording")
        self._record_thread = threading.Thread(
            target=self._record_and_transcribe, daemon=True
        )
        self._record_thread.start()

    def _on_ptt_release(self):
        if not self._recording:
            return
        self._recording = False
        if self._stop_event:
            self._stop_event.set()

    def _record_and_transcribe(self):
        try:
            audio_data = self.audio.record_until_released(self._stop_event)
        except Exception as e:
            print(f"[!] Erro na captura de áudio: {e}")
            self._recording = False
            self._set_status("idle")
            return

        min_samples = int(self.config["audio"]["sample_rate"] * 0.3)
        if len(audio_data) < min_samples:
            print("[x] Muito curto, ignorado")
            self._set_status("idle")
            return

        print("[...] Transcrevendo...")
        self._set_status("transcribing")
        try:
            text = self.transcriber.transcribe(audio_data)
        except Exception as e:
            print(f"[!] Erro na transcrição: {e}")
            self._set_status("idle")
            return

        if text:
            print(f"[ok] {text}")
            try:
                type_text(
                    text,
                    method=self.config["output"]["method"],
                    add_trailing_space=self.config["output"]["add_trailing_space"],
                )
            except Exception as e:
                print(f"[!] Erro ao inserir texto: {e}")
        else:
            print("[x] Nenhum texto reconhecido")
        self._set_status("idle")

    # -- Hands-free --

    def _start_hands_free(self):
        try:
            from gwhisper.vad import VoiceActivityDetector
        except ImportError as e:
            print(f"[!] Modo hands-free requer torch + silero-vad: {e}")
            self.mode = "push_to_talk"
            return

        if self._vad is None:
            print("Carregando modelo VAD...")
            self._vad = VoiceActivityDetector(self.config)

        self._speech_buffer = []
        self._audio_queue = queue.Queue(maxsize=1000)
        self._transcribe_queue = queue.Queue()

        chunk_size = VoiceActivityDetector.CHUNK_SIZE

        # Audio callback: only queue chunks, never block
        def on_audio_chunk(indata, frames, time_info, status):
            if status:
                print(f"[audio] {status}")
            try:
                self._audio_queue.put_nowait(indata[:, 0].copy())
            except queue.Full:
                print("[!] Audio queue cheia, descartando chunk")

        # VAD worker: process chunks from audio queue, with ring buffer
        # to ensure exactly chunk_size samples are passed to Silero VAD
        def vad_worker():
            pending = np.array([], dtype=np.float32)
            while True:
                try:
                    chunk = self._audio_queue.get()
                    if chunk is None:
                        break
                    pending = np.concatenate([pending, chunk]) if len(pending) else chunk
                    while len(pending) >= chunk_size:
                        window = pending[:chunk_size]
                        pending = pending[chunk_size:]
                        event = self._vad.process_chunk(window)
                        if event == "start":
                            self._speech_buffer = [window]
                            print("[*] Fala detectada...")
                        elif self._vad.is_speaking:
                            self._speech_buffer.append(window)
                        if event == "end" and self._speech_buffer:
                            audio = np.concatenate(self._speech_buffer)
                            self._speech_buffer = []
                            min_samples = int(
                                self.config["audio"]["sample_rate"]
                                * self.config["vad"]["min_speech_duration_ms"]
                                / 1000
                            )
                            if len(audio) >= min_samples:
                                self._transcribe_queue.put(audio)
                            else:
                                print("[x] Fala muito curta, ignorada")
                except Exception:
                    print("[!] Erro no VAD worker:")
                    traceback.print_exc()

        # Transcription worker
        def transcription_worker():
            while True:
                try:
                    audio = self._transcribe_queue.get()
                    if audio is None:
                        break
                    print("[...] Transcrevendo...")
                    text = self.transcriber.transcribe(audio)
                    if text:
                        print(f"[ok] {text}")
                        type_text(
                            text,
                            method=self.config["output"]["method"],
                            add_trailing_space=self.config["output"]["add_trailing_space"],
                        )
                    else:
                        print("[x] Nenhum texto reconhecido")
                except Exception:
                    print("[!] Erro no transcription worker:")
                    traceback.print_exc()

        self._vad_thread = threading.Thread(target=vad_worker, daemon=True)
        self._vad_thread.start()

        self._worker_thread = threading.Thread(target=transcription_worker, daemon=True)
        self._worker_thread.start()

        try:
            self._stream = self.audio.create_stream(on_audio_chunk)
            self._stream.start()
        except Exception as e:
            print(f"[!] Erro ao abrir microfone: {e}")
            self._shutdown_hands_free_threads()
            self.mode = "push_to_talk"
            return

        print("[~] Modo hands-free ativo. Fale normalmente.")

    def _shutdown_hands_free_threads(self):
        if self._audio_queue:
            try:
                self._audio_queue.put_nowait(None)
            except queue.Full:
                pass
        if self._vad_thread:
            self._vad_thread.join(timeout=5.0)
            if self._vad_thread.is_alive():
                print("[!] VAD worker não terminou em 5s")
            self._vad_thread = None
        if self._transcribe_queue:
            self._transcribe_queue.put(None)
        if self._worker_thread:
            self._worker_thread.join(timeout=10.0)
            if self._worker_thread.is_alive():
                print("[!] Transcription worker ainda rodando, aguardando...")
                self._worker_thread.join()
            self._worker_thread = None
        self._audio_queue = None
        self._transcribe_queue = None

    def _stop_hands_free(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"[!] Erro ao fechar stream: {e}")
            self._stream = None
        self._shutdown_hands_free_threads()
        if self._vad:
            self._vad.reset()
        self._speech_buffer = []
        print("[~] Modo hands-free desativado.")

    # -- Mode toggle --

    def _on_toggle_mode(self):
        if not self._toggle_lock.acquire(blocking=False):
            print("[!] Troca de modo em andamento, ignorando")
            return
        try:
            if self._recording or (self._record_thread and self._record_thread.is_alive()):
                print("[!] Aguarde PTT terminar antes de trocar de modo")
                return
            if self.mode == "push_to_talk":
                self.mode = "hands_free"
                self._start_hands_free()
            else:
                self._stop_hands_free()
                self.mode = "push_to_talk"
            print(f"Modo: {self.mode}")
            self._set_status("idle")
        finally:
            self._toggle_lock.release()

    # -- Quit --

    def _on_quit(self):
        print("\nEncerrando...")
        try:
            if self.mode == "hands_free":
                self._stop_hands_free()
            self.hotkeys.cleanup()
        except Exception as e:
            print(f"[!] Erro no shutdown: {e}")
        os._exit(0)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    if len(sys.argv) > 1 and not os.path.exists(config_path):
        print(f"[!] Config não encontrada: {config_path}")
        sys.exit(1)
    try:
        app = GWhisperApp(config_path)
    except ValueError as e:
        print(f"[!] Config inválida: {e}")
        sys.exit(1)
    try:
        app.run()
    except KeyboardInterrupt:
        app._on_quit()
