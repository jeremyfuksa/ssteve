interface SlantCorrectionProps {
  autoSlant: boolean;
  onAutoSlantChange: (enabled: boolean) => void;
  manualSlant: number;
  onManualSlantChange: (value: number) => void;
  detectedSlant?: number;
}

export function SlantCorrection({ 
  autoSlant, 
  onAutoSlantChange, 
  manualSlant, 
  onManualSlantChange,
  detectedSlant = 0
}: SlantCorrectionProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-neutral-300">Slant Correction</label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={autoSlant}
            onChange={(e) => onAutoSlantChange(e.target.checked)}
            className="w-4 h-4 rounded border-2 border-neutral-600 bg-neutral-900 checked:bg-primary-600 checked:border-primary-600 focus:ring-2 focus:ring-primary-500 transition-all cursor-pointer"
          />
          <span className="text-xs text-neutral-400">Auto</span>
        </label>
      </div>

      {!autoSlant && (
        <div className="relative">
          <input
            type="range"
            min={-10}
            max={10}
            step={0.1}
            value={manualSlant}
            onChange={(e) => onManualSlantChange(Number(e.target.value))}
            className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer slider-slant"
          />
          <div className="flex justify-between text-xs text-neutral-500 mt-1">
            <span>-10</span>
            <span>0</span>
            <span>+10</span>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between text-xs bg-neutral-800 rounded px-3 py-2">
        <span className="text-neutral-400">
          {autoSlant ? 'Detected:' : 'Manual:'}
        </span>
        <span className={`font-medium tabular-nums ${
          Math.abs(autoSlant ? detectedSlant : manualSlant) > 3 
            ? 'text-warning-500' 
            : 'text-success-500'
        }`}>
          {autoSlant ? detectedSlant.toFixed(1) : manualSlant.toFixed(1)} ms/min
        </span>
      </div>

      <style>{`
        .slider-slant::-webkit-slider-thumb {
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: rgb(96, 122, 151);
          cursor: pointer;
          transition: all 200ms ease;
        }
        
        .slider-slant::-webkit-slider-thumb:hover {
          transform: scale(1.2);
        }

        .slider-slant::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border: none;
          border-radius: 50%;
          background: rgb(96, 122, 151);
          cursor: pointer;
          transition: all 200ms ease;
        }

        .slider-slant::-moz-range-thumb:hover {
          transform: scale(1.2);
        }
      `}</style>
    </div>
  );
}
