import { useState } from 'react';
import { Play, Square, BookImage, Radio } from 'lucide-react';
import { Select } from './ui/Select';
import { LevelMeter } from './ui/LevelMeter';
import { ScanLines } from './ui/ScanLines';
import { TelemetryValue } from './ui/TelemetryValue';
import { Waterfall } from './ui/Waterfall';
import { FrequencyOffset } from './ui/FrequencyOffset';
import { SlantCorrection } from './ui/SlantCorrection';
import { AFCControl } from './ui/AFCControl';
import { SquelchControl } from './ui/SquelchControl';

// TODO: Wire to Tauri backend via IPC
interface DecodingState {
  isActive: boolean;
  currentLine: number;
  totalLines: number;
  progress: number; // 0-100
}

interface CaptureViewProps {
  onStateChange: (state: 'idle' | 'listening' | 'locked' | 'transmitting' | 'error') => void;
  telemetryReactive?: boolean;
}

type SSTVMode = {
  id: string;
  name: string;
  resolution: string;
  duration: string;
};

const modes: SSTVMode[] = [
  { id: 'scottie-s1', name: 'Scottie S1', resolution: '320×256', duration: '110 sec' },
  { id: 'martin-m1', name: 'Martin M1', resolution: '320×256', duration: '114 sec' },
  { id: 'robot-36', name: 'Robot 36', resolution: '320×240', duration: '36 sec' },
];

type StatusStep = 'listening' | 'vis' | 'sync' | 'decoding' | 'locked';

const statusSteps: { id: StatusStep; label: string }[] = [
  { id: 'listening', label: 'Listening' },
  { id: 'vis', label: 'VIS detected' },
  { id: 'sync', label: 'Sync lock' },
  { id: 'decoding', label: 'Decoding' },
  { id: 'locked', label: 'Picture locked' },
];

