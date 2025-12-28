import { useState } from 'react';
import { Search, Download, Trash2, ExternalLink } from 'lucide-react';

type Tab = 'pictures' | 'qsos';

type Picture = {
  id: string;
  timestamp: string;
  mode: string;
  callsign: string;
  source: 'RX' | 'TX';
  frequency: string;
  quality: number;
  notes: string;
};

type QSO = {
  id: string;
  startTime: string;
  endTime: string;
  callsign: string;
  mode: string;
  frequency: string;
  imageCount: number;
};

const mockPictures: Picture[] = [
  {
    id: '1',
    timestamp: '2024-12-03 14:33:02',
    mode: 'Robot 36',
    callsign: 'W1ABC',
    source: 'RX',
    frequency: '14.230 MHz',
    quality: 87,
    notes: 'Good signal, clear picture',
  },
  {
    id: '2',
    timestamp: '2024-12-03 13:15:44',
    mode: 'Scottie S1',
    callsign: 'K2DEF',
    source: 'RX',
    frequency: '14.230 MHz',
    quality: 92,
    notes: '',
  },
  {
    id: '3',
    timestamp: '2024-12-03 12:08:19',
    mode: 'Martin M1',
    callsign: 'N3GHI',
    source: 'TX',
    frequency: '14.230 MHz',
    quality: 95,
    notes: 'Test transmission',
  },
];

const mockQSOs: QSO[] = [
  {
    id: '1',
    startTime: '2024-12-03 14:30:00',
    endTime: '2024-12-03 14:35:22',
    callsign: 'W1ABC',
    mode: 'Robot 36',
    frequency: '14.230 MHz',
    imageCount: 2,
  },
  {
    id: '2',
    startTime: '2024-12-03 13:10:00',
    endTime: '2024-12-03 13:18:30',
    callsign: 'K2DEF',
    mode: 'Scottie S1',
    frequency: '14.230 MHz',
    imageCount: 1,
  },
];

