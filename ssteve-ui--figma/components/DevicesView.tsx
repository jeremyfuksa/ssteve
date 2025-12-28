import { useState } from 'react';
import { Check } from 'lucide-react';
import { Select } from './ui/Select';
import { Slider } from './ui/Slider';
import { LevelMeter } from './ui/LevelMeter';

type AudioDevice = {
  id: string;
  name: string;
  channels: number;
  sampleRates: string;
  isDefault: boolean;
};

const mockInputDevices: AudioDevice[] = [
  {
    id: 'input-1',
    name: 'Built-in Microphone',
    channels: 2,
    sampleRates: '44.1, 48 kHz',
    isDefault: true,
  },
  {
    id: 'input-2',
    name: 'USB Audio Device',
    channels: 2,
    sampleRates: '44.1, 48, 96 kHz',
    isDefault: false,
  },
  {
    id: 'input-3',
    name: 'Virtual Audio Cable',
    channels: 2,
    sampleRates: '44.1, 48 kHz',
    isDefault: false,
  },
];

const mockOutputDevices: AudioDevice[] = [
  {
    id: 'output-1',
    name: 'Built-in Speakers',
    channels: 2,
    sampleRates: '44.1, 48 kHz',
    isDefault: true,
  },
  {
    id: 'output-2',
    name: 'USB Audio Device',
    channels: 2,
    sampleRates: '44.1, 48, 96 kHz',
    isDefault: false,
  },
];

type PTTMethod = 'none' | 'serial' | 'vox';

