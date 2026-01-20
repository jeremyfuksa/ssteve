# Auto-RSV Signal Report Specification for SSTeVe

## Executive Summary

SSTeVe will automatically calculate **RSV signal reports** (Readability, Signal strength, Video quality) from measured decode metrics, enabling Smart Reply to send accurate, data-driven reports instead of generic "599" rubber stamps.

**Key Benefit:** Honest signal reports improve band conditions awareness and operator skill development, while maintaining one-click Smart Reply convenience.

---

## RSV Format for SSTV

SSTV uses **RSV reports** (not RST):

| Component | Range | Meaning for SSTV |
|-----------|-------|------------------|
| **R** (Readability) | 1-5 | Text legibility (always 5 for valid decode) |
| **S** (Signal strength) | 1-9 | RF signal level (S-meter equivalent) |
| **V** (Video quality) | 1-5 | Image clarity and artifacts |

**Common Reports:**
- **599** - Perfect signal, no noise, crystal clear image
- **595** - Good signal with some noise/artifacts (typical honest report)
- **589** - Moderate signal, noticeable degradation
- **579** - Weak signal, significant noise but readable
- **559** - Very weak, heavy distortion but identifiable

**Operator Practice:** Many give "599" as rubber stamp (especially contests), but experienced operators prefer honest reports for band condition awareness.

---

## Current SSTeVe Metrics

### What SSTeVe Already Measures

**During Decode (`rx_manager.py`, `vis_detector.py`):**

1. **VIS Detection Confidence** (0.0-1.0)
   - Goertzel filter magnitude ratios
   - Parity bit validation
   - Leader tone consistency

2. **Sync Pulse Quality** (planned in scanline decoder)
   - Timing deviation from expected
   - Amplitude consistency
   - Frequency stability (AFC corrections)

3. **Overall RX Quality Score** (0.0-1.0)
   - Currently stored in `SSTVImage.rx_quality_score`
   - Composite metric (implementation TBD)

### What We Can Add

**Signal Level Metrics:**

1. **Peak Signal Amplitude** - Direct audio level measurement
2. **Background Noise Floor** - Measure during silence before VIS
3. **SNR (Signal-to-Noise Ratio)** - Peak amplitude / noise floor (in dB)
4. **Goertzel Magnitude Averages** - Mean filter response across image

**Video Quality Metrics:**

1. **Scanline Decode Confidence** - Per-line quality scores
2. **Sync Pulse Jitter** - Timing consistency (low jitter = high V)
3. **AFC Correction Range** - Frequency drift (stable = high V)
4. **Slant Correction Applied** - Timing skew (none = high V)

---

## RSV Calculation Algorithm

### Input: Measured Decode Metrics

```python
@dataclass
class DecodeMetrics:
    """Raw measurements collected during SSTV decode."""

    # Signal level measurements
    peak_amplitude: float           # 0.0-1.0 (normalized audio level)
    noise_floor: float              # 0.0-1.0 (measured before VIS)
    snr_db: float                   # Calculated: 20*log10(peak/noise)

    # VIS detection quality
    vis_confidence: float           # 0.0-1.0 from Goertzel filters
    vis_parity_valid: bool          # VIS checksum passed

    # Sync/timing quality
    sync_pulse_jitter_ms: float     # Standard deviation of sync timing
    afc_correction_hz: float        # Total frequency offset corrected
    slant_correction_applied: bool  # Did we need slant fix?

    # Scanline decode quality
    scanline_confidences: list[float]  # Per-line quality (0.0-1.0)
    mean_scanline_quality: float       # Average across image

    # Overall composite
    rx_quality_score: float         # 0.0-1.0 (legacy field, computed)
```

### Output: RSV Report

```python
@dataclass
class RSVReport:
    """SSTV signal report (Readability, Signal, Video)."""

    readability: int    # 1-5 (typically 5 if decoded)
    signal: int         # 1-9 (S-meter equivalent)
    video: int          # 1-5 (image quality)

    # Supporting data for UI display
    snr_db: float              # Raw SNR measurement
    signal_description: str    # "Strong signal, no noise"
    confidence: float          # 0.0-1.0 (how certain are we?)

    def to_string(self) -> str:
        """Format as '595' string."""
        return f"{self.readability}{self.signal}{self.video}"

    def to_dict(self) -> dict:
        """For JSON API responses."""
        return {
            "rsv": self.to_string(),
            "readability": self.readability,
            "signal": self.signal,
            "video": self.video,
            "snr_db": round(self.snr_db, 1),
            "description": self.signal_description,
            "confidence": round(self.confidence, 2)
        }
```

