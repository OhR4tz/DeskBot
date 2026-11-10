"""The one AI Camera supplies both its IMX500 result and the matching RGB frame."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from .config import Config
from .gesture import Point
from .tracking import Box, Detection


@dataclass
class Frame:
    rgb: Any
    detections: list[Detection] | None
    hands: list[list[Point]]
    captured_at: float | None = None
    faces: list[Box] | None = None


def parse_ssd(outputs: Any, intrinsics: Any, imx500: Any, metadata: dict,
              picam2: Any, threshold: float) -> list[Detection] | None:
    if outputs is None:
        return None
    if getattr(intrinsics, "postprocess", None) == "nanodet":
        raise ValueError("this project requires the packaged SSD MobileNet model")
    boxes, scores, classes = outputs[0][0], outputs[1][0], outputs[2][0]
    if getattr(intrinsics, "bbox_normalization", False):
        boxes = boxes / imx500.get_input_size()[1]
    if getattr(intrinsics, "bbox_order", "yx") == "xy":
        boxes = boxes[:, [1, 0, 3, 2]]
    found: list[Detection] = []
    for coords, score, category in zip(boxes, scores, classes):
        # The packaged COCO SSD model uses class 0 for person.
        if int(category) != 0 or float(score) < threshold:
            continue
        rect = imx500.convert_inference_coords([float(x) for x in coords], metadata, picam2)
        x, y, width, height = (float(v) for v in rect)
        found.append(Detection(Box(x, y, width, height), float(score)))
    return found


class CameraVision:
    def __init__(self, config: Config, hands: bool = True) -> None:
        self.config = config
        self.want_hands = hands
        self.cam = None
        self.landmarker = None
        self.face_detector = None
        self._last_timestamp_ms = -1

    def __enter__(self) -> "CameraVision":
        if not Path(self.config.model).is_file():
            raise FileNotFoundError(f"IMX500 model missing: {self.config.model}")
        if self.want_hands and not Path(self.config.hand_model).is_file():
            raise FileNotFoundError(f"hand model missing: {self.config.hand_model}; run scripts/install-pi.sh")
        if not Path(self.config.face_model).is_file():
            raise FileNotFoundError(f"face model missing: {self.config.face_model}; run scripts/install-pi.sh")
        from picamera2.devices import IMX500
        from picamera2 import Picamera2
        from picamera2.devices.imx500 import NetworkIntrinsics
        self.imx500 = IMX500(self.config.model)  # Must precede Picamera2.
        self.intrinsics = self.imx500.network_intrinsics or NetworkIntrinsics()
        if self.intrinsics.task not in (None, "object detection"):
            raise ValueError("IMX500 model is not an object detector")
        self.intrinsics.task = "object detection"
        self.intrinsics.update_with_defaults()
        self.cam = Picamera2(self.imx500.camera_num)
        # libcamera BGR888 is RGB in numpy byte order; MediaPipe expects RGB.
        camera_config = self.cam.create_preview_configuration(
            main={"size": (self.config.width, self.config.height), "format": "BGR888"},
            # CPU face/hand updates need not wait for the person model's cadence.
            controls={"FrameRate": self.config.fps},
            buffer_count=4, queue=False)
        try:
            self.cam.start(camera_config, show_preview=False)
            if self.intrinsics.preserve_aspect_ratio:
                self.imx500.set_auto_aspect_ratio()
            import mediapipe as mp
            self.mp = mp
            self.face_detector = mp.tasks.vision.FaceDetector.create_from_options(
                mp.tasks.vision.FaceDetectorOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=self.config.face_model),
                    running_mode=mp.tasks.vision.RunningMode.VIDEO,
                    min_detection_confidence=0.6))
            if self.want_hands:
                opts = mp.tasks.vision.HandLandmarkerOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=self.config.hand_model),
                    running_mode=mp.tasks.vision.RunningMode.VIDEO,
                    num_hands=self.config.max_hands, min_hand_detection_confidence=0.65,
                    min_hand_presence_confidence=0.65)
                self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(opts)
        except BaseException:
            self.close()
            raise
        return self

    def capture(self) -> Frame:
        request = self.cam.capture_request()
        try:
            metadata = request.get_metadata()
            captured_at = time.monotonic()
            rgb = request.make_array("main")
            outputs = self.imx500.get_outputs(metadata, add_batch=True)
            detections = parse_ssd(outputs, self.intrinsics, self.imx500,
                                   metadata, self.cam, self.config.person_threshold)
        finally:
            request.release()
        hands: list[list[Point]] = []
        timestamp_ms = max(self._last_timestamp_ms + 1, int(captured_at * 1000))
        self._last_timestamp_ms = timestamp_ms
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.face_detector.detect_for_video(mp_image, timestamp_ms)
        faces = [Box(float(d.bounding_box.origin_x), float(d.bounding_box.origin_y),
                     float(d.bounding_box.width), float(d.bounding_box.height))
                 for d in result.detections]
        if self.landmarker is not None:
            result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
            hands = [[Point(float(p.x), float(p.y), float(p.z)) for p in hand]
                     for hand in result.hand_landmarks]
        return Frame(rgb, detections, hands, captured_at, faces)

    def close(self) -> None:
        try:
            if self.landmarker is not None:
                self.landmarker.close()
                self.landmarker = None
        finally:
            try:
                if self.face_detector is not None:
                    self.face_detector.close()
                    self.face_detector = None
            finally:
                if self.cam is not None:
                    try:
                        self.cam.stop()
                    finally:
                        self.cam.close()
                        self.cam = None

    def __exit__(self, *_: object) -> None:
        self.close()
