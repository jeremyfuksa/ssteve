import { useState, useEffect } from 'react';

interface TelemetryValueProps {
  label: string;
  value: string;
  unit?: string;
  type?: 'snr' | 'rms' | 'peak';
  reactive?: boolean;
}

export function TelemetryValue({ label, value, unit, type, reactive = true }: TelemetryValueProps) {
  const [shouldFlash, setShouldFlash] = useState(false);
  const [shouldShake, setShouldShake] = useState(false);

  // Parse numeric value
  const numericValue = parseFloat(value);

  useEffect(() => {
    if (!reactive) return;

    // SNR warnings: flash red if below 12 dB
    if (type === 'snr' && numericValue < 12) {
      setShouldFlash(true);
      const timer = setTimeout(() => setShouldFlash(false), 200);
      return () => clearTimeout(timer);
    }

    // RMS warnings: shake if exceeds 85%
    if (type === 'rms' && numericValue > 85) {
      setShouldShake(true);
      const timer = setTimeout(() => setShouldShake(false), 100);
      return () => clearTimeout(timer);
    }
  }, [value, type, numericValue, reactive]);

  return (
    <div className="flex justify-between items-baseline">
      <span className="text-xs text-neutral-400">{label}</span>
      <span 
        className={`text-sm tabular-nums transition-all ${
          type === 'snr' && numericValue < 12 
            ? shouldFlash ? 'text-danger-500' : 'text-warning-500'
            : type === 'rms' && numericValue > 85
            ? 'text-warning-500'
            : type === 'peak' && numericValue >= 100
            ? 'text-danger-500'
            : 'text-success-500'
        }`}
        style={{
          transform: shouldShake ? 'translateX(2px)' : 'translateX(0)',
          transition: shouldFlash ? 'color 200ms' : shouldShake ? 'transform 100ms' : 'color 300ms'
        }}
      >
        {value} {unit}
      </span>
    </div>
  );
}