### Calculation Logic

```python
class RSVCalculator:
    """Converts decode metrics to RSV signal report."""

    def calculate(self, metrics: DecodeMetrics) -> RSVReport:
        """
        Calculate RSV from measured decode metrics.

        Strategy:
        - R (Readability): Always 5 if we decoded successfully
        - S (Signal): Map SNR to S-units (1-9 scale)
        - V (Video): Combine sync quality + scanline quality
        """

        # R = Readability (text legibility)
        # For SSTV: If we decoded VIS and got an image, readability = 5
        # Only reduce if VIS parity invalid or major decode failures
        readability = self._calculate_readability(metrics)

        # S = Signal Strength (RF level, S-meter equivalent)
        # Map SNR (dB) to S-units (1-9)
        signal = self._calculate_signal_strength(metrics)

        # V = Video Quality (image clarity)
        # Combine sync timing, AFC stability, scanline quality
        video = self._calculate_video_quality(metrics)

        # Generate human-readable description
        description = self._generate_description(signal, video, metrics.snr_db)

        # Confidence score (how certain are we of this report?)
        confidence = self._calculate_confidence(metrics)

        return RSVReport(
            readability=readability,
            signal=signal,
            video=video,
            snr_db=metrics.snr_db,
            signal_description=description,
            confidence=confidence
        )

    def _calculate_readability(self, metrics: DecodeMetrics) -> int:
        """
        Calculate R (Readability) from VIS and decode success.

        In SSTV, readability typically means "can we identify the mode
        and decode the image structure?" For most successful decodes,
        this will be 5.
        """
        if not metrics.vis_parity_valid:
            return 4  # VIS detected but checksum failed

        if metrics.rx_quality_score < 0.3:
            return 3  # Severely degraded but still decoded

        return 5  # Clean decode

    def _calculate_signal_strength(self, metrics: DecodeMetrics) -> int:
        """
        Calculate S (Signal strength) from SNR.

        S-meter scale approximation:
        - S9: SNR >= 20 dB (very strong)
        - S8: SNR >= 17 dB
        - S7: SNR >= 14 dB
        - S6: SNR >= 11 dB
        - S5: SNR >= 8 dB
        - S4: SNR >= 5 dB
        - S3: SNR >= 2 dB
        - S2: SNR >= -1 dB
        - S1: SNR < -1 dB (barely readable)

        Based on typical SSTV signal levels at 1500-2300 Hz.
        """
        snr = metrics.snr_db

        if snr >= 20:
            return 9
        elif snr >= 17:
            return 8
        elif snr >= 14:
            return 7
        elif snr >= 11:
            return 6
        elif snr >= 8:
            return 5
        elif snr >= 5:
            return 4
        elif snr >= 2:
            return 3
        elif snr >= -1:
            return 2
        else:
            return 1

    def _calculate_video_quality(self, metrics: DecodeMetrics) -> int:
        """
        Calculate V (Video quality) from sync timing and scanline quality.

        Video quality reflects image clarity, noise, and artifacts.

        Factors:
        - Sync pulse timing consistency (jitter)
        - Scanline decode quality (mean confidence)
        - AFC corrections needed (frequency stability)
        - Slant correction applied (timing skew)
        """

        # Start with scanline quality as base
        base_quality = metrics.mean_scanline_quality  # 0.0-1.0

        # Penalize for sync jitter (timing instability)
        if metrics.sync_pulse_jitter_ms > 5.0:
            base_quality *= 0.7  # Heavy jitter → 30% penalty
        elif metrics.sync_pulse_jitter_ms > 2.0:
            base_quality *= 0.85  # Moderate jitter → 15% penalty

        # Penalize for large AFC corrections (frequency drift)
        if abs(metrics.afc_correction_hz) > 50:
            base_quality *= 0.8  # Large drift → 20% penalty
        elif abs(metrics.afc_correction_hz) > 20:
            base_quality *= 0.9  # Moderate drift → 10% penalty

        # Penalize for slant correction (timing skew)
        if metrics.slant_correction_applied:
            base_quality *= 0.9  # Needed slant fix → 10% penalty

        # Map 0.0-1.0 quality to 1-5 V scale
        if base_quality >= 0.9:
            return 5  # Excellent video
        elif base_quality >= 0.75:
            return 4  # Good video
        elif base_quality >= 0.55:
            return 3  # Fair video
        elif base_quality >= 0.35:
            return 2  # Poor video
        else:
            return 1  # Very poor video

    def _generate_description(self, signal: int, video: int, snr_db: float) -> str:
        """Generate human-readable signal description."""

        signal_desc = {
            9: "Very strong",
            8: "Strong",
            7: "Good",
            6: "Moderate",
            5: "Fair",
            4: "Weak",
            3: "Very weak",
            2: "Barely readable",
            1: "Extremely weak"
        }[signal]

        video_desc = {
            5: "crystal clear image",
            4: "clear image with minor noise",
            3: "noticeable noise and artifacts",
            2: "heavy distortion but recognizable",
            1: "severe degradation"
        }[video]

        return f"{signal_desc} signal ({snr_db:.1f} dB), {video_desc}"

    def _calculate_confidence(self, metrics: DecodeMetrics) -> float:
        """
        Calculate confidence in RSV report (0.0-1.0).

        High confidence when:
        - VIS parity valid
        - High VIS detection confidence
        - Consistent scanline quality
        - Low sync jitter

        Low confidence when:
        - Marginal VIS detection
        - High variance in scanline quality
        - Severe timing issues
        """
        confidence = 1.0

        # Reduce for VIS issues
        if not metrics.vis_parity_valid:
            confidence *= 0.7
        elif metrics.vis_confidence < 0.7:
            confidence *= 0.85

        # Reduce for inconsistent scanlines
        if len(metrics.scanline_confidences) > 0:
            scanline_variance = np.var(metrics.scanline_confidences)
            if scanline_variance > 0.1:
                confidence *= 0.9

        # Reduce for severe timing issues
        if metrics.sync_pulse_jitter_ms > 10:
            confidence *= 0.8

        return max(0.0, min(1.0, confidence))
```

