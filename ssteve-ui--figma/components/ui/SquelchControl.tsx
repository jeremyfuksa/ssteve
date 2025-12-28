interface SquelchControlProps {
  level: number;
  onChange: (level: number) => void;
  currentRMS: number;
  isOpen: boolean;
}

export function SquelchControl({ level, onChange, currentRMS, isOpen }: SquelchControlProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-neutral-300">Squelch</label>
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${
          isOpen ? 'bg-success-500/20 text-success-500' : 'bg-neutral-700 text-neutral-400'
        }`}>
          {isOpen ? 'OPEN' : 'CLOSED'}
        </span>
      </div>

      <div className="relative">
        <input
          type="range"
          min={-60}
          max={0}
          step={1}
          value={level}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer slider-squelch"
        />
        <div className="flex justify-between text-xs text-neutral-500 mt-1">
          <span>-60 dB</span>
          <span>-30 dB</span>
          <span>0 dB</span>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs bg-neutral-800 rounded px-3 py-2">
        <span className="text-neutral-400">Threshold:</span>
        <span className="font-medium text-neutral-300 tabular-nums">{level} dB</span>
      </div>

      {/* Visual level indicator */}
      <div className="relative h-2 bg-neutral-800 rounded-full overflow-hidden">
        <div 
          className={`absolute left-0 top-0 h-full transition-all ${
            isOpen ? 'bg-success-500' : 'bg-neutral-600'
          }`}
          style={{ width: `${Math.min(100, (currentRMS / 100) * 100)}%` }}
        />
        <div 
          className="absolute top-0 h-full w-0.5 bg-warning-500"
          style={{ left: `${((level + 60) / 60) * 100}%` }}
        />
      </div>

      <style>{`
        .slider-squelch::-webkit-slider-thumb {
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: ${isOpen ? 'rgb(120, 176, 120)' : 'rgb(96, 122, 151)'};
          cursor: pointer;
          transition: all 200ms ease;
        }
        
        .slider-squelch::-webkit-slider-thumb:hover {
          transform: scale(1.2);
        }

        .slider-squelch::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border: none;
          border-radius: 50%;
          background: ${isOpen ? 'rgb(120, 176, 120)' : 'rgb(96, 122, 151)'};
          cursor: pointer;
          transition: all 200ms ease;
        }

        .slider-squelch::-moz-range-thumb:hover {
          transform: scale(1.2);
        }
      `}</style>
    </div>
  );
}
