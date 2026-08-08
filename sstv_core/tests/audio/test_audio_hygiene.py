"""Audio-pipeline hygiene regressions from the 2026-08-07 audit.

Covers: ring-buffer overflow is surfaced (not silent timeline corruption),
duplicate hardware gets addressable device IDs, the bandpass filter no
longer injects "dither"/DC, and importing dsp_manager cannot touch
PortAudio.
"""

from __future__ import annotations

import numpy as np

from sstv_core.audio.bandpass_filter import BandpassConfig, SSTVBandpassFilter
from sstv_core.audio.ring_buffer import AudioRingBuffer


class TestRingBufferOverflow:
    def test_overflow_is_counted_not_silent(self):
        buffer = AudioRingBuffer(max_samples=100)
        buffer.add(np.zeros(80))
        assert buffer.dropped_samples == 0
        buffer.add(np.zeros(50))  # 30 over capacity
        assert buffer.dropped_samples == 30
        buffer.add(np.zeros(100))  # everything evicts
        assert buffer.dropped_samples == 130

    def test_clear_resets_drop_counter(self):
        buffer = AudioRingBuffer(max_samples=10)
        buffer.add(np.zeros(25))
        assert buffer.dropped_samples == 15
        buffer.clear()
        assert buffer.dropped_samples == 0


class TestDeviceIdCollisions:
    def test_duplicate_hardware_gets_distinct_addressable_ids(self, monkeypatch):
        """Two identical USB codecs (the normal rig setup) must not shadow
        each other, and each ID must resolve to its own device index."""
        import sstv_core.audio.device_manager as dm

        devices = [
            {"name": "USB Audio CODEC", "hostapi": 0, "max_input_channels": 1,
             "max_output_channels": 0, "default_samplerate": 48000.0},
            {"name": "USB Audio CODEC", "hostapi": 0, "max_input_channels": 1,
             "max_output_channels": 0, "default_samplerate": 48000.0},
        ]
        monkeypatch.setattr(dm.sd, "query_devices", lambda *a, **k: devices)
        monkeypatch.setattr(dm.sd, "query_hostapis", lambda: [{"name": "Core Audio"}])
        monkeypatch.setattr(
            dm.sd, "default", type("D", (), {"device": (0, None)})()
        )
        monkeypatch.setattr(dm.platform, "system", lambda: "Darwin")

        manager = dm.AudioDeviceManager(probe_sample_rates=False)
        ids = [d.id for d in manager.list_all_devices()]
        assert len(ids) == len(set(ids)), f"colliding IDs: {ids}"
        indexes = {manager.get_device_index(device_id) for device_id in ids}
        assert indexes == {0, 1}, f"IDs must map to distinct devices: {indexes}"


class TestBandpassNoDither:
    def test_filter_output_is_deterministic(self):
        """The old dither step added random noise per call, so filtering the
        same input twice gave different output."""
        config = BandpassConfig(sample_rate=48000)
        samples = np.sin(
            2 * np.pi * 1900.0 * np.arange(48000) / 48000
        ).astype(np.float32)
        a = SSTVBandpassFilter(config).filter(samples)
        b = SSTVBandpassFilter(config).filter(samples)
        np.testing.assert_array_equal(a, b)

    def test_dc_offset_is_actually_removed(self):
        """The old 'dither removal' re-injected the input's DC offset --
        the one thing a bandpass exists to remove."""
        config = BandpassConfig(sample_rate=48000)
        tone = np.sin(2 * np.pi * 1900.0 * np.arange(48000) / 48000)
        with_dc = (tone + 0.25).astype(np.float32)
        filtered = SSTVBandpassFilter(config).filter(with_dc)
        # Ignore filtfilt edge transients.
        assert abs(float(np.mean(filtered[2000:-2000]))) < 1e-3


class TestLazyHardwareInit:
    def test_dsp_manager_construction_does_not_query_devices(self, monkeypatch):
        """Constructing DSPManager (a module-level singleton) must not touch
        PortAudio; on a headless box that made the import itself fail."""
        import sstv_core.api.dsp_manager as dsp_module

        def explode(*args, **kwargs):
            raise RuntimeError("PortAudio touched at construction time")

        monkeypatch.setattr(dsp_module, "AudioDeviceManager", explode)
        manager = dsp_module.DSPManager()  # must not raise
        assert manager._device_manager_instance is None
