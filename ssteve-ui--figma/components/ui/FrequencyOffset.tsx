interface FrequencyOffsetProps {
  value: number;
  onChange: (value: number) => void;
  detectedFreq?: number;
}

export function FrequencyOffset({ value, onChange, detectedFreq = 1200 }: FrequencyOffsetProps) {
  const handleReset = () => {
    onChange(0);
  };

  const displayFreq = detectedFreq + value;
  const isOffNominal = Math.abs(value) > 20;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-neutral-300">Frequency Offset</label>
        <button
          onClick={handleReset}
          className="text-xs text-primary-400 hover:text-primary-300 transition-colors"
        >
          Reset
        </button>
      </div>

      <div className="relative">
        <input
          type="range"
          min={-500}
          max={500}
          step={10}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer slider-offset"
        />
        <div className="flex justify-between text-xs text-neutral-500 mt-1">
          <span>-500 Hz</span>
          <span>0</span>
          <span>+500 Hz</span>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs bg-neutral-800 rounded px-3 py-2">
        <span className="text-neutral-400">Detected:</span>
        <span className={`font-medium tabular-nums ${
          isOffNominal ? 'text-warning-500' : 'text-success-500'
        }`}>
          {displayFreq} Hz {value !== 0 && `(${value > 0 ? '+' : ''}${value} Hz)`}
        </span>
      </div>

      <style>{`
        .slider-offset::-webkit-slider-thumb {
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: ${isOffNominal ? 'rgb(220, 165, 58)' : 'rgb(96, 122, 151)'};
          cursor: pointer;
          transition: all 200ms ease;
        }
        
        .slider-offset::-webkit-slider-thumb:hover {
          transform: scale(1.2);
        }

        .slider-offset::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border: none;
          border-radius: 50%;
          background: ${isOffNominal ? 'rgb(220, 165, 58)' : 'rgb(96, 122, 151)'};
          cursor: pointer;
          transition: all 200ms ease;
        }

        .slider-offset::-moz-range-thumb:hover {
          transform: scale(1.2);
        }
      `}</style>
    </div>
  );
}
