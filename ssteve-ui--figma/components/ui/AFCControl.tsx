interface AFCControlProps {
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
  range: 50 | 100 | 200;
  onRangeChange: (range: 50 | 100 | 200) => void;
  responseTime: 'fast' | 'medium' | 'slow';
  onResponseTimeChange: (time: 'fast' | 'medium' | 'slow') => void;
}

export function AFCControl({ 
  enabled, 
  onEnabledChange, 
  range, 
  onRangeChange,
  responseTime,
  onResponseTimeChange
}: AFCControlProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-neutral-300">AFC (Auto Freq Control)</label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onEnabledChange(e.target.checked)}
            className="w-4 h-4 rounded border-2 border-neutral-600 bg-neutral-900 checked:bg-primary-600 checked:border-primary-600 focus:ring-2 focus:ring-primary-500 transition-all cursor-pointer"
          />
          <span className={`text-xs font-medium ${enabled ? 'text-success-500' : 'text-neutral-500'}`}>
            {enabled ? 'ON' : 'OFF'}
          </span>
        </label>
      </div>

      {enabled && (
        <div className="space-y-3 pl-2 border-l-2 border-primary-600/30">
          <div>
            <label className="text-xs text-neutral-400 block mb-2">Range</label>
            <div className="grid grid-cols-3 gap-2">
              {([50, 100, 200] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => onRangeChange(r)}
                  className={`px-2 py-1 text-xs rounded transition-all ${
                    range === r
                      ? 'bg-primary-600 text-white'
                      : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
                  }`}
                >
                  ±{r} Hz
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-neutral-400 block mb-2">Response</label>
            <div className="grid grid-cols-3 gap-2">
              {(['fast', 'medium', 'slow'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => onResponseTimeChange(t)}
                  className={`px-2 py-1 text-xs rounded capitalize transition-all ${
                    responseTime === t
                      ? 'bg-primary-600 text-white'
                      : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
