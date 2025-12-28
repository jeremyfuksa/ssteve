import { X } from 'lucide-react';
import { useEffect } from 'react';

export type PaletteMode = 'cool' | 'warm' | 'field';
export type MotionSensitivity = 'full' | 'reduced' | 'minimal';
export type FocusIntensity = 'standard' | 'enhanced';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: {
    paletteMode: PaletteMode;
    motionSensitivity: MotionSensitivity;
    telemetryReactive: boolean;
    focusIntensity: FocusIntensity;
  };
  onSettingsChange: (settings: {
    paletteMode?: PaletteMode;
    motionSensitivity?: MotionSensitivity;
    telemetryReactive?: boolean;
    focusIntensity?: FocusIntensity;
  }) => void;
}

export function SettingsModal({ isOpen, onClose, settings, onSettingsChange }: SettingsModalProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-neutral-950/90 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-neutral-900 border-2 border-primary-600/30 rounded-lg w-full max-w-2xl mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-neutral-800">
          <div>
            <h2 className="font-medium text-neutral-100">Settings</h2>
            <p className="text-sm text-neutral-400 mt-1">Customize your operating environment</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5 transition-all focus:outline-none focus:ring-3 focus:ring-primary-500 focus:shadow-[0_0_0_4px_rgba(96,122,151,0.3)]"
            aria-label="Close settings"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 grid grid-cols-2 gap-6">
          {/* Palette Mode */}
          <section>
            <h3 className="font-medium text-neutral-200 mb-3">Palette Mode</h3>
            <p className="text-sm text-neutral-400 mb-4">
              Adjust color temperature for extended operating sessions. Warm mode reduces blue light and adds sepia tones.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => onSettingsChange({ paletteMode: 'cool' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.paletteMode === 'cool'
                    ? 'border-primary-600 bg-primary-600/10 text-primary-300 scale-[0.98] shadow-[0_0_0_4px_rgba(96,122,151,0.2)]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-primary-500 focus:shadow-[0_0_0_4px_rgba(96,122,151,0.3)]`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Cool (Default)</div>
                <div className="text-xs opacity-75 mt-1">Blue-gray slate tones</div>
              </button>
              <button
                onClick={() => onSettingsChange({ paletteMode: 'warm' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.paletteMode === 'warm'
                    ? 'border-secondary-600 bg-secondary-600/10 text-secondary-300 scale-[0.98] shadow-[0_0_0_4px_rgba(168,101,79,0.2)]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-secondary-500 focus:shadow-[0_0_0_4px_rgba(168,101,79,0.3)]`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Warm</div>
                <div className="text-xs opacity-75 mt-1">Sepia earth tones</div>
              </button>
              <button
                onClick={() => onSettingsChange({ paletteMode: 'field' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.paletteMode === 'field'
                    ? 'border-secondary-600 bg-secondary-600/10 text-secondary-300 scale-[0.98] shadow-[0_0_0_4px_rgba(168,101,79,0.2)]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-secondary-500 focus:shadow-[0_0_0_4px_rgba(168,101,79,0.3)]`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Field</div>
                <div className="text-xs opacity-75 mt-1">High contrast tones</div>
              </button>
            </div>
          </section>

          {/* Motion Sensitivity */}
          <section>
            <h3 className="font-medium text-neutral-200 mb-3">Motion & Animation</h3>
            <p className="text-sm text-neutral-400 mb-4">
              Control animation intensity. Reduce motion during long sessions to minimize eye fatigue.
            </p>
            <div className="grid grid-cols-3 gap-3">
              <button
                onClick={() => onSettingsChange({ motionSensitivity: 'full' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.motionSensitivity === 'full'
                    ? 'border-primary-600 bg-primary-600/10 text-primary-300 scale-[0.98]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-primary-500`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Full</div>
                <div className="text-xs opacity-75 mt-1">All effects</div>
              </button>
              <button
                onClick={() => onSettingsChange({ motionSensitivity: 'reduced' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.motionSensitivity === 'reduced'
                    ? 'border-primary-600 bg-primary-600/10 text-primary-300 scale-[0.98]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-primary-500`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Reduced</div>
                <div className="text-xs opacity-75 mt-1">Essential only</div>
              </button>
              <button
                onClick={() => onSettingsChange({ motionSensitivity: 'minimal' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.motionSensitivity === 'minimal'
                    ? 'border-primary-600 bg-primary-600/10 text-primary-300 scale-[0.98]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-primary-500`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Minimal</div>
                <div className="text-xs opacity-75 mt-1">Static</div>
              </button>
            </div>
          </section>

          {/* Focus Intensity */}
          <section>
            <h3 className="font-medium text-neutral-200 mb-3">Focus Indicators</h3>
            <p className="text-sm text-neutral-400 mb-4">
              Enhance keyboard navigation visibility for power users who operate primarily via shortcuts.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => onSettingsChange({ focusIntensity: 'standard' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.focusIntensity === 'standard'
                    ? 'border-primary-600 bg-primary-600/10 text-primary-300 scale-[0.98]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-primary-500`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Standard</div>
                <div className="text-xs opacity-75 mt-1">Subtle rings</div>
              </button>
              <button
                onClick={() => onSettingsChange({ focusIntensity: 'enhanced' })}
                className={`px-4 py-3 rounded-lg border-2 transition-all ${
                  settings.focusIntensity === 'enhanced'
                    ? 'border-primary-600 bg-primary-600/10 text-primary-300 scale-[0.98]'
                    : 'border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:-translate-y-0.5'
                } focus:outline-none focus:ring-3 focus:ring-primary-500`}
                style={{
                  transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <div className="font-medium">Enhanced</div>
                <div className="text-xs opacity-75 mt-1">Glowing rings</div>
              </button>
            </div>
          </section>

          {/* Telemetry Reactivity */}
          <section>
            <h3 className="font-medium text-neutral-200 mb-3">Telemetry Behavior</h3>
            <p className="text-sm text-neutral-400 mb-4">
              Enable reactive telemetry warnings (flickers, shakes) when signal conditions change.
            </p>
            <label className="flex items-center gap-3 px-4 py-3 rounded-lg bg-neutral-800 hover:bg-neutral-750 transition-all cursor-pointer">
              <input
                type="checkbox"
                checked={settings.telemetryReactive}
                onChange={(e) => onSettingsChange({ telemetryReactive: e.target.checked })}
                className="w-5 h-5 rounded border-2 border-neutral-600 bg-neutral-900 checked:bg-primary-600 checked:border-primary-600 focus:ring-3 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-800 transition-all cursor-pointer"
              />
              <div>
                <div className="font-medium text-neutral-200">Reactive Telemetry</div>
                <div className="text-xs text-neutral-400 mt-0.5">
                  Flash warnings on poor SNR, shake on high RMS, glow on peak clipping
                </div>
              </div>
            </label>
          </section>

          {/* Storage Settings */}
          <section>
            <h3 className="font-medium text-neutral-200 mb-3">Image Storage</h3>
            <div className="space-y-3">
              <label className="flex items-center gap-3 px-4 py-3 rounded-lg bg-neutral-800 hover:bg-neutral-750 transition-all cursor-pointer">
                <input
                  type="checkbox"
                  defaultChecked={true}
                  className="w-5 h-5 rounded border-2 border-neutral-600 bg-neutral-900 checked:bg-primary-600 checked:border-primary-600 focus:ring-3 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-800 transition-all cursor-pointer"
                />
                <div>
                  <div className="font-medium text-neutral-200">Auto-Save Received Images</div>
                  <div className="text-xs text-neutral-400 mt-0.5">
                    Automatically save all successfully decoded images
                  </div>
                </div>
              </label>

              <div className="px-4 py-3 bg-neutral-800 rounded-lg">
                <label className="text-xs text-neutral-400 block mb-2">Default Format</label>
                <select className="w-full px-3 py-2 bg-neutral-900 text-neutral-100 rounded border border-neutral-700 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500">
                  <option value="png">PNG (Lossless)</option>
                  <option value="jpeg">JPEG (Compressed)</option>
                  <option value="bmp">BMP (Uncompressed)</option>
                </select>
              </div>

              <div className="px-4 py-3 bg-neutral-800 rounded-lg">
                <label className="text-xs text-neutral-400 block mb-2">Save Location</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    defaultValue="~/Documents/SSTeVe/Received"
                    className="flex-1 px-3 py-2 bg-neutral-900 text-neutral-100 rounded border border-neutral-700 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <button className="px-4 py-2 bg-neutral-700 hover:bg-neutral-600 text-neutral-200 rounded text-sm transition-colors">
                    Browse
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t border-neutral-800">
          <button
            onClick={onClose}
            className="px-6 py-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 hover:-translate-y-0.5 transition-all focus:outline-none focus:ring-3 focus:ring-primary-500 focus:shadow-[0_0_0_4px_rgba(96,122,151,0.3)]"
            style={{
              transition: 'all 200ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
            }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}