---

## Database Schema Updates

### New Fields in `SSTVImage` Table

```python
class SSTVImage(Base):
    __tablename__ = "sstv_images"

    # ... existing fields ...

    # Legacy quality score (keep for backward compatibility)
    rx_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # NEW: Detailed signal metrics
    rx_snr_db: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Signal-to-noise ratio in dB"
    )

    rx_peak_amplitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Peak audio signal level (0.0-1.0)"
    )

    rx_noise_floor: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Background noise level (0.0-1.0)"
    )

    # NEW: RSV report components
    rsv_readability: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="RSV Readability (1-5)"
    )

    rsv_signal: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="RSV Signal strength (1-9, S-meter equivalent)"
    )

    rsv_video: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="RSV Video quality (1-5)"
    )

    rsv_report: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
        comment="Formatted RSV report (e.g., '595')"
    )

    # NEW: Detailed decode metrics (JSON for flexibility)
    decode_metrics_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full DecodeMetrics as JSON for analysis"
    )

    # Index for signal strength queries
    __table_args__ = (
        # ... existing indexes ...
        Index("idx_images_rsv_signal", "rsv_signal"),
        Index("idx_images_snr", "rx_snr_db"),
    )
```

### Migration Script

```python
# sstv_core/database/migrations/versions/add_rsv_metrics.py

from alembic import op
import sqlalchemy as sa

def upgrade():
    """Add RSV signal report fields."""

    # Add signal measurement fields
    op.add_column('sstv_images', sa.Column('rx_snr_db', sa.Float(), nullable=True))
    op.add_column('sstv_images', sa.Column('rx_peak_amplitude', sa.Float(), nullable=True))
    op.add_column('sstv_images', sa.Column('rx_noise_floor', sa.Float(), nullable=True))

    # Add RSV report fields
    op.add_column('sstv_images', sa.Column('rsv_readability', sa.Integer(), nullable=True))
    op.add_column('sstv_images', sa.Column('rsv_signal', sa.Integer(), nullable=True))
    op.add_column('sstv_images', sa.Column('rsv_video', sa.Integer(), nullable=True))
    op.add_column('sstv_images', sa.Column('rsv_report', sa.String(3), nullable=True))

    # Add detailed metrics JSON
    op.add_column('sstv_images', sa.Column('decode_metrics_json', sa.Text(), nullable=True))

    # Create indexes
    op.create_index('idx_images_rsv_signal', 'sstv_images', ['rsv_signal'])
    op.create_index('idx_images_snr', 'sstv_images', ['rx_snr_db'])

def downgrade():
    """Remove RSV fields."""
    op.drop_index('idx_images_snr', table_name='sstv_images')
    op.drop_index('idx_images_rsv_signal', table_name='sstv_images')

    op.drop_column('sstv_images', 'decode_metrics_json')
    op.drop_column('sstv_images', 'rsv_report')
    op.drop_column('sstv_images', 'rsv_video')
    op.drop_column('sstv_images', 'rsv_signal')
    op.drop_column('sstv_images', 'rsv_readability')
    op.drop_column('sstv_images', 'rx_noise_floor')
    op.drop_column('sstv_images', 'rx_peak_amplitude')
    op.drop_column('sstv_images', 'rx_snr_db')
```

