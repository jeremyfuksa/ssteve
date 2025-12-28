// Breathing void - visual indication of readiness to receive
interface ScanLinesProps {
  speed?: 'slow' | 'normal' | 'fast' | 'stopped';
}

export function ScanLines({ speed = 'slow' }: ScanLinesProps) {
  const animationDuration = speed === 'fast' ? '4s' : speed === 'normal' ? '6s' : speed === 'stopped' ? '0s' : '8s';
  
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {/* Slow vertical scan lines suggesting active listening state */}
      <div className="scan-line-container">
        <div className="scan-line" style={{ animationDelay: '0s', animationDuration }} />
        <div className="scan-line" style={{ animationDelay: '2s', animationDuration }} />
        <div className="scan-line" style={{ animationDelay: '4s', animationDuration }} />
      </div>
      
      <style>{`
        .scan-line-container {
          position: absolute;
          inset: 0;
        }
        
        .scan-line {
          position: absolute;
          top: -2px;
          left: 0;
          right: 0;
          height: 1px;
          background: linear-gradient(
            to bottom,
            transparent,
            rgba(172, 187, 204, 0.15),
            transparent
          );
          box-shadow: 0 0 4px rgba(172, 187, 204, 0.1);
          animation: scan linear infinite;
          will-change: transform;
        }
        
        @keyframes scan {
          0% {
            transform: translateY(0);
            opacity: 0;
          }
          5% {
            opacity: 1;
          }
          95% {
            opacity: 1;
          }
          100% {
            transform: translateY(100vh);
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
}