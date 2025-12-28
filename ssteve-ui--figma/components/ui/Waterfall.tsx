import { useEffect, useRef, useState } from 'react';

interface WaterfallProps {
  isActive: boolean;
  height?: number;
}

export function Waterfall({ isActive, height = 200 }: WaterfallProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [fftSize, setFftSize] = useState<512 | 1024 | 2048>(1024);
  
  useEffect(() => {
    if (!isActive || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Mock waterfall animation for now
    // TODO: Replace with actual Web Audio API AnalyserNode FFT data
    let animationId: number;
    let scrollOffset = 0;

    const drawWaterfall = () => {
      const width = canvas.width;
      const height = canvas.height;

      // Scroll existing content down
      const imageData = ctx.getImageData(0, 0, width, height - 1);
      ctx.putImageData(imageData, 0, 1);

      // Draw new line at top (mock spectrum data)
      for (let x = 0; x < width; x++) {
        const freq = 300 + (x / width) * 2700; // 300-3000 Hz range
        
        // Mock signal peaks at SSTV frequencies
        let intensity = Math.random() * 30; // Base noise
        
        // Sync pulse at 1200 Hz
        if (Math.abs(freq - 1200) < 20) {
          intensity += 150 + Math.random() * 50;
        }
        // Black level at 1500 Hz
        if (Math.abs(freq - 1500) < 15) {
          intensity += 80 + Math.random() * 30;
        }
        // White level at 2300 Hz
        if (Math.abs(freq - 2300) < 15) {
          intensity += 100 + Math.random() * 40;
        }

        // Convert intensity to color (heat map)
        const r = Math.min(255, intensity * 1.5);
        const g = Math.min(255, intensity * 1.2);
        const b = Math.min(255, intensity * 0.8);
        
        ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
        ctx.fillRect(x, 0, 1, 1);
      }

      scrollOffset++;
      animationId = requestAnimationFrame(drawWaterfall);
    };

    drawWaterfall();

    return () => {
      if (animationId) cancelAnimationFrame(animationId);
    };
  }, [isActive, fftSize]);

  return (
    <div className="bg-neutral-900 rounded-lg overflow-hidden border border-neutral-800">
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-850 border-b border-neutral-800">
        <span className="text-xs font-medium text-neutral-300">Spectrum (300-3000 Hz)</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-neutral-400">FFT:</span>
          <select
            value={fftSize}
            onChange={(e) => setFftSize(Number(e.target.value) as 512 | 1024 | 2048)}
            className="text-xs bg-neutral-800 text-neutral-300 rounded px-2 py-1 border border-neutral-700 focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            <option value={512}>512</option>
            <option value={1024}>1024</option>
            <option value={2048}>2048</option>
          </select>
        </div>
      </div>
      
      <div className="relative" style={{ height }}>
        <canvas
          ref={canvasRef}
          width={800}
          height={height}
          className="w-full h-full"
          style={{ imageRendering: 'pixelated' }}
        />
        
        {/* Frequency markers */}
        <div className="absolute inset-0 pointer-events-none">
          {/* 1200 Hz sync marker */}
          <div 
            className="absolute top-0 bottom-0 w-px bg-primary-500/50"
            style={{ left: `${((1200 - 300) / 2700) * 100}%` }}
          >
            <span className="absolute top-1 left-1 text-xs text-primary-400 bg-neutral-900/80 px-1 rounded">
              1200
            </span>
          </div>
          
          {/* 1500 Hz black marker */}
          <div 
            className="absolute top-0 bottom-0 w-px bg-neutral-400/30"
            style={{ left: `${((1500 - 300) / 2700) * 100}%` }}
          >
            <span className="absolute top-1 left-1 text-xs text-neutral-400 bg-neutral-900/80 px-1 rounded">
              1500
            </span>
          </div>
          
          {/* 2300 Hz white marker */}
          <div 
            className="absolute top-0 bottom-0 w-px bg-neutral-400/30"
            style={{ left: `${((2300 - 300) / 2700) * 100}%` }}
          >
            <span className="absolute top-1 left-1 text-xs text-neutral-400 bg-neutral-900/80 px-1 rounded">
              2300
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