export function DevicesView() {
  const [audioInputDevice, setAudioInputDevice] = useState('default');
  const [audioOutputDevice, setAudioOutputDevice] = useState('default');
  const [pttMethod, setPttMethod] = useState('vox');
  const [pttPort, setPttPort] = useState('COM3');
  const [pttDelay, setPttDelay] = useState(250);
  const [leaderTone, setLeaderTone] = useState(1000);
  const [tailDelay, setTailDelay] = useState(500);
  const [useAsDefault, setUseAsDefault] = useState(false);
  const [audioLevels] = useState({ leftChannel: 52, rightChannel: 48 });

  const serialPortOptions = [
    { value: 'COM3', label: 'COM3' },
    { value: 'COM4', label: 'COM4' },
    { value: '/dev/ttyUSB0', label: '/dev/ttyUSB0' },
    { value: '/dev/ttyUSB1', label: '/dev/ttyUSB1' },
  ];

  const setDefaultInput = (id: string) => {
    setAudioInputDevice(id);
  };

  const setDefaultOutput = (id: string) => {
    setAudioOutputDevice(id);
  };

  return (
    <div className="h-full bg-neutral-950 p-6 overflow-auto">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Audio Devices Section */}
        <section>
          <h2 className="text-lg font-medium text-neutral-300 mb-4">Audio Devices</h2>
          
          <div className="grid grid-cols-2 gap-6">
            {/* Input Devices */}
            <div>
              <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-3">Input Devices</h3>
              <div className="bg-neutral-900 rounded-lg overflow-hidden">
                <table className="w-full">
                  <caption className="sr-only">Audio input devices</caption>
                  <thead className="bg-neutral-800 text-neutral-400 text-xs">
                    <tr>
                      <th className="text-left px-4 py-2 font-medium">Name</th>
                      <th className="text-left px-4 py-2 font-medium">Channels</th>
                      <th className="text-left px-4 py-2 font-medium">Sample Rates</th>
                      <th className="text-left px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="text-sm">
                    {mockInputDevices.map((device) => (
                      <tr key={device.id} className="border-b border-neutral-800">
                        <td className="px-4 py-4 flex items-center gap-2">
                          <span className="font-medium">{device.name}</span>
                          {device.isDefault && (
                            <span className="px-2 py-0.5 bg-primary-900/30 text-primary-400 text-xs rounded font-medium">
                              Default
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-4">{device.channels}</td>
                        <td className="px-4 py-4 text-neutral-400 text-xs">{device.sampleRates}</td>
                        <td className="px-4 py-4">
                          {!device.isDefault && (
                            <button
                              onClick={() => setDefaultInput(device.id)}
                              className="text-xs text-primary-400 hover:text-primary-300 font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900 rounded px-2 py-1"
                            >
                              Set default
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                
                {/* Level meter for selected input */}
                <div className="bg-neutral-800 p-4 border-t border-neutral-700">
                  <LevelMeter levels={audioLevels} label="Input level" />
                </div>
              </div>
            </div>

            {/* Output Devices */}
            <div>
              <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-3">Output Devices</h3>
              <div className="bg-neutral-900 rounded-lg overflow-hidden">
                <table className="w-full">
                  <caption className="sr-only">Audio output devices</caption>
                  <thead className="bg-neutral-800 text-neutral-400 text-xs">
                    <tr>
                      <th className="text-left px-4 py-2 font-medium">Name</th>
                      <th className="text-left px-4 py-2 font-medium">Channels</th>
                      <th className="text-left px-4 py-2 font-medium">Sample Rates</th>
                      <th className="text-left px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="text-sm">
                    {mockOutputDevices.map((device) => (
                      <tr key={device.id} className="border-b border-neutral-800">
                        <td className="px-4 py-4 flex items-center gap-2">
                          <span className="font-medium">{device.name}</span>
                          {device.isDefault && (
                            <span className="px-2 py-0.5 bg-primary-900/30 text-primary-400 text-xs rounded font-medium">
                              Default
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-4">{device.channels}</td>
                        <td className="px-4 py-4 text-neutral-400 text-xs">{device.sampleRates}</td>
                        <td className="px-4 py-4">
                          {!device.isDefault && (
                            <button
                              onClick={() => setDefaultOutput(device.id)}
                              className="text-xs text-primary-400 hover:text-primary-300 font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900 rounded px-2 py-1"
                            >
                              Set default
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        {/* PTT Configuration Section */}
        <section>
          <h2 className="text-lg font-medium text-neutral-300 mb-4">PTT Configuration</h2>
          
          <div className="bg-neutral-900 rounded-lg p-6 max-w-2xl">
            <div className="space-y-2 mb-6">
              <label className="flex items-center gap-3 px-4 py-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700 transition-all focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 focus-within:ring-offset-neutral-900">
                <input
                  type="radio"
                  name="ptt-global"
                  value="none"
                  checked={pttMethod === 'none'}
                  onChange={(e) => setPttMethod(e.target.value as PTTMethod)}
                  className="accent-primary-600 focus:outline-none"
                />
                <span className="font-medium">None (Manual PTT)</span>
              </label>
              
              <label className="flex items-center gap-3 px-4 py-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700 transition-all focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 focus-within:ring-offset-neutral-900">
                <input
                  type="radio"
                  name="ptt-global"
                  value="serial"
                  checked={pttMethod === 'serial'}
                  onChange={(e) => setPttMethod(e.target.value as PTTMethod)}
                  className="accent-primary-600 focus:outline-none"
                />
                <span className="font-medium">Serial (CAT)</span>
              </label>
              
              <label className="flex items-center gap-3 px-4 py-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700 transition-all focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 focus-within:ring-offset-neutral-900">
                <input
                  type="radio"
                  name="ptt-global"
                  value="vox"
                  checked={pttMethod === 'vox'}
                  onChange={(e) => setPttMethod(e.target.value as PTTMethod)}
                  className="accent-primary-600 focus:outline-none"
                />
                <span className="font-medium">VOX (Voice-activated)</span>
              </label>
            </div>

            {/* Serial PTT Settings */}
            {pttMethod === 'serial' && (
              <div className="bg-neutral-800 rounded-lg p-6 space-y-6">
                <Select
                  id="serial-port-global"
                  label="Serial port"
                  value={pttPort}
                  onChange={setPttPort}
                  options={serialPortOptions}
                />

                <div>
                  <div className="text-sm font-medium text-neutral-300 mb-3">Control lines</div>
                  <div className="flex gap-6">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={useRTS}
                        onChange={(e) => setUseRTS(e.target.checked)}
                        className="accent-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-800"
                      />
                      <span className="text-sm font-medium">RTS (Request to Send)</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={useDTR}
                        onChange={(e) => setUseDTR(e.target.checked)}
                        className="accent-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-800"
                      />
                      <span className="text-sm font-medium">DTR (Data Terminal Ready)</span>
                    </label>
                  </div>
                </div>

                <Slider
                  id="pre-delay-global"
                  label="Pre-TX delay"
                  value={pttDelay}
                  onChange={setPttDelay}
                  min={0}
                  max={2000}
                  step={50}
                  unit=" ms"
                  helpText="Delay before transmission starts"
                />

                <Slider
                  id="post-delay-global"
                  label="Post-TX delay"
                  value={tailDelay}
                  onChange={setTailDelay}
                  min={0}
                  max={2000}
                  step={50}
                  unit=" ms"
                  helpText="Delay after transmission ends"
                />

                <button className="w-full px-4 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-all font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-800">
                  Test Serial PTT
                </button>
              </div>
            )}
          </div>
        </section>

        {/* PTT Timing */}
        <section className="bg-neutral-900 rounded-lg p-6">
          <h2 className="font-medium text-neutral-100 mb-4">PTT Timing</h2>
          <div className="space-y-4">
            <Slider
              id="ptt-delay"
              label="PTT Delay"
              value={pttDelay}
              onChange={setPttDelay}
              min={0}
              max={2000}
              step={50}
              unit=" ms"
              helpText="Delay before transmitting audio after keying PTT"
            />
            <Slider
              id="leader-tone"
              label="Leader Tone Duration"
              value={leaderTone}
              onChange={setLeaderTone}
              min={0}
              max={5000}
              step={100}
              unit=" ms"
              helpText="Duration of leader tone before VIS code"
            />
            <Slider
              id="tail-delay"
              label="Tail Delay"
              value={tailDelay}
              onChange={setTailDelay}
              min={0}
              max={2000}
              step={50}
              unit=" ms"
              helpText="Hold PTT after transmission ends"
            />
          </div>
        </section>

        {/* Defaults Section */}
        <section>
          <h2 className="text-lg font-medium text-neutral-300 mb-4">Defaults</h2>
          
          <div className="bg-neutral-900 rounded-lg p-6 max-w-2xl">
            <label className="flex items-start gap-3 cursor-pointer focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 focus-within:ring-offset-neutral-900 rounded p-2 -m-2">
              <input
                type="checkbox"
                checked={useAsDefault}
                onChange={(e) => setUseAsDefault(e.target.checked)}
                className="mt-1 accent-primary-600 focus:outline-none"
              />
              <div>
                <div className="mb-2 font-medium">Use this setup as my default</div>
                <div className="text-sm text-neutral-400">
                  Current defaults: {mockInputDevices.find((d) => d.isDefault)?.name} (input),{' '}
                  {mockOutputDevices.find((d) => d.isDefault)?.name} (output), {pttMethod.toUpperCase()} PTT
                  {pttMethod === 'serial' && ` via ${pttPort}`}
                </div>
              </div>
            </label>

            {useAsDefault && (
              <div className="mt-4 p-4 bg-success-700/20 border border-success-600 rounded-lg flex items-start gap-2">
                <Check className="w-5 h-5 text-success-500 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-success-500">
                  These settings will be used automatically when SSTeVe starts
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}