export function LogView() {
  const [activeTab, setActiveTab] = useState<Tab>('pictures');
  const [selectedPicture, setSelectedPicture] = useState<Picture | null>(mockPictures[0]);
  const [selectedQSO, setSelectedQSO] = useState<QSO | null>(null);

  return (
    <div className="h-full bg-neutral-950 p-6 flex flex-col">
      {/* Tab Navigation */}
      <nav className="flex gap-1 mb-6 bg-neutral-900 rounded-lg p-1" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'pictures'}
          onClick={() => setActiveTab('pictures')}
          className={`flex-1 px-6 py-3 rounded-lg font-medium transition-all ${
            activeTab === 'pictures'
              ? 'bg-primary-600 text-white'
              : 'text-neutral-400 hover:text-neutral-200'
          } focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900`}
        >
          Pictures
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'qsos'}
          onClick={() => setActiveTab('qsos')}
          className={`flex-1 px-6 py-3 rounded-lg font-medium transition-all ${
            activeTab === 'qsos'
              ? 'bg-primary-600 text-white'
              : 'text-neutral-400 hover:text-neutral-200'
          } focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900`}
        >
          QSOs
        </button>
      </nav>

      {/* Pictures Tab Content */}
      {activeTab === 'pictures' && (
        <div role="tabpanel" className="flex-1 grid grid-cols-[1fr,400px] gap-6 overflow-hidden h-full w-full">
          {/* Pictures List */}
          <section className="flex flex-col">
            <h2 className="text-sm font-medium text-neutral-300 mb-3">Received & Transmitted Pictures</h2>
            <div className="flex-1 bg-neutral-900 rounded-lg overflow-auto">
              <table className="w-full">
                <caption className="sr-only">Received and transmitted pictures log</caption>
                <thead className="sticky top-0 bg-neutral-800 text-neutral-400 text-sm">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium">Preview</th>
                    <th className="text-left px-4 py-3 font-medium">Timestamp</th>
                    <th className="text-left px-4 py-3 font-medium">Mode</th>
                    <th className="text-left px-4 py-3 font-medium">Callsign</th>
                    <th className="text-left px-4 py-3 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {mockPictures.map((picture) => (
                    <tr
                      key={picture.id}
                      onClick={() => setSelectedPicture(picture)}
                      className={`cursor-pointer transition-all border-b border-neutral-800 ${
                        selectedPicture?.id === picture.id
                          ? 'bg-neutral-800'
                          : 'hover:bg-neutral-800/50'
                      } focus-within:ring-2 focus-within:ring-primary-500`}
                      tabIndex={0}
                      role="button"
                      aria-label={`Picture from ${picture.callsign} at ${picture.timestamp}`}
                    >
                      <td className="px-4 py-4">
                        <div className="w-16 h-12 bg-neutral-700 rounded"></div>
                      </td>
                      <td className="px-4 py-4 tabular-nums font-mono text-xs">{picture.timestamp}</td>
                      <td className="px-4 py-4">{picture.mode}</td>
                      <td className="px-4 py-4 font-medium">{picture.callsign}</td>
                      <td className="px-4 py-4">
                        <span
                          className={`px-2 py-1 rounded text-xs font-medium ${
                            picture.source === 'RX'
                              ? 'bg-primary-900/30 text-primary-400'
                              : 'bg-secondary-900/30 text-secondary-400'
                          }`}
                        >
                          {picture.source}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Picture Detail Panel */}
          <section className="flex flex-col bg-neutral-900 rounded-lg p-6">
            {selectedPicture ? (
              <>
                <h2 className="text-sm font-medium text-neutral-300 mb-4">Picture Details</h2>
                
                {/* Large Preview */}
                <div className="w-full max-h-64 bg-neutral-800 rounded-lg mb-6 overflow-hidden">
                  {/* TODO: Add actual image with object-cover */}
                  <div className="w-full h-64 bg-neutral-800"></div>
                </div>

                {/* Metadata */}
                <div className="space-y-3 mb-6">
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Mode</span>
                    <span>{selectedPicture.mode}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Callsign</span>
                    <span className="font-medium">{selectedPicture.callsign}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Frequency</span>
                    <span className="tabular-nums">{selectedPicture.frequency}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Quality</span>
                    <span className="text-success-500 font-medium">{selectedPicture.quality}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Source</span>
                    <span>{selectedPicture.source === 'RX' ? 'Received' : 'Transmitted'}</span>
                  </div>
                </div>

                {/* Notes */}
                <div>
                  <label htmlFor="notes" className="text-sm font-medium text-neutral-300 block mb-2">
                    Notes
                  </label>
                  <textarea
                    id="notes"
                    rows={4}
                    defaultValue={selectedPicture.notes}
                    className="w-full px-3 py-2 bg-neutral-800 text-neutral-200 rounded-lg border border-neutral-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900 resize-none"
                    placeholder="Add notes about this picture..."
                  />
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-neutral-500 text-sm">
                Select a picture to view details
              </div>
            )}
          </section>
        </div>
      )}

      {/* QSOs Tab Content */}
      {activeTab === 'qsos' && (
        <div role="tabpanel" className="flex-1 grid grid-cols-[1fr,400px] gap-6 overflow-hidden h-full w-full">
          {/* QSO List */}
          <section className="flex flex-col">
            <h2 className="text-sm font-medium text-neutral-300 mb-3">QSO Log</h2>
            <div className="flex-1 bg-neutral-900 rounded-lg overflow-auto">
              <table className="w-full">
                <caption className="sr-only">QSO contact log</caption>
                <thead className="sticky top-0 bg-neutral-800 text-neutral-400 text-sm">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium">Start Time</th>
                    <th className="text-left px-4 py-3 font-medium">End Time</th>
                    <th className="text-left px-4 py-3 font-medium">Callsign</th>
                    <th className="text-left px-4 py-3 font-medium">Mode</th>
                    <th className="text-left px-4 py-3 font-medium">Frequency</th>
                    <th className="text-left px-4 py-3 font-medium">Images</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {mockQSOs.map((qso) => (
                    <tr
                      key={qso.id}
                      onClick={() => setSelectedQSO(qso)}
                      className={`cursor-pointer transition-all border-b border-neutral-800 ${
                        selectedQSO?.id === qso.id ? 'bg-neutral-800' : 'hover:bg-neutral-800/50'
                      } focus-within:ring-2 focus-within:ring-primary-500`}
                      tabIndex={0}
                      role="button"
                      aria-label={`QSO with ${qso.callsign} from ${qso.startTime}`}
                    >
                      <td className="px-4 py-4 tabular-nums font-mono text-xs">{qso.startTime}</td>
                      <td className="px-4 py-4 tabular-nums font-mono text-xs">{qso.endTime}</td>
                      <td className="px-4 py-4 font-medium">{qso.callsign}</td>
                      <td className="px-4 py-4">{qso.mode}</td>
                      <td className="px-4 py-4 tabular-nums">{qso.frequency}</td>
                      <td className="px-4 py-4">{qso.imageCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* QSO Detail Panel */}
          <section className="bg-neutral-900 rounded-lg p-6">
            {selectedQSO ? (
              <>
                <h2 className="text-sm font-medium text-neutral-300 mb-4">QSO Details</h2>
                
                <div className="space-y-3 mb-6">
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Callsign</span>
                    <span className="font-medium">{selectedQSO.callsign}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Mode</span>
                    <span>{selectedQSO.mode}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Frequency</span>
                    <span className="tabular-nums">{selectedQSO.frequency}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-neutral-400 font-medium">Duration</span>
                    <span className="tabular-nums">5m 22s</span>
                  </div>
                </div>

                <div>
                  <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-3">
                    Associated Images ({selectedQSO.imageCount})
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    {Array.from({ length: selectedQSO.imageCount }).map((_, i) => (
                      <div key={i} className="aspect-[4/3] bg-neutral-800 rounded-lg"></div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-neutral-500 text-sm">
                Select a QSO to view details
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}