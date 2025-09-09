import Foundation
import AVFoundation
import Combine

@MainActor
class AudioManager: ObservableObject {
    @Published var isRecording = false
    @Published var audioLevel: Float = 0.0
    @Published var spectrumData: [Float] = Array(repeating: 0.0, count: 512)
    @Published var currentDevice = "Built-in Microphone"
    @Published var availableDevices: [AVAudioDevice] = []
    
    private var audioEngine = AVAudioEngine()
    private var inputNode: AVAudioInputNode?
    private var mixer = AVAudioMixerNode()
    
    // Audio processing
    private let fftSize = 1024
    private var audioBuffer: [Float] = []
    private let bufferSize = 4096
    
    // Data handler for SSTV processor
    var dataHandler: ((Data) -> Void)?
    
    init() {
        setupAudioSession()
        setupAudioEngine()
        discoverAudioDevices()
    }
    
    deinit {
        stopAudioCapture()
    }
    
    // MARK: - Audio Session Setup
    
    private func setupAudioSession() {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.record, mode: .measurement, options: [.allowBluetooth])
            try audioSession.setActive(true)
        } catch {
            print("Failed to setup audio session: \(error)")
        }
    }
    
    // MARK: - Audio Engine Setup
    
    private func setupAudioEngine() {
        audioEngine.attach(mixer)
        
        // Connect mixer to output (for monitoring)
        audioEngine.connect(mixer, to: audioEngine.mainMixerNode, format: nil)
        
        do {
            try audioEngine.start()
        } catch {
            print("Failed to start audio engine: \(error)")
        }
    }
    
    // MARK: - Device Discovery
    
    private func discoverAudioDevices() {
        #if os(macOS)
        // macOS device enumeration
        var deviceID: AudioDeviceID = 0
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        
        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            0,
            nil,
            &size,
            &deviceID
        )
        
        if status == noErr {
            updateCurrentDevice(deviceID: deviceID)
        }
        #endif
    }
    
    #if os(macOS)
    private func updateCurrentDevice(deviceID: AudioDeviceID) {
        var size = UInt32(0)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceName,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        
        AudioObjectGetPropertyDataSize(deviceID, &address, 0, nil, &size)
        
        var name = [CChar](repeating: 0, count: Int(size))
        AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &name)
        
        currentDevice = String(cString: name)
    }
    #endif
    
    // MARK: - Audio Capture Control
    
    func startAudioCapture() {
        guard !isRecording else { return }
        
        inputNode = audioEngine.inputNode
        guard let inputNode = inputNode else {
            print("No input node available")
            return
        }
        
        let inputFormat = inputNode.inputFormat(forBus: 0)
        let recordingFormat = AVAudioFormat(
            standardFormatWithSampleRate: 22050, // SSTV sample rate
            channels: 1
        )
        
        guard let recordingFormat = recordingFormat else {
            print("Failed to create recording format")
            return
        }
        
        // Install tap for audio processing
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, time in
            Task { @MainActor in
                self?.processAudioBuffer(buffer)
            }
        }
        
        // Connect input to mixer for processing
        audioEngine.connect(inputNode, to: mixer, format: inputFormat)
        
        isRecording = true
        print("Audio capture started - Device: \(currentDevice)")
    }
    
    func stopAudioCapture() {
        guard isRecording else { return }
        
        inputNode?.removeTap(onBus: 0)
        audioEngine.disconnectNodeInput(mixer)
        
        isRecording = false
        print("Audio capture stopped")
    }
    
    // MARK: - Audio Processing
    
    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData?[0] else { return }
        let frameCount = Int(buffer.frameLength)
        
        // Update audio level for VU meter
        var sum: Float = 0
        for i in 0..<frameCount {
            sum += abs(channelData[i])
        }
        audioLevel = sum / Float(frameCount)
        
        // Add to audio buffer for spectrum analysis
        for i in 0..<frameCount {
            audioBuffer.append(channelData[i])
        }
        
        // Process when we have enough samples
        if audioBuffer.count >= bufferSize {
            updateSpectrumData()
            
            // Send audio data to SSTV processor
            let audioData = Data(bytes: audioBuffer, count: audioBuffer.count * MemoryLayout<Float>.size)
            dataHandler?(audioData)
            
            // Keep some overlap for continuous processing
            let overlap = bufferSize / 4
            audioBuffer = Array(audioBuffer.suffix(overlap))
        }
    }
    
    private func updateSpectrumData() {
        // Simple FFT approximation for spectrum display
        // In production, this would use Accelerate framework for proper FFT
        let chunkSize = audioBuffer.count / spectrumData.count
        
        for i in 0..<spectrumData.count {
            let startIndex = i * chunkSize
            let endIndex = min(startIndex + chunkSize, audioBuffer.count)
            
            if startIndex < endIndex {
                let chunk = Array(audioBuffer[startIndex..<endIndex])
                let magnitude = chunk.map { abs($0) }.reduce(0, +) / Float(chunk.count)
                spectrumData[i] = magnitude
            }
        }
    }
    
    // MARK: - Device Selection
    
    func selectAudioDevice(_ device: AVAudioDevice) {
        stopAudioCapture()
        
        // Update audio engine input
        // Implementation depends on platform-specific device selection
        
        currentDevice = device.localizedName
        startAudioCapture()
    }
}

// MARK: - Supporting Types

struct AVAudioDevice {
    let id: String
    let localizedName: String
    let isInput: Bool
}

extension AudioManager {
    static let shared = AudioManager()
}