---

## Implementation: Signal Measurement

### Measure SNR During Decode

```python
# sstv_core/src/sstv_core/decode/signal_analyzer.py

class SignalAnalyzer:
    """Measures signal metrics during SSTV decode."""

    def __init__(self, sample_rate: int = 48000):
        self._sample_rate = sample_rate
        self._noise_floor = None
        self._peak_amplitude = None
        self._snr_db = None

    def measure_noise_floor(self, silence_buffer: np.ndarray) -> float:
        """
        Measure background noise from silence before VIS.

        Args:
            silence_buffer: Audio samples before VIS detection (500ms+)

        Returns:
            RMS noise level (0.0-1.0)
        """
        # Calculate RMS of noise
        rms_noise = np.sqrt(np.mean(silence_buffer ** 2))
        self._noise_floor = max(rms_noise, 1e-6)  # Avoid division by zero
        return self._noise_floor

    def measure_peak_amplitude(self, signal_buffer: np.ndarray) -> float:
        """
        Measure peak signal amplitude from SSTV image audio.

        Args:
            signal_buffer: Audio samples during image transmission

        Returns:
            Peak amplitude (0.0-1.0)
        """
        # Use 95th percentile instead of absolute max (avoids spikes)
        self._peak_amplitude = np.percentile(np.abs(signal_buffer), 95)
        return self._peak_amplitude

    def calculate_snr(self) -> float:
        """
        Calculate SNR from measured peak and noise floor.

        Returns:
            SNR in dB
        """
        if self._noise_floor is None or self._peak_amplitude is None:
            raise ValueError("Must measure noise floor and peak amplitude first")

        # SNR (dB) = 20 * log10(signal / noise)
        snr_ratio = self._peak_amplitude / self._noise_floor
        self._snr_db = 20 * np.log10(snr_ratio)

        return self._snr_db

    def get_metrics(self) -> dict:
        """Return all measured signal metrics."""
        return {
            "noise_floor": self._noise_floor,
            "peak_amplitude": self._peak_amplitude,
            "snr_db": self._snr_db
        }
```

### Integration with RX Manager

