


class Bridge:
    def __init__(self):
        self.frames = {}


    def set_frame(self, camera_id, frame):
        """

        """
        self.frames[camera_id] = frame

    def get_frame(self, camera_id):
        frame = None
        if camera_id in self.frames.keys():
            frame = self.frames[camera_id]
        return frame
