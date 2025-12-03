import { invoke } from '@tauri-apps/api/core';
import { open, save } from '@tauri-apps/plugin-dialog';
import { copyFile, remove } from '@tauri-apps/plugin-fs';
import './style.css';

class Toast {
  constructor(container) {
    this.container = container || this.createContainer();
  }

  createContainer() {
    const div = document.createElement('div');
    div.id = 'toast-container';
    div.className = 'toast-container';
    document.body.appendChild(div);
    return div;
  }

  show(message, type = 'info', duration = 4000) {
    if (!this.container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    this.container.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add('visible');
    });

    setTimeout(() => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
}

class SSTVStation {
  constructor() {
    this.currentMode = 'RECEIVE';
    this.isDecoding = false;
    this.isProcessing = false;
    this.audioContext = null;
    this.audioStream = null;
    this.currentImageData = null;
    this.currentEncodedAudio = null;
    this.progressiveCanvas = null;
    this.progressiveCtx = null;
    this.currentProgress = 0;
    this.decodedImages = [];
    this.galleryIndex = 0;
    this.processingButtonState = {};
    this.toast = null;
    this.recentFiles = [];
    this.maxRecentFiles = 6;
    this.defaultTitle = document.title || 'SSTV Station';
    this.currentFileName = 'None';
    
    this.init();
  }

  async init() {
    this.setupUI();
    this.recentFiles = this.loadRecentFiles();
    this.renderRecentFiles();
    this.setupKeyboardShortcuts();
    this.setupDragAndDrop();
    this.updateDocumentTitle();
    if (!this.hasTauriBridge()) {
      this.updateStatus('Tauri bridge unavailable. Running in browser-only preview.');
      this.loadSSTVModes(true);
    } else {
      await this.checkPythonEngine();
      await this.loadSSTVModes();
    }
    this.setupAudioSystem();
  }

  setupUI() {
    const app = document.querySelector('#app');
    
    app.innerHTML = `
      <div class="sstv-station">
        <!-- Function Button Bank -->
        <div class="function-buttons">
          <button class="function-btn active" data-mode="RECEIVE">
            <span>RECEIVE</span>
            <div class="led active"></div>
          </button>
          <button class="function-btn" data-mode="TRANSMIT">
            <span>TRANSMIT</span>
            <div class="led"></div>
          </button>
          <button class="function-btn" data-mode="GALLERY">
            <span>GALLERY</span>
            <div class="led"></div>
          </button>
          <button class="function-btn" data-mode="SETTINGS">
            <span>SETTINGS</span>
            <div class="led"></div>
          </button>
        </div>

        <div class="main-content">
          <!-- Left Column - VFD Display -->
          <div class="left-column">
            <div class="vfd-display">
              <canvas id="spectrum-canvas" width="460" height="300"></canvas>
              <canvas id="image-canvas" width="460" height="300" style="display: none;"></canvas>
              <canvas id="progressive-canvas" width="460" height="300" style="display: none;"></canvas>
              <div class="scan-lines"></div>
              <div class="status-overlay">
                <span id="status-text">INITIALIZING...</span>
              </div>
              <div class="progress-overlay" style="display: none;">
                <div class="progress-bar">
                  <div id="progress-fill" class="progress-fill"></div>
                </div>
                <span id="progress-text">0%</span>
              </div>
            </div>

            <!-- Image Enhancement Panel -->
            <div id="enhancement-panel" class="enhancement-panel" style="display: none;">
              <div class="enhancement-controls">
                <div class="enhancement-control">
                  <label>CONTRAST</label>
                  <input type="range" id="contrast-slider" min="0.5" max="2.0" value="1.0" step="0.1">
                  <span id="contrast-value">1.0</span>
                </div>
                <div class="enhancement-control">
                  <label>BRIGHTNESS</label>
                  <input type="range" id="brightness-slider" min="-50" max="50" value="0" step="5">
                  <span id="brightness-value">0</span>
                </div>
                <div class="enhancement-control">
                  <label>SATURATION</label>
                  <input type="range" id="saturation-slider" min="0" max="2" value="1" step="0.1">
                  <span id="saturation-value">1.0</span>
                </div>
              </div>
              <div class="enhancement-presets">
                <button class="preset-btn" data-preset="conservative">CONSERVATIVE</button>
                <button class="preset-btn" data-preset="moderate">MODERATE</button>
                <button class="preset-btn" data-preset="aggressive">AGGRESSIVE</button>
                <button class="preset-btn" data-preset="reset">RESET</button>
              </div>
            </div>

            <!-- Manual Adjustment Panel -->
            <div id="adjustment-panel" class="adjustment-panel">
              <div class="adjustment-control">
                <label>SKEW</label>
                <input type="range" id="skew-slider" min="-10" max="10" value="0" step="0.1">
                <span id="skew-value">0.0</span>
              </div>
              <div class="adjustment-control">
                <label>OFFSET</label>
                <input type="range" id="offset-slider" min="-100" max="100" value="0" step="1">
                <span id="offset-value">0</span>
              </div>
            </div>
          </div>

          <!-- Right Column - Controls -->
          <div class="right-column">
            <!-- Audio Level Meter -->
            <div class="audio-meter">
              <div class="meter-bars">
                ${Array.from({length: 20}, (_, i) => `<div class="meter-bar" data-level="${i}"></div>`).join('')}
              </div>
            </div>

            <!-- Spectrum Analyzer -->
            <div class="spectrum-analyzer">
              <canvas id="mini-spectrum" width="220" height="70"></canvas>
            </div>

            <!-- Mode Selector -->
            <div class="mode-selector">
              <div class="auto-mode">
                <input type="checkbox" id="auto-mode" checked>
                <label for="auto-mode">AUTO MODE</label>
              </div>
              <select id="sstv-mode" disabled>
                <option value="ScottieS1">Scottie S1</option>
                <option value="ScottieS2">Scottie S2</option>
                <option value="ScottieDX">Scottie DX</option>
                <option value="MartinM1">Martin M1</option>
                <option value="MartinM2">Martin M2</option>
                <option value="Robot36">Robot 36</option>
              </select>
            </div>

            <!-- Control Buttons -->
            <div class="control-buttons">
              <button id="start-listening" class="control-btn primary">
                START LISTENING
              </button>
              <button id="load-file" class="control-btn">
                LOAD FILE
              </button>
              <button id="encode-audio" class="control-btn" style="display: none;">
                ENCODE AUDIO
              </button>
              <button id="save-audio" class="control-btn" style="display: none;" disabled>
                SAVE AUDIO
              </button>
              <button id="enhance-image" class="control-btn" disabled>
                ENHANCE
              </button>
              <button id="save-image" class="control-btn" disabled>
                SAVE IMAGE
              </button>
              <button id="gallery-prev" class="control-btn gallery-btn" disabled style="display: none;">
                ◀ PREV
              </button>
              <button id="gallery-next" class="control-btn gallery-btn" disabled style="display: none;">
                NEXT ▶
              </button>
            </div>

            <!-- Status Panel -->
            <div class="status-panel">
              <div class="status-header">STATUS</div>
              <div id="processing-indicator" class="processing-indicator" style="display: none;">PROCESSING...</div>
              <div id="detailed-status">Initializing SSTV Station...</div>
              <div class="device-info">
                <span>DEVICE: <span id="audio-device">Built-in Microphone</span></span>
              </div>
              <div class="file-info">
                <span>FILE: <span id="current-file-name">None</span></span>
              </div>
              <div class="recent-files" id="recent-files-section">
                <div class="recent-header">RECENT</div>
                <div id="recent-files-list" class="recent-files-list">
                  <span class="recent-empty">No recent files yet</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div id="toast-container" class="toast-container"></div>
      </div>
    `;

    // Setup event listeners
    this.setupEventListeners();
    this.toast = new Toast(document.getElementById('toast-container'));
  }

