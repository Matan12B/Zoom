import sounddevice as sd
import numpy as np


class AudioOutput:
    def __init__(self, rate=44100, channels=2, device_index=None):
        """
        Initialize output device.
        Stream is created lazily on first play_bytes() call so that it is opened
        from the correct thread (the playback loop) and with the best available config.
        :param rate: Sample rate (e.g. 16000 Hz)
        :param channels: Number of channels (1 = mono, 2 = stereo)
        :param device_index: Output device ID (None = default)
        """
        self.rate = rate
        self.channels = channels
        self.device_index = device_index
        self.stream = None
        self._use_float32 = True  # set properly by _open_stream

    def _open_stream(self):
        """Try several configurations from most to least compatible."""
        configs = [
            # float32 shared-mode — most compatible on Windows WASAPI and macOS CoreAudio
            dict(samplerate=self.rate, channels=self.channels, dtype='float32',
                 device=self.device_index),
            # float32 with explicit high latency
            dict(samplerate=self.rate, channels=self.channels, dtype='float32',
                 device=self.device_index, latency='high'),
            # int16 fallback
            dict(samplerate=self.rate, channels=self.channels, dtype='int16',
                 device=self.device_index),
        ]
        for cfg in configs:
            try:
                self.stream = sd.OutputStream(**cfg)
                self.stream.start()
                self._use_float32 = (cfg['dtype'] == 'float32')
                print(f"AudioOutput stream opened: dtype={cfg['dtype']}, "
                      f"rate={self.rate}, channels={self.channels}")
                break
            except Exception as e:
                print(f"AudioOutput stream open error ({cfg.get('dtype')}, "
                      f"latency={cfg.get('latency', 'default')}): {e}")
        else:
            self.stream = None

    def play_bytes(self, audio_bytes):
        """Play audio with automatic stream recovery."""
        if not audio_bytes:
            return
        # Ensure hardware is ready (Lazy Init)
        if self.stream is None:
            self._open_stream()
        if self.stream:
            try:
                # Process the data
                audio_data = self._process_audio_data(audio_bytes)
                # Write to hardware
                if audio_data.size > 0:
                    self.stream.write(audio_data)
            except Exception as e:
                print(f"Audio error: {e} - Resetting...")
                self.stop()  # Modular cleanup
                self._open_stream()

    def _process_audio_data(self, audio_bytes):
        """Handles the math and shaping in one clear flow."""
        # Convert to numpy array
        data = np.frombuffer(audio_bytes, dtype=np.int16)
        # Normalize if needed
        if self._use_float32:
            data = data.astype(np.float32) / 32768.0
        # Align and Reshape for channels
        if self.channels > 1:
            # The // operator ensures we don't have a partial sample for stereo
            data = data[:(data.size // self.channels) * self.channels]
            data = data.reshape(-1, self.channels)
        return data
    def stop(self):
        """Close stream and release resources."""
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    @staticmethod
    def list_devices():
        """List all available audio devices."""
        print(sd.query_devices())

def main():
    a = AudioOutput()
