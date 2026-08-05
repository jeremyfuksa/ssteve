"""Hough Transform-based slant correction for SSTV images.

Uses Hough Transform to detect and correct horizontal slant in SSTV images.
Provides automatic correction without manual slider adjustment.

Reference: "Hough Transform slant correction: Perfectly straight images
without manual slider. Differentiates from 90% of free market."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from sstv_core.accessibility.slant_detector import SlantErrorData

logger = logging.getLogger(__name__)


@dataclass
class HoughSlantConfig:
    """Configuration for Hough Transform slant correction."""

    # Detection parameters
    canny_threshold1: float = 50.0
    canny_threshold2: float = 150.0
    hough_threshold: int = 30
    hough_min_line_length: int = 50
    hough_max_line_gap: int = 20

    # Correction parameters
    max_correction_angle: float = 15.0  # Maximum correction in degrees
    min_confidence: float = 0.7  # Minimum confidence to apply correction

    # Image parameters
    image_height: int = 256
    image_width: int = 320

    # Processing options
    enable_debug_output: bool = False


@dataclass
class SlantCorrectionResult:
    """Result of slant correction operation."""

    corrected_image: np.ndarray
    slant_angle_degrees: float
    confidence: float
    num_lines_detected: int

    def to_dict(self) -> dict:
        return {
            "slant_angle_degrees": self.slant_angle_degrees,
            "confidence": self.confidence,
            "num_lines_detected": self.num_lines_detected,
        }


class HoughSlantCorrector:
    """Slant correction using Hough Transform.

    Algorithm:
    1. Convert image to grayscale
    2. Apply Canny edge detection
    3. Use Hough Transform to detect lines
    4. Calculate dominant line angle
    5. Rotate image to correct slant
    6. Return corrected image with confidence score

    Advantages over simple sync timing:
    - Detects actual slant from image content
    - Works on partial/corrupted images
    - No dependency on sync pulse timing
    - More accurate for severe slant
    """

    def __init__(self, config: HoughSlantConfig | None = None) -> None:
        """Initialize Hough slant corrector.

        Args:
            config: Correction configuration

        """
        self._config = config or HoughSlantConfig()

    def correct_slant(self, image: np.ndarray) -> SlantCorrectionResult:
        """Detect and correct slant in SSTV image.

        Args:
            image: Input image (RGB or grayscale) as numpy array

        Returns:
            SlantCorrectionResult with corrected image and metadata

        """
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image.copy()

        # Enhance contrast for better edge detection
        gray_enhanced = self._enhance_contrast(gray)

        # Detect edges using Canny
        edges = cv2.Canny(
            gray_enhanced,
            threshold1=self._config.canny_threshold1,
            threshold2=self._config.canny_threshold2,
            apertureSize=3,
        )

        # Detect lines using Hough Transform
        lines = cv2.HoughLinesP(
            edges,
            rho=1,  # Distance resolution (pixels)
            theta=np.pi / 180,  # Angle resolution (radians)
            threshold=self._config.hough_threshold,
            minLineLength=self._config.hough_min_line_length,
            maxLineGap=self._config.hough_max_line_gap,
        )

        # Analyze detected lines
        if lines is None or len(lines) == 0:
            logger.warning("No lines detected by Hough Transform, returning original image")
            return SlantCorrectionResult(
                corrected_image=image,
                slant_angle_degrees=0.0,
                confidence=0.0,
                num_lines_detected=0,
            )

        # Calculate dominant angle
        dominant_angle, confidence = self._calculate_dominant_angle(lines)

        logger.info(
            "Hough detected %d lines, dominant angle: %.2f° (confidence: %.2f)",
            len(lines),
            dominant_angle,
            confidence,
        )

        # Check if correction needed and within bounds
        abs_angle = abs(dominant_angle)
        if abs_angle < 1.0:  # Less than 1 degree - essentially straight
            logger.debug("Slant angle (%.2f°) below correction threshold", abs_angle)
            return SlantCorrectionResult(
                corrected_image=image,
                slant_angle_degrees=dominant_angle,
                confidence=confidence,
                num_lines_detected=len(lines),
            )

        if abs_angle > self._config.max_correction_angle:
            logger.warning(
                "Slant angle (%.2f°) exceeds max correction limit (%.2f°)",
                abs_angle,
                self._config.max_correction_angle,
            )
            dominant_angle = np.clip(
                dominant_angle,
                -self._config.max_correction_angle,
                self._config.max_correction_angle,
            )

        # Rotate image to correct slant
        corrected = self._rotate_image(image, -dominant_angle)

        # Check confidence threshold
        if confidence < self._config.min_confidence:
            logger.warning(
                "Confidence (%.2f) below threshold (%.2f), not applying correction",
                confidence,
                self._config.min_confidence,
            )
            return SlantCorrectionResult(
                corrected_image=image,  # Return original if low confidence
                slant_angle_degrees=dominant_angle,
                confidence=confidence,
                num_lines_detected=len(lines),
            )

        logger.info(
            "Slant correction applied: %.2f° (confidence: %.2f)",
            -dominant_angle,
            confidence,
        )

        return SlantCorrectionResult(
            corrected_image=corrected,
            slant_angle_degrees=dominant_angle,
            confidence=confidence,
            num_lines_detected=len(lines),
        )

    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """Enhance image contrast for better edge detection.

        Uses CLAHE (Contrast Limited Adaptive Histogram Equalization)
        for local contrast enhancement.

        Args:
            image: Grayscale input image

        Returns:
            Contrast-enhanced image

        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)

    def _calculate_dominant_angle(
        self, lines: np.ndarray
    ) -> tuple[float, float]:
        """Calculate dominant line angle from Hough lines.

        Uses weighted averaging based on line length (longer lines = more weight).

        Args:
            lines: Array of lines from cv2.HoughLinesP [[x1, y1, x2, y2]]

        Returns:
            Tuple of (dominant_angle_degrees, confidence_score)

        """
        angles = []
        weights = []

        for line in lines:
            x1, y1, x2, y2 = line[0]

            # Calculate angle of this line
            angle = np.arctan2(y2 - y1, x2 - x1)
            angle_degrees = np.degrees(angle)

            # Normalize angle to [-90, 90] range
            if angle_degrees > 90:
                angle_degrees -= 180

            # Calculate line length as weight
            line_length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

            # Filter out nearly horizontal/vertical lines (likely scanlines, not slant)
            # We want to detect diagonal slant, not scanline edges
            if abs(angle_degrees) < 10 or abs(angle_degrees) > 80:
                continue

            angles.append(angle_degrees)
            weights.append(line_length)

        if not angles:
            # No valid slant lines found
            return 0.0, 0.0

        # Weighted average angle
        angles_arr = np.array(angles)
        weights_arr = np.array(weights)

        # Use weighted mean (longer lines have more influence)
        dominant_angle = np.average(angles_arr, weights=weights_arr)

        # Calculate confidence based on consistency
        # High confidence = most lines have similar angles
        if len(angles_arr) > 1:
            angle_std = np.std(angles_arr)
            # Lower std dev = higher confidence
            # Scale to [0, 1] range
            confidence = max(0.0, 1.0 - (angle_std / 30.0))
        else:
            confidence = 0.5

        return dominant_angle, confidence

    def _rotate_image(
        self, image: np.ndarray, angle_degrees: float
    ) -> np.ndarray:
        """Rotate image by given angle.

        Args:
            image: Input image
            angle_degrees: Rotation angle in degrees (positive = clockwise)

        Returns:
            Rotated image

        """
        # Get image dimensions
        height, width = image.shape[:2]

        # Calculate rotation matrix
        rotation_matrix = cv2.getRotationMatrix2D(
            center=(width / 2, height / 2),
            angle=angle_degrees,
            scale=1.0,
        )

        # Calculate new image dimensions after rotation
        cos_angle = abs(rotation_matrix[0, 0])
        sin_angle = abs(rotation_matrix[0, 1])
        new_width = int((height * sin_angle) + (width * cos_angle))
        new_height = int((height * cos_angle) + (width * sin_angle))

        # Adjust rotation matrix for new dimensions
        rotation_matrix[0, 2] += (new_width - width) / 2
        rotation_matrix[1, 2] += (new_height - height) / 2

        # Rotate image
        rotated = cv2.warpAffine(
            image,
            rotation_matrix,
            (new_width, new_height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )

        # Crop back to original dimensions (center-crop)
        # This handles padding added by warpAffine
        if rotated.shape[0] > height and rotated.shape[1] > width:
            y_start = (rotated.shape[0] - height) // 2
            x_start = (rotated.shape[1] - width) // 2
            cropped = rotated[
                y_start : y_start + height, x_start : x_start + width
            ]
            return cropped
        elif rotated.shape[0] > height:
            y_start = (rotated.shape[0] - height) // 2
            cropped = rotated[y_start : y_start + height, :]
            return cropped
        elif rotated.shape[1] > width:
            x_start = (rotated.shape[1] - width) // 2
            cropped = rotated[:, x_start : x_start + width]
            return cropped
        else:
            # Resize back to original dimensions
            return cv2.resize(rotated, (width, height))

    def estimate_slant_from_edges(
        self, image: np.ndarray
    ) -> SlantErrorData | None:
        """Estimate slant without applying correction.

        Useful for providing slant feedback to user via UI.

        Args:
            image: Input image

        Returns:
            SlantErrorData with measurement, or None if detection failed

        """
        result = self.correct_slant(image)

        # Convert to SlantErrorData format for compatibility
        # Use dominant angle as slant measurement
        return SlantErrorData(
            slant_degrees=result.slant_angle_degrees,
            drift_pixels_per_line=result.slant_angle_degrees / 90.0 * 320.0,  # Approximate
            cumulative_drift_pixels=result.slant_angle_degrees / 90.0 * 256.0,
            confidence=result.confidence,
            measurement_lines=result.num_lines_detected,
        )
