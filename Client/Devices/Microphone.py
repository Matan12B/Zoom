import queue
import sounddevice as sd
import numpy

class Microphone:
    def __init__(self, volume, rate=16000, channels=1, chunk=1024, device_index=None):
        self.running = False
        self.is_muted = True
        self.records = queue.Queue()
        self.volume = self._validate_volume(volume)
        # Audio settings
        self.rate = rate
        self.channels = channels
        self.chunk = chunk
        self.device_index = device_index
        # SoundDevice stream
        self.stream = None

    def _validate_volume(self, volume: int) -> int:
        """
        validate volume
        """
        if not 0 <= volume <= 100:
            raise ValueError("Volume must be between 0 and 100.")
        return volume

    def start(self):
        """
        if microphone is not active, start microphone
        """
        if not self.running:
            self.stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                dtype='int16',
                blocksize=self.chunk,
                device=self.device_index
            )
            self.stream.start()
            self.running = True
            print("Microphone started.")

    def stop(self):
        """
        stop the mic
        """
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.running = False
        print("Microphone stopped.")

    def set_volume(self, volume):
        """
        set volume
        """
        self.volume = self._validate_volume(volume)

    def record(self):
        """
        record the microphone
        :return: audio data
        """
        if not self.running:
            raise RuntimeError("Microphone is not active.")
        data, _ = self.stream.read(self.chunk)  # numpy array
        if self.is_muted:
            result = b'\x00' * (data.size * 2)  # int16 = 2 bytes
        else:
            data = self._apply_volume(data)
            result = data.tobytes()
        return result

    def _apply_volume(self, data):
        """
        apply volume
        """
        # data is already a numpy array (int16)
        scaled = (data * (self.volume / 100)).astype(numpy.int16)
        return scaled

    def unmute(self):
        """
        unmute mic
        """
        self.is_muted = False

    def mute(self):
        """
        mute mic
        """
        self.is_muted = True