```python
# sstv_core/src/sstv_core/decode/rx_manager.py

class RxManager:
    def __init__(self, ...):
        self.signal_analyzer = SignalAnalyzer(sample_rate)
        self.rsv_calculator = RSVCalculator()
        # ...

    async def decode_audio(self, audio_buffer: np.ndarray):
        # 0. Measure noise floor from silence before VIS
        silence_start = 0
        silence_end = int(self._sample_rate * 0.5)  # First 500ms
        silence_buffer = audio_buffer[silence_start:silence_end]
        noise_floor = self.signal_analyzer.measure_noise_floor(silence_buffer)

        # 1. Detect VIS code
        vis_result = self.vis_detector.detect_from_buffer(audio_buffer)

        # 2. Decode SSTV image scanlines
        mode_params = get_mode_parameters(vis_result.mode)
        image, scanline_metrics = self.scanline_decoder.decode_with_metrics(
            audio_buffer,
            mode_params
        )

        # 3. Measure peak signal amplitude from image portion
        image_start = vis_result.vis_end_sample
        image_end = image_start + int(mode_params.total_duration_ms * self._sample_rate / 1000)
        signal_buffer = audio_buffer[image_start:image_end]
        peak_amplitude = self.signal_analyzer.measure_peak_amplitude(signal_buffer)

        # 4. Calculate SNR
        snr_db = self.signal_analyzer.calculate_snr()

        # 5. Build DecodeMetrics object
        metrics = DecodeMetrics(
            peak_amplitude=peak_amplitude,
            noise_floor=noise_floor,
            snr_db=snr_db,
            vis_confidence=vis_result.confidence,
            vis_parity_valid=vis_result.parity_valid,
            sync_pulse_jitter_ms=scanline_metrics.sync_jitter_ms,
            afc_correction_hz=scanline_metrics.afc_correction_hz,
            slant_correction_applied=scanline_metrics.slant_applied,
            scanline_confidences=scanline_metrics.line_confidences,
            mean_scanline_quality=np.mean(scanline_metrics.line_confidences),
            rx_quality_score=vis_result.confidence * np.mean(scanline_metrics.line_confidences)
        )

        # 6. Calculate RSV report
        rsv_report = self.rsv_calculator.calculate(metrics)

        # 7. Look for FSKID (from previous spec)
        callsign = self.fskid_decoder.decode(audio_buffer[image_end:])

        # 8. Store in database with all metrics
        image_record = self.db.save_image(
            image_data=image,
            mode=vis_result.mode.name,
            callsign=callsign,
            # Legacy field
            rx_quality_score=metrics.rx_quality_score,
            # NEW: Signal measurements
            rx_snr_db=metrics.snr_db,
            rx_peak_amplitude=metrics.peak_amplitude,
            rx_noise_floor=metrics.noise_floor,
            # NEW: RSV report
            rsv_readability=rsv_report.readability,
            rsv_signal=rsv_report.signal,
            rsv_video=rsv_report.video,
            rsv_report=rsv_report.to_string(),
            # NEW: Full metrics JSON
            decode_metrics_json=json.dumps(metrics.__dict__),
            timestamp=datetime.utcnow()
        )

        # 9. Emit WebSocket event with RSV
        await self.websocket.send_json({
            "event": "decode_complete",
            "image_id": image_record.id,
            "mode": vis_result.mode.name,
            "callsign": callsign,
            "fskid_detected": callsign is not None,
            # NEW: RSV report data
            "rsv": rsv_report.to_dict()
        })

        return image_record
```

---

## Smart Reply Integration

### API Enhancement

```python
# sstv_core/src/sstv_core/api/routes/smart_reply.py

@router.get("/smart-reply/prefill/{image_id}")
async def get_smart_reply_prefill(
    image_id: int,
    db: Session = Depends(get_db)
) -> dict:
    """
    Get pre-filled data for Smart Reply modal.

    Returns callsign (from FSKID), calculated RSV report,
    and recent contacts for dropdown.
    """
    image = db.query(SSTVImage).filter(SSTVImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Get recent contacts (last 20 unique callsigns)
    recent_contacts = (
        db.query(RecentContact)
        .order_by(RecentContact.last_contact_utc.desc())
        .limit(20)
        .all()
    )

    # Get user's callsign from config
    config = get_user_config()

    return {
        "received_image_id": image_id,
        "callsign": image.callsign,  # From FSKID (may be None)
        "fskid_detected": image.callsign is not None,
        "rsv_report": image.rsv_report or "595",  # Auto-calculated or default
        "rsv_components": {
            "readability": image.rsv_readability or 5,
            "signal": image.rsv_signal or 9,
            "video": image.rsv_video or 5
        },
        "signal_description": _format_rsv_description(
            image.rsv_signal,
            image.rsv_video,
            image.rx_snr_db
        ),
        "my_callsign": config.operator_callsign,
        "recent_contacts": [
            {
                "callsign": c.callsign,
                "last_contact": c.last_contact_utc.isoformat()
            }
            for c in recent_contacts
        ],
        "default_message": "73!",
        "timestamp": datetime.utcnow().isoformat()
    }

def _format_rsv_description(signal: int, video: int, snr_db: float) -> str:
    """Generate human-readable signal description."""
    if not signal or not video:
        return "Signal report unavailable"

    signal_words = {
        9: "Very strong", 8: "Strong", 7: "Good",
        6: "Moderate", 5: "Fair", 4: "Weak",
        3: "Very weak", 2: "Barely readable", 1: "Extremely weak"
    }

    video_words = {
        5: "crystal clear",
        4: "clear with minor noise",
        3: "noticeable artifacts",
        2: "heavy distortion",
        1: "severe degradation"
    }

    snr_str = f" ({snr_db:.1f} dB)" if snr_db else ""
    return f"{signal_words.get(signal, 'Unknown')} signal{snr_str}, {video_words.get(video, 'unknown')} image"
```

