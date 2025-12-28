import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

interface ConfirmTransmitModalProps {
  isOpen: boolean;
  mode: string;
  duration: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmTransmitModal({
  isOpen,
  mode,
  duration,
  onConfirm,
  onCancel,
}: ConfirmTransmitModalProps) {
  const [countdown, setCountdown] = useState(3);
  const [isPulsing, setIsPulsing] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setCountdown(3);
      setIsPulsing(false);
      return;
    }

    setIsPulsing(true);
    
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      } else if (e.key === 'Enter' && countdown === 0) {
        onConfirm();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, countdown, onConfirm, onCancel]);

  if (!isOpen) return null;

  const currentTime = new Date().toISOString().slice(11, 19) + ' UTC';

  return (
    <div className="fixed inset-0 bg-neutral-950/80 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-neutral-900 border-2 border-secondary-600 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className={`p-2 rounded-lg bg-secondary-700/20 ${isPulsing ? 'animate-pulse' : ''}`}>
            <AlertTriangle className="w-6 h-6 text-secondary-500" />
          </div>
          <div>
            <h2 className="font-medium text-neutral-100">Initiate TX Sequence</h2>
            <div className="text-xs text-neutral-400 font-mono">{currentTime}</div>
          </div>
        </div>

        {/* Transmission Details */}
        <div className="bg-neutral-800 rounded-lg p-4 mb-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-neutral-400">Mode</span>
            <span className="font-medium font-mono">{mode}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-neutral-400">Duration</span>
            <span className="font-medium font-mono">{duration}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-neutral-400">Frequency</span>
            <span className="font-medium font-mono">14.230 MHz</span>
          </div>
        </div>

        {/* Warning */}
        <div className="bg-secondary-900/20 border border-secondary-700/30 rounded-lg p-3 mb-4">
          <p className="text-xs text-secondary-400">
            You are about to transmit on an active frequency. Other operators will yield during your transmission.
          </p>
        </div>

        {/* Countdown */}
        {countdown > 0 ? (
          <div className="text-center mb-4">
            <div className="text-4xl font-mono font-medium text-secondary-500 mb-1">
              {countdown}
            </div>
            <div className="text-xs text-neutral-500">Confirming in...</div>
          </div>
        ) : (
          <div className="text-center mb-4">
            <div className="text-sm text-success-500 font-medium">Ready to transmit</div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 bg-neutral-800 text-neutral-300 rounded-lg hover:bg-neutral-700 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-neutral-900"
          >
            Cancel
            <span className="text-xs opacity-75 ml-2">ESC</span>
          </button>
          <button
            onClick={onConfirm}
            disabled={countdown > 0}
            className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-neutral-900 ${
              countdown > 0
                ? 'bg-neutral-700 text-neutral-500 cursor-not-allowed'
                : 'bg-secondary-600 text-white hover:bg-secondary-700 focus:ring-secondary-500'
            }`}
          >
            Transmit
            {countdown === 0 && <span className="text-xs opacity-75 ml-2">ENTER</span>}
          </button>
        </div>
      </div>
    </div>
  );
}
