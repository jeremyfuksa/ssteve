import { useState } from 'react';
import { Upload, Play, Send } from 'lucide-react';
import { Select } from './ui/Select';
import { Slider } from './ui/Slider';
import { ConfirmTransmitModal } from './ui/ConfirmTransmitModal';

interface TransmitViewProps {
  onStateChange: (state: 'idle' | 'listening' | 'locked' | 'transmitting' | 'error') => void;
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

type PTTMethod = 'none' | 'serial' | 'vox';
type FitMode = 'fit' | 'letterbox';

export function TransmitView({ onStateChange }: TransmitViewProps) {
  const [selectedMode, setSelectedMode] = useState('scottie-s1');
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [hasImage, setHasImage] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [countdown, setCountdown] = useState(5);
  const [isTransmitting, setIsTransmitting] = useState(false);
  
  // Transmit controls
  const [callsign, setCallsign] = useState('');
  const [overlayPosition, setOverlayPosition] = useState<'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'>('bottom-right');
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [brightness, setBrightness] = useState(0);
  const [contrast, setContrast] = useState(0);
  const [pttMethod, setPttMethod] = useState<PTTMethod>('vox');
  const [outputDevice, setOutputDevice] = useState('default');
  const [serialPort, setSerialPort] = useState('COM3');
  const [useRTS, setUseRTS] = useState(true);
  const [useDTR, setUseDTR] = useState(false);
  const [preDelay, setPreDelay] = useState(500);
  const [postDelay, setPostDelay] = useState(200);
  
  const outputDeviceOptions = [
    { value: 'default', label: 'System Default' },
    { value: 'built-in', label: 'Built-in Speakers' },
    { value: 'usb', label: 'USB Audio Device' },
  ];

  const serialPortOptions = [
    { value: 'COM3', label: 'COM3' },
    { value: 'COM4', label: 'COM4' },
    { value: '/dev/ttyUSB0', label: '/dev/ttyUSB0' },
  ];

  const handleTransmitClick = () => {
    if (hasImage) {
      setShowConfirmModal(true);
    }
  };

  const handleConfirmTransmit = () => {
    setShowConfirmModal(false);
    setIsTransmitting(true);
    onStateChange('transmitting');
    // TODO: Initiate actual transmission
  };

  const handleCancelTransmit = () => {
    setShowConfirmModal(false);
  };

  const selectedModeData = modes.find(m => m.id === selectedMode);

  return (
    <div className="h-full bg-neutral-950 p-6">
      <ConfirmTransmitModal
        isOpen={showConfirmModal}
        mode={selectedModeData?.name || ''}
        duration={selectedModeData?.duration || ''}
        onConfirm={handleConfirmTransmit}
        onCancel={handleCancelTransmit}
      />
      
      <div className="grid grid-cols-[320px,1fr,280px] gap-6 h-full w-full">
        {/* Left Column - Controls */}
        <div className="space-y-6">
          {/* Mode Selection */}
          <section>
            <h2 className="text-sm font-medium text-neutral-300 mb-3">SSTV Mode</h2>
            <div className="grid grid-cols-2 gap-2">
              {modes.map((mode) => (
                <button
                  key={mode.id}
                  onClick={() => setSelectedMode(mode.id)}
                  className={`px-4 py-3 rounded-lg text-left transition-all hover:-translate-y-0.5 ${
                    selectedMode === mode.id
                      ? 'bg-secondary-600 text-white scale-[0.98]'
                      : 'bg-neutral-800 text-neutral-300 hover:bg-neutral-700'
                  } focus:outline-none focus:ring-2 focus:ring-secondary-500 focus:ring-offset-2 focus:ring-offset-neutral-950`}
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

          {/* Callsign Overlay */}
          <section>
            <h2 className="text-sm font-medium text-neutral-300 mb-3">Station ID</h2>
            <div className="space-y-3">
              <div>
                <label htmlFor="callsign" className="text-xs text-neutral-400 block mb-2">
                  Callsign
                </label>
                <input
                  id="callsign"
                  type="text"
                  value={callsign}
                  onChange={(e) => setCallsign(e.target.value.toUpperCase())}
                  placeholder="W1ABC"
                  maxLength={10}
                  className="w-full px-3 py-2 bg-neutral-800 text-neutral-100 rounded-lg border border-neutral-700 focus:outline-none focus:ring-2 focus:ring-secondary-500 focus:border-transparent uppercase"
                />
              </div>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={overlayEnabled}
                  onChange={(e) => setOverlayEnabled(e.target.checked)}
                  className="w-4 h-4 rounded border-2 border-neutral-600 bg-neutral-900 checked:bg-secondary-600 checked:border-secondary-600 focus:ring-2 focus:ring-secondary-500 transition-all cursor-pointer"
                />
                <span className="text-xs text-neutral-400">Show callsign overlay</span>
              </label>

              {overlayEnabled && (
                <div>
                  <label className="text-xs text-neutral-400 block mb-2">Position</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { value: 'top-left', label: 'Top Left' },
                      { value: 'top-right', label: 'Top Right' },
                      { value: 'bottom-left', label: 'Bottom Left' },
                      { value: 'bottom-right', label: 'Bottom Right' },
                    ].map((pos) => (
                      <button
                        key={pos.value}
                        onClick={() => setOverlayPosition(pos.value as any)}
                        className={`px-2 py-1.5 text-xs rounded transition-all ${
                          overlayPosition === pos.value
                            ? 'bg-secondary-600 text-white'
                            : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
                        }`}
                      >
                        {pos.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* Image Adjustments */}
          <section>
            <h2 className="text-sm font-medium text-neutral-300 mb-3">Image Adjustments</h2>
            <div className="space-y-4">
              <Slider
                id="brightness"
                label="Brightness"
                value={brightness}
                onChange={setBrightness}
                min={-50}
                max={50}
                step={5}
                unit="%"
              />
              <Slider
                id="contrast"
                label="Contrast"
                value={contrast}
                onChange={setContrast}
                min={-50}
                max={50}
                step={5}
                unit="%"
              />
            </div>
          </section>
        </div>

        {/* Center Column - Image Preview & Upload */}
        <div className="flex-1 flex flex-col gap-6">
          {/* Image Preview Canvas */}
          <section className="flex-1 bg-neutral-900 rounded-lg flex items-center justify-center relative overflow-hidden min-h-[400px]">
            {!hasImage ? (
              <div className="text-center text-neutral-500">
                <Upload className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <div className="text-sm font-medium">No image loaded</div>
                <div className="text-xs mt-1 opacity-75">Click "Load Image" to select a file</div>
              </div>
            ) : (
              <div className="relative w-full h-full p-6">
                {/* TODO: Replace with actual image preview canvas */}
                <div 
                  className="w-full h-full bg-neutral-950 rounded border-2 border-neutral-700 flex items-center justify-center relative"
                  style={{
                    filter: `brightness(${100 + brightness}%) contrast(${100 + contrast}%)`
                  }}
                >
                  <div className="text-neutral-600 text-center">
                    <div className="text-sm font-medium">Image Preview</div>
                    <div className="text-xs mt-2 opacity-75">320×256 @ Scottie S1</div>
                  </div>
                  
                  {/* Callsign Overlay Preview */}
                  {overlayEnabled && callsign && (
                    <div 
                      className={`absolute text-white bg-black/60 px-3 py-1 rounded font-mono text-sm ${
                        overlayPosition === 'top-left' ? 'top-4 left-4' :
                        overlayPosition === 'top-right' ? 'top-4 right-4' :
                        overlayPosition === 'bottom-left' ? 'bottom-4 left-4' :
                        'bottom-4 right-4'
                      }`}
                    >
                      {callsign}
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>

        {/* Right Column - Output & PTT */}
        <div className="flex flex-col gap-6">
          {/* Output Device */}
          <section>
            <h2 className="text-sm font-medium text-neutral-300 mb-3">Output</h2>
            <Select
              id="output-device"
              value={outputDevice}
              onChange={setOutputDevice}
              options={outputDeviceOptions}
              className="mb-3"
            />
            <button className="w-full px-4 py-2 bg-neutral-800 text-neutral-300 rounded-lg hover:bg-neutral-700 transition-all flex items-center justify-center gap-2 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-950">
              <Play className="w-4 h-4" />
              Play test tone
            </button>
          </section>

          {/* PTT Settings */}
          <section className="flex-1 flex flex-col">
            <h2 className="text-sm font-medium text-neutral-300 mb-3">PTT Method</h2>
            
            <div className="space-y-2 mb-4">
              <label className="flex items-center gap-3 px-4 py-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700 transition-all focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 focus-within:ring-offset-neutral-950">
                <input
                  type="radio"
                  name="ptt"
                  value="none"
                  checked={pttMethod === 'none'}
                  onChange={(e) => setPttMethod(e.target.value as PTTMethod)}
                  className="accent-primary-600 focus:outline-none"
                />
                <span>None (Manual)</span>
              </label>
              
              <label className="flex items-center gap-3 px-4 py-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700 transition-all focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 focus-within:ring-offset-neutral-950">
                <input
                  type="radio"
                  name="ptt"
                  value="serial"
                  checked={pttMethod === 'serial'}
                  onChange={(e) => setPttMethod(e.target.value as PTTMethod)}
                  className="accent-primary-600 focus:outline-none"
                />
                <span>Serial (CAT)</span>
              </label>
              
              <label className="flex items-center gap-3 px-4 py-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700 transition-all focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 focus-within:ring-offset-neutral-950">
                <input
                  type="radio"
                  name="ptt"
                  value="vox"
                  checked={pttMethod === 'vox'}
                  onChange={(e) => setPttMethod(e.target.value as PTTMethod)}
                  className="accent-primary-600 focus:outline-none"
                />
                <span>VOX</span>
              </label>
            </div>

            {/* Serial PTT Settings */}
            {pttMethod === 'serial' && (
              <div className="bg-neutral-900 rounded-lg p-4 space-y-5">
                <Select
                  id="serial-port"
                  label="Serial port"
                  value={serialPort}
                  onChange={setSerialPort}
                  options={serialPortOptions}
                />

                <div className="flex gap-3">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={useRTS}
                      onChange={(e) => setUseRTS(e.target.checked)}
                      className="accent-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900"
                    />
                    <span className="text-sm font-medium">RTS</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={useDTR}
                      onChange={(e) => setUseDTR(e.target.checked)}
                      className="accent-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900"
                    />
                    <span className="text-sm font-medium">DTR</span>
                  </label>
                </div>

                <Slider
                  id="pre-delay"
                  label="Pre-TX delay"
                  value={preDelay}
                  onChange={setPreDelay}
                  min={0}
                  max={2000}
                  step={50}
                  unit=" ms"
                  helpText="Delay before transmission starts"
                />

                <Slider
                  id="post-delay"
                  label="Post-TX delay"
                  value={postDelay}
                  onChange={setPostDelay}
                  min={0}
                  max={2000}
                  step={50}
                  unit=" ms"
                  helpText="Delay after transmission ends"
                />

                <button className="w-full px-4 py-2 bg-neutral-800 text-neutral-300 rounded-lg hover:bg-neutral-700 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900">
                  Test PTT
                </button>
              </div>
            )}
          </section>

          {/* Transmit Button */}
          <section>
            <button
              onClick={handleTransmitClick}
              disabled={!hasImage}
              className={`w-full px-6 py-4 rounded-lg flex items-center justify-center gap-2 transition-all ${
                hasImage
                  ? 'bg-secondary-600 hover:bg-secondary-700 hover:-translate-y-0.5 hover:shadow-[0_0_20px_rgba(168,101,79,0.4)] text-white focus:outline-none focus:ring-2 focus:ring-secondary-500 focus:ring-offset-2 focus:ring-offset-neutral-950'
                  : 'bg-neutral-700 text-neutral-500 cursor-not-allowed'
              }`}
              style={{
                transition: hasImage 
                  ? 'all 300ms cubic-bezier(0.68, -0.55, 0.265, 1.55)' 
                  : 'none',
                animation: hasImage ? 'breathe 2s ease-in-out infinite' : 'none'
              }}
              aria-disabled={!hasImage}
            >
              <Send className="w-5 h-5" />
              <div>
                <div className="font-medium">{hasImage ? 'Initiate TX Sequence' : 'Transmit'}</div>
                <div className="text-xs opacity-75">{hasImage ? 'Click to confirm' : 'Load image to enable'}</div>
              </div>
            </button>
            
            {/* Progress bar placeholder */}
            <div className="mt-3 bg-neutral-900 rounded-lg p-3">
              <div className="flex justify-between text-xs text-neutral-400 mb-2 font-medium">
                <span>Ready</span>
                <span className="tabular-nums">36 sec estimated</span>
              </div>
              <div className="w-full bg-neutral-800 rounded-full h-2">
                <div className="bg-primary-600 h-2 rounded-full w-0 transition-all"></div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}