### UI Changes

```tsx
// ssteve-ui--figma/components/TransmitView.tsx

interface SmartReplyPrefill {
  received_image_id: number;
  callsign: string | null;
  fskid_detected: boolean;
  rsv_report: string;  // "595"
  rsv_components: {
    readability: number;
    signal: number;
    video: number;
  };
  signal_description: string;  // "Strong signal (15.3 dB), clear with minor noise"
  my_callsign: string;
  recent_contacts: Array<{ callsign: string; last_contact: string }>;
  default_message: string;
}

const SmartReplyModal: React.FC<{ imageId: number }> = ({ imageId }) => {
  const [prefill, setPrefill] = useState<SmartReplyPrefill | null>(null);
  const [callsign, setCallsign] = useState("");
  const [rsvReport, setRsvReport] = useState("595");
  const [message, setMessage] = useState("73!");

  useEffect(() => {
    // Fetch pre-filled data
    api.getSmartReplyPrefill(imageId).then(data => {
      setPrefill(data);
      setCallsign(data.callsign || "");
      setRsvReport(data.rsv_report);
      setMessage(data.default_message);
    });
  }, [imageId]);

  if (!prefill) return <Spinner />;

  return (
    <Dialog open onClose={onClose}>
      <DialogTitle>Smart Reply</DialogTitle>

      <DialogContent>
        {/* Callsign input with FSKID indicator */}
        <Input
          label="To Callsign"
          value={callsign}
          onChange={setCallsign}
          hint={prefill.fskid_detected
            ? "✓ Auto-detected via FSKID"
            : "Enter callsign manually"}
          leftIcon={prefill.fskid_detected ? <CheckCircle /> : <AlertCircle />}
        />

        {/* RSV Report with auto-calculated indicator */}
        <Input
          label="Signal Report (RSV)"
          value={rsvReport}
          onChange={setRsvReport}
          hint={`Auto-calculated: ${prefill.signal_description}`}
          leftIcon={<BarChart />}
          helperText="R=Readability, S=Signal, V=Video quality"
        />

        {/* Optional: Breakdown display */}
        <div className="text-sm text-gray-400 mt-1">
          R={prefill.rsv_components.readability}
          S={prefill.rsv_components.signal}
          V={prefill.rsv_components.video}
        </div>

        {/* Message */}
        <Textarea
          label="Message"
          value={message}
          onChange={setMessage}
          placeholder="73!"
        />

        {/* Preview image */}
        <div className="mt-4 border border-gray-700 rounded">
          <TransmitPreview
            callsign={callsign}
            rsvReport={rsvReport}
            message={message}
            myCallsign={prefill.my_callsign}
          />
        </div>
      </DialogContent>

      <DialogActions>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button onClick={handleTransmit}>Transmit</Button>
      </DialogActions>
    </Dialog>
  );
};
```

---

## User Configuration

Add settings for RSV behavior:

```python
# sstv_core/src/sstv_core/config/settings.py

class SmartReplyConfig(BaseModel):
    """Configuration for Smart Reply system."""

    # Auto-calculate RSV from decode metrics
    auto_calculate_rsv: bool = True

    # Default RSV when auto-calculation unavailable
    default_rsv: str = "595"

    # Allow user to override auto-calculated RSV
    allow_rsv_override: bool = True

    # Conservative mode: Never report better than measured
    # (avoids inflating reports for weak signals)
    conservative_reporting: bool = True

    # Honest mode: Always use measured RSV (no "599" rubber stamp)
    honest_mode: bool = True
```

---

## Testing Strategy

### Unit Tests

