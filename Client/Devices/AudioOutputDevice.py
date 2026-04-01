import sounddevice as sd
import numpy as np


class AudioOutput:
    def __init__(self, rate=44100, channels=2, device_index=None):
        """
        Initialize output device.
        :param rate: Sample rate (e.g. 16000Hz)
        :param channels: Number of channels (1 = mono, 2 = stereo)
        :param device_index: Output device ID (None = default)
        """
        self.rate = rate
        self.channels = channels
        self.device_index = device_index
        self.stream = None
        self._open_stream()

    def _open_stream(self):
        try:
            self.stream = sd.OutputStream(
                samplerate=self.rate,
                channels=self.channels,
                dtype='int16',
                device=self.device_index,
                latency='low'
            )
            self.stream.start()
        except Exception as e:
            print(f"AudioOutput stream open error: {e}")
            self.stream = None

    def play_bytes(self, audio_bytes):
        """Play raw int16 bytes, restarting the stream if it has failed."""
        if not audio_bytes:
            return

        if self.stream is None:
            self._open_stream()
            if self.stream is None:
                return

        try:
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)

            if self.channels > 1:
                # Trim to exact multiple of channel count
                trim = (len(audio_data) // self.channels) * self.channels
                audio_data = audio_data[:trim].reshape(-1, self.channels)

            if len(audio_data) == 0:
                return

            self.stream.write(audio_data)
        except Exception as e:
            print(f"AudioOutput play_bytes error: {e} — restarting stream")
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            self._open_stream()

    def stop(self):
        """Close stream and release resources"""
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    @staticmethod
    def list_devices():
        """List all available audio devices"""
        print(sd.query_devices())

def main():
    a = AudioOutput()