export function CaptureView({ onStateChange, telemetryReactive = true }: CaptureViewProps) {
  const [selectedMode, setSelectedMode] = useState('scottie-s1');
  const [inputDevice, setInputDevice] = useState('default');
  const [isCapturing, setIsCapturing] = useState(false);
  const [currentStep, setCurrentStep] = useState<StatusStep>('listening');
  const [audioLevels, setAudioLevels] = useState({ leftChannel: 45, rightChannel: 42 });
  const [decodingState, setDecodingState] = useState({
    isActive: false,
    progress: 0,
    currentLine: 0,
    totalLines: 256
  });
  
  // MVP Signal Processing Controls
  const [forcedMode, setForcedMode] = useState(false);
  const [freqOffset, setFreqOffset] = useState(0);
  const [autoSlant, setAutoSlant] = useState(true);
  const [manualSlant, setManualSlant] = useState(0);
  const [afcEnabled, setAfcEnabled] = useState(true);
  const [afcRange, setAfcRange] = useState<50 | 100 | 200>(100);
  const [afcResponse, setAfcResponse] = useState<'fast' | 'medium' | 'slow'>('medium');
  const [squelchLevel, setSquelchLevel] = useState(-30);
  const [inputGain, setInputGain] = useState(100);

  const handleStartCapture = () => {
    setIsCapturing(true);
    setCurrentStep('listening');
    onStateChange('listening');
    
    // Simulate signal detection and decoding workflow
    setTimeout(() => {
      setCurrentStep('vis');
      setTimeout(() => {
        setCurrentStep('sync');
        setTimeout(() => {
          setCurrentStep('decoding');
          onStateChange('locked');
          
          // Simulate progressive decode
          const interval = setInterval(() => {
            setDecodingState(prev => {
              if (prev.progress >= 100) {
                clearInterval(interval);
                setCurrentStep('locked');
                return prev;
              }
              return {
                isActive: true,
                progress: prev.progress + 2,
                currentLine: Math.floor((prev.progress / 100) * prev.totalLines),
                totalLines: prev.totalLines
              };
            });
          }, 100);
        }, 1500);
      }, 1000);
    }, 2000);
  };

  const handleStopCapture = () => {
    setIsCapturing(false);
    setCurrentStep('listening');
    onStateChange('idle');
    setDecodingState({
      isActive: false,
      progress: 0,
      currentLine: 0,
      totalLines: 256
    });
  };

  const handleManualSync = () => {
    if (!isCapturing) {
      handleStartCapture();
    }
    // Force sync lock regardless of current state
    setCurrentStep('sync');
    setTimeout(() => {
      setCurrentStep('decoding');
      onStateChange('locked');
    }, 500);
  };

  // Mock squelch state based on audio levels
  const currentRMS = (audioLevels.leftChannel + audioLevels.rightChannel) / 2;
  const squelchOpen = currentRMS > ((squelchLevel + 60) / 60) * 100;

  return (
    <div className="h-full bg-neutral-950 p-6">
      <div className="grid grid-cols-[320px,1fr,280px] gap-6 h-full w-full">
        {/* Left Column - Controls */}
        <div className="space-y-6">
          {/* Input Device */}
          <section>
            <Select
              id="input-device"
              label="Input Device"
              value={inputDevice}
              onChange={setInputDevice}
              options={[
                { value: 'default', label: 'Default Audio In' },
                { value: 'vb-cable', label: 'VB-Cable Output' },
                { value: 'usb-audio', label: 'USB Audio Interface' },
              ]}
            />
          </section>

          {/* Input Gain */}
          <section>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-sm font-medium text-neutral-300">Input Gain</label>
                <span className="text-sm text-neutral-400 tabular-nums">{inputGain}%</span>
              </div>
              <input
                type="range"
                min={0}
                max={200}
                step={5}
                value={inputGain}
                onChange={(e) => setInputGain(Number(e.target.value))}
                className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-xs text-neutral-500">
                <span>0%</span>
                <span>100%</span>
                <span>200%</span>
              </div>
            </div>
          </section>

          {/* Squelch Control */}
          <section>
            <SquelchControl
              level={squelchLevel}
              onChange={setSquelchLevel}
              currentRMS={currentRMS}
              isOpen={squelchOpen}
            />
          </section>

          {/* Mode Selection with Force Lock */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium text-neutral-300">SSTV Mode</h2>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={forcedMode}
                  onChange={(e) => setForcedMode(e.target.checked)}
                  className="w-4 h-4 rounded border-2 border-neutral-600 bg-neutral-900 checked:bg-warning-600 checked:border-warning-600 focus:ring-2 focus:ring-warning-500 transition-all cursor-pointer"
                />
                <span className="text-xs text-neutral-400">Force Mode</span>
              </label>
            </div>
            {forcedMode && (
              <div className="mb-3 px-3 py-2 bg-warning-500/10 border border-warning-500/30 rounded text-xs text-warning-400">
                VIS auto-detection disabled
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              {modes.map((mode) => (
                <button
                  key={mode.id}
                  onClick={() => setSelectedMode(mode.id)}
                  className={`px-4 py-3 rounded-lg text-left transition-all hover:-translate-y-0.5 ${
                    selectedMode === mode.id
                      ? 'bg-primary-600 text-white scale-[0.98]'
                      : 'bg-neutral-800 text-neutral-300 hover:bg-neutral-700'
                  } focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900`}
                  style={{
                    transition: 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                  }}
                  aria-pressed={selectedMode === mode.id}
                >
                  <div className="font-medium text-sm">{mode.name}</div>
                  <div className="text-xs opacity-75 mt-0.5">{mode.resolution}</div>
                </button>
              ))}
            </div>
          </section>

          {/* Control Buttons */}
          <section className="flex gap-2">
            {!isCapturing ? (
              <button
                onClick={handleStartCapture}
                className="flex-1 bg-success-600 hover:bg-success-700 text-white px-4 py-3 rounded-lg flex items-center justify-center gap-2 transition-all hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-success-500 focus:ring-offset-2 focus:ring-offset-neutral-950"
                style={{
                  transition: 'all 200ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <Play className="w-4 h-4" />
                <span className="font-medium">Start</span>
              </button>
            ) : (
              <button
                onClick={handleStopCapture}
                className="flex-1 bg-danger-600 hover:bg-danger-700 text-white px-4 py-3 rounded-lg flex items-center justify-center gap-2 transition-all hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-danger-500 focus:ring-offset-2 focus:ring-offset-neutral-950"
                style={{
                  transition: 'all 200ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
                }}
              >
                <Square className="w-4 h-4" />
                <span className="font-medium">Stop</span>
              </button>
            )}
          </section>

          {/* Manual Sync Button */}
          <section>
            <button
              onClick={handleManualSync}
              disabled={!squelchOpen && !isCapturing}
              className={`w-full px-4 py-3 rounded-lg flex items-center justify-center gap-2 font-medium transition-all ${
                squelchOpen || isCapturing
                  ? 'bg-primary-600 hover:bg-primary-700 text-white hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-950'
                  : 'bg-neutral-800 text-neutral-500 cursor-not-allowed'
              }`}
              style={{
                transition: 'all 200ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
              }}
            >
              <Radio className="w-4 h-4" />
              <div className="text-left">
                <div className="text-sm">Manual SYNC</div>
                <div className="text-xs opacity-75">Press at sync tone</div>
              </div>
            </button>
            <p className="text-xs text-neutral-500 mt-2">
              Keyboard: Press <kbd className="px-1.5 py-0.5 bg-neutral-800 rounded text-neutral-400">SPACE</kbd> or <kbd className="px-1.5 py-0.5 bg-neutral-800 rounded text-neutral-400">S</kbd>
            </p>
          </section>

          {/* AFC Control */}
          <section>
            <AFCControl
              enabled={afcEnabled}
              onEnabledChange={setAfcEnabled}
              range={afcRange}
              onRangeChange={setAfcRange}
              responseTime={afcResponse}
              onResponseTimeChange={setAfcResponse}
            />
          </section>
        </div>

        {/* Center Column - Canvas & Status Rail */}
        <div className="flex flex-col gap-4">
          {/* Status Rail */}
          <section className="bg-neutral-900 rounded-lg px-6 py-4" role="navigation" aria-label="Decoding status">
            <div className="flex items-center justify-between">
              {statusSteps.map((step, index) => (
                <div key={step.id} className="flex items-center">
                  <div className="flex flex-col items-center gap-2">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium transition-all ${
                        currentStep === step.id
                          ? 'bg-primary-600 text-white ring-2 ring-primary-400 ring-offset-2 ring-offset-neutral-900'
                          : 'bg-neutral-800 text-neutral-500'
                      }`}
                      aria-current={currentStep === step.id ? 'step' : undefined}
                    >
                      {index + 1}
                    </div>
                    <span className={`text-xs ${currentStep === step.id ? 'text-neutral-300 font-medium' : 'text-neutral-400'}`}>
                      {step.label}
                    </span>
                  </div>
                  {index < statusSteps.length - 1 && (
                    <div className="w-16 h-px bg-neutral-700 mx-2 mb-6"></div>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Canvas Area */}
          <section className="flex-1 bg-neutral-900 rounded-lg flex items-center justify-center relative overflow-hidden">
            {!isCapturing ? (
              <div className="relative w-full h-full flex items-center justify-center">
                <ScanLines speed="slow" />
                <div className="text-center text-neutral-500 relative z-10">
                  <div className="text-sm font-medium">Ready to capture SSTV signal</div>
                  <div className="text-xs mt-1 opacity-75">Listening for carrier...</div>
                </div>
              </div>
            ) : currentStep === 'listening' || currentStep === 'vis' ? (
              <div className="relative w-full h-full flex items-center justify-center">
                <ScanLines speed={currentStep === 'vis' ? 'fast' : 'normal'} />
                <div className="text-center text-neutral-400 relative z-10">
                  <div className="text-sm font-medium">
                    {currentStep === 'vis' ? 'VIS code detected...' : 'Listening for signal...'}
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-full h-full p-6" style={{
                boxShadow: currentStep === 'decoding' || currentStep === 'locked' 
                  ? 'inset 0 0 40px rgba(96, 122, 151, 0.1)' 
                  : 'none',
                transition: 'box-shadow 600ms ease-out'
              }}>
                {/* TODO: Replace with actual <canvas> element for bitmap rendering */}
                <div className="w-full h-full bg-neutral-950 rounded border-2 border-neutral-700 border-dashed flex items-center justify-center relative">
                  <div className="text-neutral-600 text-center">
                    <div className="text-sm font-medium">Decoding in progress...</div>
                    <div className="text-xs mt-2 opacity-75">320×256 @ 45%</div>
                  </div>
                  
                  {/* Horizontal scan line during decode */}
                  {currentStep === 'decoding' && (
                    <div className="absolute inset-0 pointer-events-none overflow-hidden">
                      <div 
                        className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-primary-400/40 to-transparent"
                        style={{
                          top: `${decodingState.progress}%`,
                          transition: 'top 100ms linear',
                          boxShadow: '0 0 8px rgba(128, 152, 176, 0.4)'
                        }}
                      />
                    </div>
                  )}
                  
                  {/* Loading overlay */}
                  {decodingState.isActive && (
                    <div className="absolute inset-0 bg-neutral-950/80 flex items-center justify-center">
                      <div className="flex flex-col items-center gap-3">
                        <div className="w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
                        <span className="text-sm text-neutral-400 font-medium">
                          Decoding line {decodingState.currentLine}/{decodingState.totalLines}
                        </span>
                        <div className="w-48 h-1 bg-neutral-800 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-primary-600 transition-all duration-300"
                            style={{ width: `${decodingState.progress}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>

        {/* Right Column - Status & Telemetry */}
        <div className="flex flex-col gap-6">
          {/* Status Rail */}
          <section>
            <h2 className="text-sm font-medium text-neutral-300 mb-4">Status</h2>
            <div className="flex flex-col gap-3">
              {statusSteps.map((step, index) => {
                const isActive = currentStep === step.id;
                const isCompleted = currentStep && statusSteps.findIndex(s => s.id === currentStep) > index;
                const isPreviousActive = index > 0 && currentStep === statusSteps[index - 1].id;
                
                return (
                  <div key={step.id} className="flex items-center gap-3">
                    <div className="flex flex-col items-center">
                      <div
                        className={`rounded-full border-2 flex items-center justify-center font-medium transition-all ${
                          isActive
                            ? 'w-9 h-9 border-primary-500 bg-primary-500 text-white scale-110'
                            : isCompleted
                            ? 'w-6 h-6 border-success-500 bg-success-500/20 text-success-500'
                            : 'w-6 h-6 border-neutral-600 bg-neutral-800 text-neutral-500'
                        }`}
                        style={{
                          transition: 'all 400ms cubic-bezier(0.34, 1.56, 0.64, 1)',
                          animation: isActive ? 'pulse-once 400ms cubic-bezier(0.4, 0, 0.6, 1)' : 'none'
                        }}
                      >
                        <span className="text-xs">{index + 1}</span>
                      </div>
                      {index < statusSteps.length - 1 && (
                        <div className={`w-0.5 h-8 my-1 transition-all ${
                          isCompleted ? 'bg-success-500' : 'bg-neutral-700'
                        }`}
                          style={{
                            transition: isCompleted || isPreviousActive ? 'background-color 400ms ease-out' : 'none'
                          }}
                        />
                      )}
                    </div>
                    <span
                      className={`text-xs transition-all ${
                        isActive ? 'text-neutral-100 font-medium' : 'text-neutral-400'
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Telemetry */}
          <section>
            <h2 className="text-sm font-medium text-neutral-300 mb-4">Telemetry</h2>
            <div 
              className="bg-neutral-800 rounded-lg p-4 space-y-3 transition-all"
              style={{
                boxShadow: audioLevels.leftChannel >= 95 || audioLevels.rightChannel >= 95
                  ? '0 0 0 2px rgba(220, 58, 56, 0.5)'
                  : 'none',
                transition: 'box-shadow 200ms ease-out'
              }}
            >
              <TelemetryValue label="SNR" value="18.4" unit="dB" type="snr" reactive={telemetryReactive} />
              <TelemetryValue label="RMS" value="42.1" unit="%" type="rms" reactive={telemetryReactive} />
              <TelemetryValue label="Peak" value="87.3" unit="%" type="peak" reactive={telemetryReactive} />
              <div className="pt-2 border-t border-neutral-700 mt-4">
                <TelemetryValue label="Frequency" value="1900" unit="Hz" />
              </div>
            </div>
          </section>

          {/* Frequency Offset */}
          <section>
            <FrequencyOffset
              value={freqOffset}
              onChange={setFreqOffset}
              detectedFreq={1200}
            />
          </section>

          {/* Slant Correction */}
          <section>
            <SlantCorrection
              autoSlant={autoSlant}
              onAutoSlantChange={setAutoSlant}
              manualSlant={manualSlant}
              onManualSlantChange={setManualSlant}
              detectedSlant={2.3}
            />
          </section>

          {/* Save Last Image */}
          <section>
            <button
              onClick={() => {/* TODO: Implement save */}}
              disabled={currentStep !== 'locked' && !decodingState.isActive}
              className={`w-full px-4 py-3 rounded-lg flex items-center justify-center gap-2 font-medium transition-all ${
                currentStep === 'locked' || decodingState.isActive
                  ? 'bg-success-600 hover:bg-success-700 text-white hover:-translate-y-0.5'
                  : 'bg-neutral-800 text-neutral-500 cursor-not-allowed'
              }`}
              style={{
                transition: 'all 200ms cubic-bezier(0.68, -0.55, 0.265, 1.55)'
              }}
            >
              <BookImage className="w-4 h-4" />
              Save Image
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}