  setupEventListeners() {
    // Function buttons
    document.querySelectorAll('.function-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const mode = e.currentTarget.dataset.mode;
        this.setMode(mode);
      });
    });

    // Auto mode toggle
    document.getElementById('auto-mode').addEventListener('change', (e) => {
      const modeSelect = document.getElementById('sstv-mode');
      modeSelect.disabled = e.target.checked;
    });

    // Control buttons
    document.getElementById('start-listening').addEventListener('click', () => {
      this.toggleListening();
    });

    document.getElementById('load-file').addEventListener('click', () => {
      this.loadAudioFile();
    });

    document.getElementById('enhance-image').addEventListener('click', () => {
      this.toggleImageEnhancement();
    });

    document.getElementById('save-image').addEventListener('click', () => {
      this.saveCurrentImage();
    });

    document.getElementById('encode-audio').addEventListener('click', () => {
      this.encodeFromImage();
    });

    document.getElementById('save-audio').addEventListener('click', () => {
      this.saveEncodedAudio();
    });

    document.getElementById('gallery-prev').addEventListener('click', () => {
      this.navigateGallery(-1);
    });

    document.getElementById('gallery-next').addEventListener('click', () => {
      this.navigateGallery(1);
    });

    // Enhancement sliders
    document.getElementById('contrast-slider').addEventListener('input', (e) => {
      document.getElementById('contrast-value').textContent = parseFloat(e.target.value).toFixed(1);
      this.applyImageEnhancements();
    });

    document.getElementById('brightness-slider').addEventListener('input', (e) => {
      document.getElementById('brightness-value').textContent = e.target.value;
      this.applyImageEnhancements();
    });

    document.getElementById('saturation-slider').addEventListener('input', (e) => {
      document.getElementById('saturation-value').textContent = parseFloat(e.target.value).toFixed(1);
      this.applyImageEnhancements();
    });

    // Enhancement presets
    document.querySelectorAll('.preset-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this.applyEnhancementPreset(e.target.dataset.preset);
      });
    });

    // Manual adjustment sliders
    document.getElementById('skew-slider').addEventListener('input', (e) => {
      document.getElementById('skew-value').textContent = parseFloat(e.target.value).toFixed(1);
    });

    document.getElementById('offset-slider').addEventListener('input', (e) => {
      document.getElementById('offset-value').textContent = e.target.value;
    });
  }

  setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => this.handleKeyDown(e));
  }

  handleKeyDown(e) {
    const targetTag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
    if (targetTag === 'input' || targetTag === 'textarea') return;

    const isOpenShortcut = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'o';
    const isSaveShortcut = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's';

    if (isOpenShortcut) {
      e.preventDefault();
      if (this.isProcessing) return;
      if (this.currentMode === 'TRANSMIT') {
        this.encodeFromImage();
      } else {
        this.loadAudioFile();
      }
    }

    if (isSaveShortcut) {
      e.preventDefault();
      if (this.isProcessing) return;
      if (this.currentMode === 'TRANSMIT' && this.currentEncodedAudio) {
        this.saveEncodedAudio();
      } else if (this.currentImageData) {
        this.saveCurrentImage();
      } else if (this.toast) {
        this.toast.show('Nothing to save yet', 'info');
      }
    }
  }

  setupDragAndDrop() {
    const root = document.querySelector('.sstv-station');
    if (!root) return;

    const addHighlight = (event) => {
      event.preventDefault();
      root.classList.add('drag-over');
    };
    const removeHighlight = (event) => {
      event.preventDefault();
      root.classList.remove('drag-over');
    };

    ['dragenter', 'dragover'].forEach(eventName => {
      root.addEventListener(eventName, addHighlight);
    });
    ['dragleave', 'dragend'].forEach(eventName => {
      root.addEventListener(eventName, removeHighlight);
    });

    root.addEventListener('drop', (event) => {
      event.preventDefault();
      root.classList.remove('drag-over');

      if (!event.dataTransfer || !event.dataTransfer.files || event.dataTransfer.files.length === 0) {
        return;
      }

      const file = event.dataTransfer.files[0];
      const filePath = file.path || file.name;
      const fileName = file.name || this.extractFileName(filePath);

      if (!filePath) {
        if (this.toast) this.toast.show('File path unavailable in this environment', 'error');
        return;
      }

      this.handleDroppedFile(filePath, fileName);
    });
  }

  handleDroppedFile(filePath, fileName) {
    const fileType = this.detectFileType(filePath);
    if (!fileType) {
      if (this.toast) this.toast.show('Unsupported file type', 'error');
      return;
    }

    if (!this.hasTauriBridge()) {
      if (this.toast) this.toast.show('Drag-and-drop works in the desktop app', 'info');
      return;
    }

    if (fileType === 'audio') {
      this.setMode('RECEIVE');
      this.loadAudioFile(filePath, fileName);
    } else if (fileType === 'image') {
      this.setMode('TRANSMIT');
      this.encodeFromImage(filePath, fileName);
    }
  }

  detectFileType(path) {
    const lowered = path.toLowerCase();
    const audioExt = ['.wav', '.mp3', '.ogg', '.flac'];
    const imageExt = ['.png', '.jpg', '.jpeg', '.bmp'];

    if (audioExt.some(ext => lowered.endsWith(ext))) return 'audio';
    if (imageExt.some(ext => lowered.endsWith(ext))) return 'image';
    return null;
  }

  setCurrentFileName(name) {
    this.currentFileName = name || 'None';
    const label = document.getElementById('current-file-name');
    if (label) label.textContent = this.currentFileName;
    this.updateDocumentTitle();
  }

  updateDocumentTitle() {
    document.title = (this.currentFileName && this.currentFileName !== 'None')
      ? `${this.defaultTitle} - ${this.currentFileName}`
      : this.defaultTitle;
  }

  loadRecentFiles() {
    try {
      const stored = window.localStorage.getItem('sstv-recent-files');
      const parsed = stored ? JSON.parse(stored) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      console.error('Failed to load recent files', error);
      return [];
    }
  }

  persistRecentFiles() {
    try {
      window.localStorage.setItem('sstv-recent-files', JSON.stringify(this.recentFiles));
    } catch (error) {
      console.error('Failed to persist recent files', error);
    }
  }

  addRecentFile(path, name, type) {
    if (!path) return;
    const entry = {
      path,
      name: name || this.extractFileName(path),
      type
    };

    this.recentFiles = [
      entry,
      ...this.recentFiles.filter(item => item.path !== path)
    ].slice(0, this.maxRecentFiles);

    this.persistRecentFiles();
    this.renderRecentFiles();
  }

  renderRecentFiles() {
    const list = document.getElementById('recent-files-list');
    if (!list) return;

    list.innerHTML = '';
    if (!this.recentFiles || this.recentFiles.length === 0) {
      const empty = document.createElement('span');
      empty.className = 'recent-empty';
      empty.textContent = 'No recent files yet';
      list.appendChild(empty);
      return;
    }

    this.recentFiles.forEach(item => {
      const btn = document.createElement('button');
      btn.className = 'recent-file-btn';
      btn.textContent = item.name || this.extractFileName(item.path);
      btn.title = item.path;
      btn.addEventListener('click', () => {
        if (item.type === 'audio') {
          this.setMode('RECEIVE');
          this.loadAudioFile(item.path, item.name);
        } else if (item.type === 'image') {
          this.setMode('TRANSMIT');
          this.encodeFromImage(item.path, item.name);
        }
      });
      list.appendChild(btn);
    });
  }

  setMode(mode) {
    this.currentMode = mode;
    
    // Update button states
    document.querySelectorAll('.function-btn').forEach(btn => {
      const isActive = btn.dataset.mode === mode;
      btn.classList.toggle('active', isActive);
      btn.querySelector('.led').classList.toggle('active', isActive);
    });

    // Show/hide mode-specific panels
    this.updateModeDisplay(mode);

    // Update status
    const statusMessages = {
      'RECEIVE': 'QRV - Listening for SSTV signals',
      'TRANSMIT': 'Transmit mode - Select image to encode', 
      'GALLERY': 'Gallery - Browse decoded images',
      'SETTINGS': 'Settings - Configure SSTV Station'
    };
    
    this.updateStatus(statusMessages[mode] || 'Mode selected');
  }

  updateModeDisplay(mode) {
    const enhancementPanel = document.getElementById('enhancement-panel');
    const adjustmentPanel = document.getElementById('adjustment-panel');
    const galleryBtns = document.querySelectorAll('.gallery-btn');
    const enhanceBtn = document.getElementById('enhance-image');
    const saveAudioBtn = document.getElementById('save-audio');
    
    // Reset display states
    enhancementPanel.style.display = 'none';
    adjustmentPanel.style.display = 'block';
    galleryBtns.forEach(btn => btn.style.display = 'none');
    
    switch(mode) {
      case 'RECEIVE':
        this.showSpectrumView();
        document.getElementById('encode-audio').style.display = 'none';
        saveAudioBtn.style.display = 'none';
        break;
      case 'TRANSMIT':
        document.getElementById('encode-audio').style.display = 'inline-block';
        if (this.currentEncodedAudio) {
          saveAudioBtn.style.display = 'inline-block';
          saveAudioBtn.disabled = false;
        } else {
          saveAudioBtn.style.display = 'none';
        }
        break;
      case 'GALLERY':
        this.showGalleryView();
        galleryBtns.forEach(btn => btn.style.display = 'inline-block');
        this.updateGalleryControls();
        saveAudioBtn.style.display = 'none';
        break;
      case 'SETTINGS':
        // Settings mode specific UI
        saveAudioBtn.style.display = 'none';
        break;
    }
  }

  async checkPythonEngine() {
    if (!this.hasTauriBridge()) {
      this.updateStatus('Tauri bridge unavailable in browser preview');
      return;
    }

    try {
      const result = await invoke('check_python_engine');
      if (result.success) {
        this.updateStatus('SSTV engine ready - QRV');
      } else {
        this.updateStatus(`Engine error: ${result.message}`);
      }
    } catch (error) {
      this.updateStatus(`Failed to check engine: ${error}`);
    }
  }

  async loadSSTVModes(forceDefaults = false) {
    const select = document.getElementById('sstv-mode');
    if (!select) return;

    const setOptions = (modes) => {
      select.innerHTML = '';
      modes.forEach(mode => {
        const option = document.createElement('option');
        option.value = mode;
        option.textContent = this.formatModeName(mode);
        select.appendChild(option);
      });
    };

    if (forceDefaults || !this.hasTauriBridge()) {
      setOptions(this.defaultModes());
      return;
    }

    try {
      const modes = await invoke('get_sstv_modes');
      setOptions(modes);
    } catch (error) {
      console.error('Failed to load SSTV modes:', error);
      setOptions(this.defaultModes());
    }
  }

  formatModeName(mode) {
    const names = {
      'ScottieS1': 'Scottie S1',
      'ScottieS2': 'Scottie S2', 
      'ScottieDX': 'Scottie DX',
      'MartinM1': 'Martin M1',
      'MartinM2': 'Martin M2',
      'Robot36': 'Robot 36'
    };
    return names[mode] || mode;
  }

  defaultModes() {
    return [
      'ScottieS1',
      'ScottieS2',
      'ScottieDX',
      'MartinM1',
      'MartinM2',
      'Robot36'
    ];
  }

  hasTauriBridge() {
    return typeof window !== 'undefined' &&
      window.__TAURI_INTERNALS__ &&
      typeof window.__TAURI_INTERNALS__.invoke === 'function';
  }

  async setupAudioSystem() {
    try {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 22050 // SSTV standard sample rate
      });
      
      this.updateStatus('Audio system initialized');
    } catch (error) {
      this.updateStatus(`Audio error: ${error.message}`);
    }
  }

  async toggleListening() {
    const btn = document.getElementById('start-listening');
    
    if (!this.isDecoding) {
      try {
        // Request microphone access
        this.audioStream = await navigator.mediaDevices.getUserMedia({ 
          audio: {
            sampleRate: 22050,
            channelCount: 1,
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false
          } 
        });
        
        // Setup audio processing
        this.setupAudioProcessing();
        
        this.isDecoding = true;
        btn.textContent = 'STOP LISTENING';
        btn.classList.add('stop');
        this.showProgressiveView();
        this.updateProgress(0, 'Listening for SSTV signals...');
        
        // Simulate progressive rendering during real-time decode
        this.startProgressSimulation();
        
      } catch (error) {
        this.updateStatus(`Microphone error: ${error.message}`);
      }
    } else {
      // Stop listening
      if (this.audioStream) {
        this.audioStream.getTracks().forEach(track => track.stop());
        this.audioStream = null;
      }
      
      this.isDecoding = false;
      btn.textContent = 'START LISTENING';
      btn.classList.remove('stop');
      this.showSpectrumView();
      this.updateStatus('QRV - Ready to listen');
      
      // Stop progress simulation
      if (this.progressInterval) {
        clearInterval(this.progressInterval);
        this.progressInterval = null;
      }
    }
  }

  startProgressSimulation() {
    if (this.progressInterval) {
      clearInterval(this.progressInterval);
    }
    
    let progress = 0;
    const targetHeight = 256; // Standard SSTV height
    
    this.progressInterval = setInterval(() => {
      progress += Math.random() * 2 + 0.5; // Variable progress rate
      
      if (progress >= 100) {
        progress = 100;
        clearInterval(this.progressInterval);
        this.progressInterval = null;
        
        // Simulate completed decode
        setTimeout(() => {
          this.updateStatus('Signal detected - decoding complete');
          this.showSpectrumView();
        }, 1000);
      }
      
      this.updateProgress(progress, `Decoding line ${Math.floor((progress/100) * targetHeight)} of ${targetHeight}`);
      this.renderProgressiveLine(progress / 100);
      
    }, 100); // Update every 100ms
  }

  renderProgressiveLine(progressRatio) {
    if (!this.progressiveCtx) return;
    
    const canvas = document.getElementById('progressive-canvas');
    const ctx = this.progressiveCtx;
    
    // Clear canvas with black background
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw progressive scan lines
    const currentLine = Math.floor(progressRatio * 256);
    
    // Simulate SSTV image data with noise and color bands
    for (let y = 0; y < currentLine; y++) {
      const lineProgress = y / 256;
      
      // Create color bands mimicking SSTV signals
      const hue = (y * 2) % 360;
      const noise = Math.random() * 0.3;
      const brightness = 0.5 + Math.sin(lineProgress * Math.PI * 4) * 0.3 + noise;
      
      ctx.fillStyle = `hsl(${hue}, 70%, ${brightness * 50}%)`;
      
      // Draw scan line
      const lineHeight = canvas.height / 256;
      ctx.fillRect(50, y * lineHeight, canvas.width - 100, lineHeight);
      
      // Add some horizontal sync artifacts
      if (y % 32 === 0) {
        ctx.fillStyle = '#00ff41';
        ctx.fillRect(0, y * lineHeight, canvas.width, 1);
      }
    }
    
    // Add scan lines effect
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#00ff41';
    for (let scanY = 0; scanY < canvas.height; scanY += 4) {
      ctx.fillRect(0, scanY, canvas.width, 1);
    }
    ctx.globalAlpha = 1.0;
  }

  setupAudioProcessing() {
    if (!this.audioContext || !this.audioStream) return;

    const source = this.audioContext.createMediaStreamSource(this.audioStream);
    const analyser = this.audioContext.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.8;

    source.connect(analyser);

    // Start spectrum visualization
    this.startSpectrumVisualization(analyser);
    
    // Start audio level monitoring  
    this.startAudioLevelMonitoring(analyser);
  }

  startSpectrumVisualization(analyser) {
    const canvas = document.getElementById('spectrum-canvas');
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      requestAnimationFrame(draw);
      
      analyser.getByteFrequencyData(dataArray);
      
      // Clear canvas with VFD background
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // Draw spectrum
      ctx.fillStyle = '#00ff41';
      ctx.globalAlpha = 0.8;
      
      const barWidth = canvas.width / bufferLength;
      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * canvas.height;
        ctx.fillRect(i * barWidth, canvas.height - barHeight, barWidth, barHeight);
      }
      
      // Add scan lines effect
      ctx.globalAlpha = 0.1;
      ctx.fillStyle = '#00ff41';
      for (let y = 0; y < canvas.height; y += 4) {
        ctx.fillRect(0, y, canvas.width, 1);
      }
      ctx.globalAlpha = 1.0;
    };

    draw();
  }

  startAudioLevelMonitoring(analyser) {
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const updateLevel = () => {
      requestAnimationFrame(updateLevel);
      
      analyser.getByteFrequencyData(dataArray);
      
      // Calculate RMS level
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i] * dataArray[i];
      }
      const rms = Math.sqrt(sum / bufferLength) / 255;
      
      // Update meter bars
      const meterBars = document.querySelectorAll('.meter-bar');
      meterBars.forEach((bar, index) => {
        const threshold = index / 20;
        const isActive = rms > threshold;
        
        bar.classList.toggle('active', isActive);
        
        if (isActive) {
          if (index < 14) bar.style.backgroundColor = '#00ff41';
          else if (index < 18) bar.style.backgroundColor = '#ffaa00'; 
          else bar.style.backgroundColor = '#ff4444';
        } else {
          bar.style.backgroundColor = '#222';
        }
      });
    };

    updateLevel();
  }

  async loadAudioFile(filePathOverride = null, providedName = null) {
    if (!this.hasTauriBridge()) {
      this.updateStatus('Tauri bridge unavailable; file load disabled in browser preview');
      if (this.toast) this.toast.show('File load only works in Tauri app', 'info');
      return;
    }

    let filePath = filePathOverride;
    let fileName = providedName || (filePath ? this.extractFileName(filePath) : null);

    if (!filePath) {
      const selected = await open({
        multiple: false,
        filters: [{
          name: 'Audio Files',
          extensions: ['wav', 'mp3', 'ogg', 'flac']
        }]
      });

      if (!selected) return;
      filePath = typeof selected === 'string' ? selected : selected.path || selected;
      fileName = (typeof selected === 'object' && selected.name) ? selected.name : this.extractFileName(filePath);
    }

    if (!filePath) return;
    await this.decodeAudioFile(filePath, fileName);
  }

  async decodeAudioFile(filePath, fileName) {
    try {
      this.setCurrentFileName(fileName || this.extractFileName(filePath));
      this.updateStatus(`Loading file: ${this.currentFileName}`);

      this.showProgressiveView();
      this.updateProgress(0, 'Starting decode...');
      this.setProcessing(true, 'Decoding audio...');

      const result = await invoke('decode_sstv_file', { audioPath: filePath });

      if (result.success) {
        const endMsg = result.message ? result.message : 'Decode complete';
        this.updateProgress(100, endMsg);

        // Brief delay to show completion
        setTimeout(async () => {
          if (result.image_path) {
            await this.displayDecodedImage(result.image_path);
          }
        }, 500);
        this.addRecentFile(filePath, this.currentFileName, 'audio');
        if (this.toast) this.toast.show('Decode complete', 'success');
      } else {
        this.updateStatus(`Decode failed: ${result.message}`);
        this.showSpectrumView();
        if (this.toast) this.toast.show(`Decode failed: ${result.message}`, 'error');
      }
    } catch (error) {
      this.updateStatus(`File load error: ${error}`);
      if (this.toast) this.toast.show('File load error', 'error');
    } finally {
      this.setProcessing(false);
    }
  }

  async displayDecodedImage(imagePath) {
    const img = new Image();
    img.onload = () => {
      this.currentImageData = {
        image: img,
        path: imagePath,
        originalData: null
      };
      
      // Add to gallery
      this.decodedImages.push(this.currentImageData);
      this.galleryIndex = this.decodedImages.length - 1;
      
      // Show image view
      this.showImageView();
      this.renderCurrentImage();
      
      // Enable controls
      document.getElementById('save-image').disabled = false;
      document.getElementById('enhance-image').disabled = false;
    };
    
    img.src = `file://${imagePath}`;
  }

  showSpectrumView() {
    const spectrumCanvas = document.getElementById('spectrum-canvas');
    const imageCanvas = document.getElementById('image-canvas');
    const progressiveCanvas = document.getElementById('progressive-canvas');
    
    spectrumCanvas.style.display = 'block';
    imageCanvas.style.display = 'none';
    progressiveCanvas.style.display = 'none';
    document.querySelector('.progress-overlay').style.display = 'none';
  }

  showImageView() {
    const spectrumCanvas = document.getElementById('spectrum-canvas');
    const imageCanvas = document.getElementById('image-canvas');
    const progressiveCanvas = document.getElementById('progressive-canvas');
    
    spectrumCanvas.style.display = 'none';
    imageCanvas.style.display = 'block';
    progressiveCanvas.style.display = 'none';
    document.querySelector('.progress-overlay').style.display = 'none';
  }

  showProgressiveView() {
    const spectrumCanvas = document.getElementById('spectrum-canvas');
    const imageCanvas = document.getElementById('image-canvas');
    const progressiveCanvas = document.getElementById('progressive-canvas');
    
    spectrumCanvas.style.display = 'none';
    imageCanvas.style.display = 'none';
    progressiveCanvas.style.display = 'block';
    document.querySelector('.progress-overlay').style.display = 'block';
    
    // Initialize progressive canvas
    if (!this.progressiveCtx) {
      this.progressiveCtx = progressiveCanvas.getContext('2d');
    }
  }

  showGalleryView() {
    if (this.decodedImages.length > 0) {
      this.showImageView();
      this.renderCurrentImage();
    } else {
      this.showSpectrumView();
    }
  }

  updateStatus(message) {
    document.getElementById('status-text').textContent = message;
    document.getElementById('detailed-status').textContent = message;
  }

  setProcessing(isProcessing, message) {
    this.isProcessing = isProcessing;
    const indicator = document.getElementById('processing-indicator');
    const buttons = [
      'start-listening',
      'load-file',
      'encode-audio',
      'save-audio',
      'enhance-image',
      'save-image',
      'gallery-prev',
      'gallery-next'
    ];

    if (isProcessing) {
      this.processingButtonState = {};
      buttons.forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
          this.processingButtonState[id] = btn.disabled;
          btn.disabled = true;
          btn.classList.add('processing');
        }
      });
      if (indicator) indicator.style.display = 'block';
      if (message) this.updateStatus(message);
    } else {
      buttons.forEach(id => {
        const btn = document.getElementById(id);
        if (btn && Object.prototype.hasOwnProperty.call(this.processingButtonState, id)) {
          btn.disabled = this.processingButtonState[id];
          btn.classList.remove('processing');
        }
      });
      this.processingButtonState = {};
      if (indicator) indicator.style.display = 'none';
    }
  }

  toggleImageEnhancement() {
    const enhancementPanel = document.getElementById('enhancement-panel');
    const adjustmentPanel = document.getElementById('adjustment-panel');
    
    if (enhancementPanel.style.display === 'none') {
      enhancementPanel.style.display = 'block';
      adjustmentPanel.style.display = 'none';
      this.updateStatus('Image enhancement controls active');
    } else {
      enhancementPanel.style.display = 'none';
      adjustmentPanel.style.display = 'block';
      this.updateStatus('Manual adjustment controls active');
    }
  }

  applyEnhancementPreset(preset) {
    const presets = {
      conservative: { contrast: 1.1, brightness: 5, saturation: 1.1 },
      moderate: { contrast: 1.3, brightness: 10, saturation: 1.2 },
      aggressive: { contrast: 1.5, brightness: 15, saturation: 1.4 },
      reset: { contrast: 1.0, brightness: 0, saturation: 1.0 }
    };
    
    const values = presets[preset];
    if (values) {
      document.getElementById('contrast-slider').value = values.contrast;
      document.getElementById('brightness-slider').value = values.brightness;
      document.getElementById('saturation-slider').value = values.saturation;
      
      document.getElementById('contrast-value').textContent = values.contrast.toFixed(1);
      document.getElementById('brightness-value').textContent = values.brightness;
      document.getElementById('saturation-value').textContent = values.saturation.toFixed(1);
      
      this.applyImageEnhancements();
      this.updateStatus(`Applied ${preset} enhancement preset`);
    }
  }

  applyImageEnhancements() {
    if (!this.currentImageData) return;
    
    const contrast = parseFloat(document.getElementById('contrast-slider').value);
    const brightness = parseInt(document.getElementById('brightness-slider').value);
    const saturation = parseFloat(document.getElementById('saturation-slider').value);
    
    // Apply CSS filters to the canvas
    const imageCanvas = document.getElementById('image-canvas');
    imageCanvas.style.filter = `contrast(${contrast}) brightness(${1 + brightness/100}) saturate(${saturation})`;
  }

  renderCurrentImage() {
    if (!this.currentImageData) return;
    
    const imageCanvas = document.getElementById('image-canvas');
    const ctx = imageCanvas.getContext('2d');
    const img = this.currentImageData.image;
    
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, imageCanvas.width, imageCanvas.height);
    
    // Scale image to fit canvas while maintaining aspect ratio
    const scale = Math.min(imageCanvas.width / img.width, imageCanvas.height / img.height);
    const scaledWidth = img.width * scale;
    const scaledHeight = img.height * scale;
    const x = (imageCanvas.width - scaledWidth) / 2;
    const y = (imageCanvas.height - scaledHeight) / 2;
    
    ctx.drawImage(img, x, y, scaledWidth, scaledHeight);
    
    // Add scan lines effect
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#00ff41';
    for (let scanY = 0; scanY < imageCanvas.height; scanY += 4) {
      ctx.fillRect(0, scanY, imageCanvas.width, 1);
    }
    ctx.globalAlpha = 1.0;
  }

  navigateGallery(direction) {
    if (this.decodedImages.length === 0) return;
    
    this.galleryIndex += direction;
    if (this.galleryIndex < 0) this.galleryIndex = this.decodedImages.length - 1;
    if (this.galleryIndex >= this.decodedImages.length) this.galleryIndex = 0;
    
    this.currentImageData = this.decodedImages[this.galleryIndex];
    this.renderCurrentImage();
    this.updateGalleryControls();
    
    this.updateStatus(`Gallery: Image ${this.galleryIndex + 1} of ${this.decodedImages.length}`);
  }

  updateGalleryControls() {
    const prevBtn = document.getElementById('gallery-prev');
    const nextBtn = document.getElementById('gallery-next');
    
    const hasImages = this.decodedImages.length > 0;
    const hasMultiple = this.decodedImages.length > 1;
    
    prevBtn.disabled = !hasMultiple;
    nextBtn.disabled = !hasMultiple;
  }

  updateProgress(progress, message) {
    this.currentProgress = progress;
    
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${Math.round(progress)}%`;
    
    if (message) {
      this.updateStatus(message);
    }
  }

  async saveCurrentImage() {
    if (!this.hasTauriBridge()) {
      this.updateStatus('Save requires Tauri bridge');
      if (this.toast) this.toast.show('Save is only available in the desktop app', 'info');
      return;
    }

    if (!this.currentImageData) {
      this.updateStatus('No image to save');
      return;
    }
    
    try {
      // Use Tauri dialog to save file
      const result = await invoke('save_image_dialog', {
        imagePath: this.currentImageData.path
      });
      
      if (result.success) {
        this.updateStatus('Image saved successfully');
      } else {
        this.updateStatus('Failed to save image');
      }
    } catch (error) {
      this.updateStatus(`Save error: ${error}`);
    }
  }

  async encodeFromImage(filePathOverride = null, providedName = null) {
    if (!this.hasTauriBridge()) {
      this.updateStatus('Tauri bridge unavailable; encode disabled in browser preview');
      if (this.toast) this.toast.show('Encode only works in the desktop app', 'info');
      return;
    }

    let filePath = filePathOverride;
    let fileName = providedName || (filePath ? this.extractFileName(filePath) : null);

    if (!filePath) {
      const selected = await open({
        multiple: false,
        filters: [{
          name: 'Image Files',
          extensions: ['png', 'jpg', 'jpeg', 'bmp']
        }]
      });

      if (!selected) return;

      filePath = typeof selected === 'string' ? selected : selected.path || selected;
      fileName = (typeof selected === 'object' && selected.name) ? selected.name : this.extractFileName(filePath);
    }

    if (!filePath) return;
    await this.encodeImage(filePath, fileName);
  }

  async encodeImage(filePath, fileName) {
    try {
      const modeSelect = document.getElementById('sstv-mode');
      const mode = modeSelect.value || 'ScottieS1';
      this.currentEncodedAudio = null;
      const saveAudioBtn = document.getElementById('save-audio');
      if (saveAudioBtn) {
        saveAudioBtn.disabled = true;
        saveAudioBtn.style.display = 'none';
      }

      this.setCurrentFileName(fileName || this.extractFileName(filePath));
      this.updateStatus(`Encoding ${this.currentFileName} as ${this.formatModeName(mode)}...`);
      this.setProcessing(true, 'Encoding image to audio...');

      const result = await invoke('encode_sstv_image', {
        imagePath: filePath,
        mode
      });

      if (result.success && result.audio_path) {
        this.currentEncodedAudio = {
          path: result.audio_path,
          fileName: this.extractFileName(result.audio_path)
        };
        this.revealSaveAudioButton();
        this.updateStatus(`Encode complete: ${this.currentEncodedAudio.fileName}`);
        this.addRecentFile(filePath, this.currentFileName, 'image');
        if (this.toast) this.toast.show('Encode complete. Save the audio file.', 'success');
      } else if (result.success) {
        this.updateStatus('Encode complete.');
        if (this.toast) this.toast.show('Encode complete', 'success');
      } else {
        this.updateStatus(`Encode failed: ${result.message}`);
        if (this.toast) this.toast.show(`Encode failed: ${result.message}`, 'error');
      }
    } catch (error) {
      this.updateStatus(`Encode error: ${error}`);
      if (this.toast) this.toast.show('Encode error', 'error');
    } finally {
      this.setProcessing(false);
    }
  }

  revealSaveAudioButton() {
    const btn = document.getElementById('save-audio');
    if (btn) {
      btn.style.display = 'inline-block';
      btn.disabled = false;
    }
  }

  extractFileName(path) {
    return path ? (path.split(/[\\/]/).pop() || 'sstv_audio.wav') : 'sstv_audio.wav';
  }

  async saveEncodedAudio() {
    if (!this.currentEncodedAudio || !this.currentEncodedAudio.path) {
      if (this.toast) this.toast.show('No encoded audio available', 'info');
      return;
    }

    const suggestedName = this.currentEncodedAudio.fileName || 'sstv_audio.wav';
    const destination = await save({
      defaultPath: suggestedName,
      filters: [{ name: 'Wave Audio', extensions: ['wav'] }]
    });

    if (!destination) {
      this.updateStatus('Save canceled');
      return;
    }

    try {
      this.setProcessing(true, 'Saving audio file...');
      await copyFile(this.currentEncodedAudio.path, destination);
      if (destination !== this.currentEncodedAudio.path) {
        await remove(this.currentEncodedAudio.path).catch(() => {});
      }
      this.currentEncodedAudio.path = destination;
      if (this.toast) this.toast.show('Audio saved successfully', 'success');
      this.updateStatus(`Audio saved: ${destination}`);

      const saveBtn = document.getElementById('save-audio');
      if (saveBtn) saveBtn.disabled = true;
    } catch (error) {
      this.updateStatus(`Save failed: ${error}`);
      if (this.toast) this.toast.show('Failed to save audio', 'error');
    } finally {
      this.setProcessing(false);
    }
  }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
  new SSTVStation();
});
