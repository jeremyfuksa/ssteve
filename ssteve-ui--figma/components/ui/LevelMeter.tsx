// TODO: Wire to Tauri audio API
interface AudioLevelProps {
  leftChannel: number; // 0-100
  rightChannel: number; // 0-100
  peakHold?: number;
}

interface LevelMeterProps {
  levels: AudioLevelProps;
  label?: string;
}

interface SegmentState {
  active: boolean;
  peak: boolean;
}

export function LevelMeter({ levels, label }: LevelMeterProps) {
  // Ballistic behavior: segments stay lit briefly after signal drops
  // Simulating attack/decay like analog VU meters
  const getSegmentStates = (level: number): SegmentState[] => {
    return Array.from({ length: 20 }).map((_, i) => {
      const threshold = (i + 1) * 5;
      return {
        active: level >= threshold,
        peak: level >= 95 && threshold >= 95, // Peak hold indicator
      };
    });
  };

  const getBarColor = (threshold: number, isActive: boolean, isPeak: boolean) => {
    if (!isActive) return 'bg-neutral-800';
    if (isPeak) return 'bg-danger-500 shadow-[0_0_4px_rgba(231,83,81,0.5)]';
    if (threshold >= 90) return 'bg-danger-500';
    if (threshold >= 75) return 'bg-warning-500';
    return 'bg-success-500';
  };

  return (
    <div>
      {label && <div className="text-xs text-neutral-400 mb-2">{label}</div>}
      
      {/* Left Channel */}
      <div className="flex items-center gap-2 h-6">
        <span className="text-xs text-neutral-500 w-6">L</span>
        <div 
          className="flex-1 bg-neutral-900 rounded-sm h-2 overflow-hidden"
          role="meter"
          aria-valuenow={levels.leftChannel}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Left channel input level"
        >
          <div className="h-full flex gap-px">
            {getSegmentStates(levels.leftChannel).map((segment, i) => {
              const threshold = (i + 1) * 5;
              const color = getBarColor(threshold, segment.active, segment.peak);
              
              return (
                <div 
                  key={i} 
                  className={`flex-1 ${color}`}
                  style={{
                    transition: segment.active 
                      ? 'background-color 75ms cubic-bezier(0.4, 0.0, 1, 1), transform 100ms cubic-bezier(0.34, 1.56, 0.64, 1)' 
                      : 'background-color 600ms cubic-bezier(0.0, 0.0, 0.2, 1), transform 100ms ease-out',
                    transform: segment.peak ? 'scaleY(1.2)' : 'scaleY(1)',
                    transformOrigin: 'center'
                  }}
                />
              );
            })}
          </div>
        </div>
        <span className="text-xs text-neutral-400 w-12 text-right tabular-nums">
          {levels.leftChannel}%
        </span>
      </div>

      {/* Right Channel */}
      <div className="flex items-center gap-2 h-6">
        <span className="text-xs text-neutral-500 w-6">R</span>
        <div 
          className="flex-1 bg-neutral-900 rounded-sm h-2 overflow-hidden"
          role="meter"
          aria-valuenow={levels.rightChannel}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Right channel input level"
        >
          <div className="h-full flex gap-px">
            {getSegmentStates(levels.rightChannel).map((segment, i) => {
              const threshold = (i + 1) * 5;
              const color = getBarColor(threshold, segment.active, segment.peak);
              
              return (
                <div 
                  key={i} 
                  className={`flex-1 ${color}`}
                  style={{
                    transition: segment.active 
                      ? 'background-color 75ms cubic-bezier(0.4, 0.0, 1, 1), transform 100ms cubic-bezier(0.34, 1.56, 0.64, 1)' 
                      : 'background-color 600ms cubic-bezier(0.0, 0.0, 0.2, 1), transform 100ms ease-out',
                    transform: segment.peak ? 'scaleY(1.2)' : 'scaleY(1)',
                    transformOrigin: 'center'
                  }}
                />
              );
            })}
          </div>
        </div>
        <span className="text-xs text-neutral-400 w-12 text-right tabular-nums">
          {levels.rightChannel}%
        </span>
      </div>
    </div>
  );
}