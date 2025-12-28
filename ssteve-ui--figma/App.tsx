import { useState } from 'react';
import { Radio, Send, BookImage, Settings as SettingsIcon, Activity } from 'lucide-react';
import { CaptureView } from './components/CaptureView';
import { TransmitView } from './components/TransmitView';
import { LogView } from './components/LogView';
import { DevicesView } from './components/DevicesView';
import { SettingsModal, PaletteMode, MotionSensitivity, FocusIntensity } from './components/SettingsModal';

type View = 'capture' | 'transmit' | 'log' | 'devices';
type AppState = 'idle' | 'listening' | 'locked' | 'transmitting' | 'error';

export default function App() {
  const [activeView, setActiveView] = useState<View>('capture');
  const [appState, setAppState] = useState<AppState>('idle');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState({
    paletteMode: 'cool' as PaletteMode,
    motionSensitivity: 'full' as MotionSensitivity,
    telemetryReactive: true,
    focusIntensity: 'enhanced' as FocusIntensity,
  });

  const stateColors: Record<AppState, string> = {
    idle: 'bg-neutral-600',
    listening: 'bg-primary-500',
    locked: 'bg-success-500',
    transmitting: 'bg-secondary-600',
    error: 'bg-danger-500',
  };

  const stateLabels: Record<AppState, string> = {
    idle: 'Idle',
    listening: 'Listening',
    locked: 'Picture locked',
    transmitting: 'TX active',
    error: 'Error',
  };

  const handleSettingsChange = (newSettings: typeof settings) => {
    setSettings(newSettings);
  };

  return (
    <div className={`flex h-screen bg-neutral-950 text-neutral-100 ${settings.paletteMode === 'warm' ? 'warm-mode' : ''} ${settings.paletteMode === 'field' ? 'field-mode' : ''} ${settings.focusIntensity === 'enhanced' ? 'enhanced-focus' : ''} ${settings.motionSensitivity !== 'full' ? `motion-${settings.motionSensitivity}` : ''}`}>
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onSettingsChange={handleSettingsChange}
      />
      
      {/* Left Navigation Sidebar */}
      <aside className="w-20 bg-neutral-900 border-r border-neutral-800 flex flex-col items-center py-6 gap-6">
        <div className="mb-4">
          <div className="w-12 h-12 bg-primary-600 rounded-lg flex items-center justify-center">
            <Radio className="w-7 h-7" />
          </div>
          <div className="text-center text-xs mt-2 tracking-wide font-medium">SSTeVe</div>
        </div>

        <nav className="flex-1 flex flex-col gap-2" role="navigation" aria-label="Main navigation">
          <button
            onClick={() => setActiveView('capture')}
            className={`flex flex-col items-center gap-1 px-3 py-3 rounded-lg transition-all ${
              activeView === 'capture'
                ? 'bg-neutral-800 text-primary-400'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
            } focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900`}
            aria-pressed={activeView === 'capture'}
            aria-label="Capture view"
          >
            <Radio className="w-5 h-5" />
            <span className="text-xs">Capture</span>
          </button>

          <button
            onClick={() => setActiveView('transmit')}
            className={`flex flex-col items-center gap-1 px-3 py-3 rounded-lg transition-all ${
              activeView === 'transmit'
                ? 'bg-neutral-800 text-primary-400'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
            } focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900`}
            aria-pressed={activeView === 'transmit'}
            aria-label="Transmit view"
          >
            <Send className="w-5 h-5" />
            <span className="text-xs">Transmit</span>
          </button>

          <button
            onClick={() => setActiveView('log')}
            className={`flex flex-col items-center gap-1 px-3 py-3 rounded-lg transition-all ${
              activeView === 'log'
                ? 'bg-neutral-800 text-primary-400'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
            } focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900`}
            aria-pressed={activeView === 'log'}
            aria-label="Log view"
          >
            <BookImage className="w-5 h-5" />
            <span className="text-xs">Log</span>
          </button>

          <button
            onClick={() => setActiveView('devices')}
            className={`flex flex-col items-center gap-1 px-3 py-3 rounded-lg transition-all ${
              activeView === 'devices'
                ? 'bg-neutral-800 text-primary-400'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
            } focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900`}
            aria-pressed={activeView === 'devices'}
            aria-label="Devices view"
          >
            <Activity className="w-5 h-5" />
            <span className="text-xs">Devices</span>
          </button>
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Top Status Bar */}
        <header className="h-16 bg-neutral-900 border-b border-neutral-800 flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <h1 className="tracking-wide">SSTeVe SSTV</h1>
            <div
              className={`px-3 py-1 rounded-full text-xs ${stateColors[appState]} text-white`}
              role="status"
              aria-label={`Application state: ${stateLabels[appState]}`}
            >
              {stateLabels[appState]}
            </div>
          </div>

          <div className="flex items-center gap-6">
            {/* SNR/Level Indicator */}
            <div className="flex items-center gap-3 text-sm">
              <span className="text-neutral-400">SNR</span>
              <div className="flex gap-1 items-center">
                <div className="w-1 h-3 bg-success-500 rounded-sm"></div>
                <div className="w-1 h-4 bg-success-500 rounded-sm"></div>
                <div className="w-1 h-5 bg-success-500 rounded-sm"></div>
                <div className="w-1 h-6 bg-warning-500 rounded-sm"></div>
                <div className="w-1 h-4 bg-neutral-700 rounded-sm"></div>
                <div className="w-1 h-3 bg-neutral-700 rounded-sm"></div>
              </div>
              <span className="text-neutral-300 tabular-nums">18 dB</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              className="p-2 rounded-lg bg-neutral-800 text-neutral-300 hover:bg-neutral-700 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900"
              aria-label="Settings"
              onClick={() => setSettingsOpen(true)}
            >
              <SettingsIcon className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Main View Area */}
        <main className="flex-1 overflow-auto">
          {activeView === 'capture' && <CaptureView onStateChange={setAppState} telemetryReactive={settings.telemetryReactive} />}
          {activeView === 'transmit' && <TransmitView onStateChange={setAppState} />}
          {activeView === 'log' && <LogView />}
          {activeView === 'devices' && <DevicesView />}
        </main>
      </div>
    </div>
  );
}