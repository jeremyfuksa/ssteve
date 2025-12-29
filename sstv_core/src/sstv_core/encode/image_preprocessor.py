"""Image preprocessing for SSTV transmission."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)


class ResizeMode(Enum):
    FIT = "fit"
    FILL = "fill"
    STRETCH = "stretch"


class ColorSpace(Enum):
    RGB = "rgb"
    YUV = "yuv"


@dataclass
class ModeResolution:
    width: int
    height: int
    aspect_ratio: float

    @classmethod
    def scottie_s1(cls):
        return cls(width=320, height=256, aspect_ratio=320/256)


@dataclass
class PreprocessResult:
    image: np.ndarray
    original_size: tuple
    final_size: tuple
    was_resized: bool
    was_cropped: bool


class ImagePreprocessor:
    def __init__(self, target_resolution: ModeResolution, resize_mode: ResizeMode = ResizeMode.FIT,
                 background_color: tuple = (0, 0, 0), color_space: ColorSpace = ColorSpace.RGB):
        self._resolution = target_resolution
        self._resize_mode = resize_mode
        self._bg_color = background_color
        self._color_space = color_space

    @property
    def target_width(self) -> int:
        return self._resolution.width

    @property
    def target_height(self) -> int:
        return self._resolution.height

    def load_image(self, source: Union[str, Path, np.ndarray]) -> Image.Image:
        if isinstance(source, (str, Path)):
            img = Image.open(source)
        elif isinstance(source, np.ndarray):
            img = Image.fromarray(source.astype(np.uint8) if source.dtype != np.uint8 else source)
        else:
            raise ValueError(f"Unsupported source: {type(source)}")
        return img.convert("RGB") if img.mode != "RGB" else img

    def _resize_fit(self, img: Image.Image):
        orig_ratio = img.width / img.height
        tgt_ratio = self._resolution.aspect_ratio
        if orig_ratio > tgt_ratio:
            new_w, new_h = self._resolution.width, int(self._resolution.width / orig_ratio)
        else:
            new_h, new_w = self._resolution.height, int(self._resolution.height * orig_ratio)
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (self._resolution.width, self._resolution.height), self._bg_color)
        canvas.paste(resized, ((self._resolution.width - new_w) // 2, (self._resolution.height - new_h) // 2))
        return canvas, new_w != img.width or new_h != img.height, False

    def _resize_fill(self, img: Image.Image):
        orig_ratio = img.width / img.height
        tgt_ratio = self._resolution.aspect_ratio
        if orig_ratio > tgt_ratio:
            new_h, new_w = self._resolution.height, int(self._resolution.height * orig_ratio)
        else:
            new_w, new_h = self._resolution.width, int(self._resolution.width / orig_ratio)
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x, y = (new_w - self._resolution.width) // 2, (new_h - self._resolution.height) // 2
        return resized.crop((x, y, x + self._resolution.width, y + self._resolution.height)), True, True

    def _resize_stretch(self, img: Image.Image):
        return img.resize((self._resolution.width, self._resolution.height), Image.Resampling.LANCZOS), True, False

    def process(self, source: Union[str, Path, np.ndarray], enhance_contrast: float = 1.0,
                enhance_saturation: float = 1.0, enhance_sharpness: float = 1.0) -> PreprocessResult:
        img = self.load_image(source)
        orig_size = (img.width, img.height)
        if enhance_contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(enhance_contrast)
        if enhance_saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(enhance_saturation)
        if enhance_sharpness != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(enhance_sharpness)
        if self._resize_mode == ResizeMode.FIT:
            processed, resized, cropped = self._resize_fit(img)
        elif self._resize_mode == ResizeMode.FILL:
            processed, resized, cropped = self._resize_fill(img)
        else:
            processed, resized, cropped = self._resize_stretch(img)
        return PreprocessResult(np.array(processed, dtype=np.uint8), orig_size,
                               (self._resolution.width, self._resolution.height), resized, cropped)

    @classmethod
    def for_scottie_s1(cls, **kwargs):
        return cls(target_resolution=ModeResolution.scottie_s1(), **kwargs)