```python
# sstv_core/tests/test_rsv_calculator.py

def test_strong_signal_clean_image():
    """SNR=20dB, perfect sync → 599."""
    metrics = DecodeMetrics(
        snr_db=20.0,
        vis_confidence=0.95,
        vis_parity_valid=True,
        sync_pulse_jitter_ms=0.5,
        afc_correction_hz=5.0,
        slant_correction_applied=False,
        mean_scanline_quality=0.95,
        scanline_confidences=[0.95] * 128,
        rx_quality_score=0.90,
        peak_amplitude=0.8,
        noise_floor=0.08
    )

    calc = RSVCalculator()
    rsv = calc.calculate(metrics)

    assert rsv.readability == 5
    assert rsv.signal == 9
    assert rsv.video == 5
    assert rsv.to_string() == "599"

def test_moderate_signal_noisy_image():
    """SNR=12dB, sync jitter, AFC → 573."""
    metrics = DecodeMetrics(
        snr_db=12.0,
        vis_confidence=0.85,
        vis_parity_valid=True,
        sync_pulse_jitter_ms=4.5,
        afc_correction_hz=35.0,
        slant_correction_applied=True,
        mean_scanline_quality=0.60,
        scanline_confidences=[0.60] * 128,
        rx_quality_score=0.51,
        peak_amplitude=0.5,
        noise_floor=0.125
    )

    calc = RSVCalculator()
    rsv = calc.calculate(metrics)

    assert rsv.readability == 5
    assert rsv.signal == 7  # SNR ~12dB → S7
    assert rsv.video == 3   # Fair video quality
    assert rsv.to_string() == "573"

def test_weak_signal_poor_image():
    """SNR=6dB, heavy jitter, slant → 542."""
    metrics = DecodeMetrics(
        snr_db=6.0,
        vis_confidence=0.70,
        vis_parity_valid=True,
        sync_pulse_jitter_ms=8.0,
        afc_correction_hz=60.0,
        slant_correction_applied=True,
        mean_scanline_quality=0.40,
        scanline_confidences=[0.40] * 128,
        rx_quality_score=0.28,
        peak_amplitude=0.3,
        noise_floor=0.15
    )

    calc = RSVCalculator()
    rsv = calc.calculate(metrics)

    assert rsv.readability == 5
    assert rsv.signal == 4  # SNR ~6dB → S4
    assert rsv.video == 2   # Poor video quality
    assert rsv.to_string() == "542"
```

### Integration Tests

```python
def test_smart_reply_uses_calculated_rsv():
    """Smart Reply API returns auto-calculated RSV."""
    # Decode test image with known signal characteristics
    test_audio = load_test_audio("robot36_snr15_moderate_noise.wav")

    # RX Manager decodes and calculates RSV
    rx_manager = RxManager()
    image_record = await rx_manager.decode_audio(test_audio)

    # Smart Reply should use calculated RSV
    response = await client.get(f"/smart-reply/prefill/{image_record.id}")

    assert response.json()["rsv_report"] == "575"  # Expected for this test file
    assert "Strong signal" in response.json()["signal_description"]
```

---

## Success Metrics

**Accuracy Goals:**
- RSV within ±1 S-unit of operator's subjective assessment: >80% of cases
- RSV better predictor of decode quality than legacy `rx_quality_score`: >70% correlation

**User Adoption:**
- % of Smart Reply transmissions using auto-calculated RSV: >90%
- % of users overriding auto-RSV: <20% (indicates good defaults)
- % of "honest mode" users (vs rubber stamp 599): Target >60%

**Band Condition Awareness:**
- Track RSV reports over time → Show propagation trends in UI
- Aggregate S-units by band/time → Visualize sunspot cycle impact

---

## Future Enhancements

**Phase 2: Advanced Analytics**
- Historical SNR trends per callsign (track propagation)
- RSV heatmap by frequency/time (band conditions)
- Automatic antenna tuning suggestions based on S-units

**Phase 3: Contest Mode**
- Contest exchange templates (serial numbers, zones)
- Batch RSV calculation for QSO log import
- ADIF export with accurate RSV in `RST_RCVD` field

---

## References

- [RSV Signal Reports for SSTV](https://wa9tt.com/tutorial/SSTV_signal_report.pdf)
- [R-S-T System (Wikipedia)](https://en.wikipedia.org/wiki/R-S-T_system)
- [Practical Signal Reports (Ham Radio School)](https://www.hamradioschool.com/post/practical-signal-reports)
- [SSTeVe TRANSMIT_SPEC.md](./TRANSMIT_SPEC.md) - Smart Reply context

---

**Document Status:** Complete specification for auto-RSV calculation

**Next Action:** Implement `SignalAnalyzer` and `RSVCalculator` classes, integrate with RX Manager
