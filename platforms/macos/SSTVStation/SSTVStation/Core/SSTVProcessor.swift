import Foundation
import Combine

@MainActor
class SSTVProcessor: ObservableObject {
    @Published var currentMode: SSTVMode = .receive
    @Published var selectedMode = "ScottieS1"
    @Published var autoMode = true
    @Published var status = "Initializing..."
    @Published var imageData: Data?
    @Published var skewAdjustment: Double = 0.0
    @Published var offsetAdjustment: Double = 0.0
    
    // Processing state
    @Published var isDecoding = false
    @Published var decodingProgress: Float = 0.0
    @Published var detectedVISCode: Int?
    
    private var pythonBridge: PythonBridge?
    private var audioDataQueue: [Data] = []
    private let maxQueueSize = 10
    
    // Audio processing
    private var isProcessingAudio = false
    private let processingQueue = DispatchQueue(label: "sstv.processing", qos: .userInitiated)
    
    init() {
        status = "Ready to initialize Python bridge"
    }
    
    // MARK: - Initialization
    
    func initializePythonBridge() {
        Task {
            do {
                pythonBridge = try PythonBridge()
                await pythonBridge?.initialize()
                status = "QRV - Listening for SSTV signals"
            } catch {
                status = "Error: Failed to initialize Python engine - \(error.localizedDescription)"
                print("Python bridge initialization failed: \(error)")
            }
        }
    }
    
    // MARK: - Audio Data Processing
    
    func processAudioData(_ data: Data) {
        // Queue audio data for processing
        audioDataQueue.append(data)
        
        // Limit queue size to prevent memory issues
        if audioDataQueue.count > maxQueueSize {
            audioDataQueue.removeFirst()
        }
        
        // Process if not already processing
        if !isProcessingAudio {
            processQueuedAudio()
        }
    }
    
    private func processQueuedAudio() {
        guard !audioDataQueue.isEmpty else { return }
        
        isProcessingAudio = true
        
        processingQueue.async { [weak self] in
            guard let self = self else { return }
            
            // Combine queued audio data
            let combinedData = self.audioDataQueue.reduce(Data()) { $0 + $1 }
            self.audioDataQueue.removeAll()
            
            Task { @MainActor in
                await self.processAudioInPython(combinedData)
                self.isProcessingAudio = false
                
                // Process more if queue has accumulated
                if !self.audioDataQueue.isEmpty {
                    self.processQueuedAudio()
                }
            }
        }
    }
    
    private func processAudioInPython(_ audioData: Data) async {
        guard let pythonBridge = pythonBridge else {
            status = "Error: Python bridge not initialized"
            return
        }
        
        do {
            let result = try await pythonBridge.processAudioStream(audioData)
            await handleProcessingResult(result)
        } catch {
            status = "Processing error: \(error.localizedDescription)"
            print("Audio processing error: \(error)")
        }
    }
    
    private func handleProcessingResult(_ result: SSTVProcessingResult) async {
        switch result.type {
        case .spectrum:
            // Spectrum data for visualization - handled by AudioManager
            if !isDecoding {
                status = "QRV - Listening on \(getCurrentDeviceName())"
            }
            
        case .visDetected:
            if let visCode = result.visCode {
                detectedVISCode = visCode
                let detectedMode = SSTVModeDetector.modeFromVIS(visCode)
                
                if autoMode {
                    selectedMode = detectedMode
                }
                
                isDecoding = true
                decodingProgress = 0.0
                status = "Signal detected - Decoding \(detectedMode)"
            }
            
        case .lineData:
            // Progressive image update
            if let lineData = result.imageData {
                updateProgressiveImage(lineData)
                decodingProgress = result.progress
                status = "Decoding \(selectedMode) - \(Int(decodingProgress * 100))%"
            }
            
        case .imageComplete:
            if let completeImageData = result.imageData {
                imageData = completeImageData
                isDecoding = false
                decodingProgress = 1.0
                status = "Image complete - \(selectedMode) decoded successfully"
                
                // Save to gallery if configured
                saveDecodedImage(completeImageData)
            }
            
        case .error:
            isDecoding = false
            status = "Decode error: \(result.errorMessage ?? "Unknown error")"
        }
    }
    
    // MARK: - Image Processing
    
    private func updateProgressiveImage(_ lineData: Data) {
        // TODO: Implement progressive image rendering
        // This would combine the new line data with existing image data
        // For now, we'll wait for complete images
    }
    
    private func saveDecodedImage(_ imageData: Data) {
        // TODO: Implement image saving to gallery
        let timestamp = Date().formatted(.iso8601)
        let filename = "sstv_\(selectedMode.lowercased())_\(timestamp).png"
        print("Would save image as: \(filename)")
    }
    
    // MARK: - Mode Control
    
    func setMode(_ mode: SSTVMode) {
        currentMode = mode
        
        switch mode {
        case .receive:
            status = "QRV - Listening for SSTV signals"
        case .transmit:
            status = "Transmit mode - Select image to encode"
        case .gallery:
            status = "Gallery - Browse decoded images"
        case .settings:
            status = "Settings - Configure SSTV Station"
        }
    }
    
    func resetDecoding() {
        isDecoding = false
        decodingProgress = 0.0
        imageData = nil
        detectedVISCode = nil
        status = "QRV - Listening for SSTV signals"
    }
    
    // MARK: - Manual Adjustments
    
    func applySkewAdjustment(_ skew: Double) {
        skewAdjustment = skew
        // TODO: Send adjustment to Python bridge
    }
    
    func applyOffsetAdjustment(_ offset: Double) {
        offsetAdjustment = offset
        // TODO: Send adjustment to Python bridge
    }
    
    // MARK: - Utilities
    
    private func getCurrentDeviceName() -> String {
        // TODO: Get from AudioManager
        return "Built-in Microphone"
    }
}

// MARK: - Supporting Types

enum SSTVMode: String, CaseIterable {
    case receive = "RECEIVE"
    case transmit = "TRANSMIT"
    case gallery = "GALLERY"
    case settings = "SETTINGS"
    
    var displayName: String {
        return self.rawValue
    }
}

struct SSTVProcessingResult {
    enum ResultType {
        case spectrum
        case visDetected
        case lineData
        case imageComplete
        case error
    }
    
    let type: ResultType
    let visCode: Int?
    let imageData: Data?
    let progress: Float
    let errorMessage: String?
    
    init(type: ResultType, visCode: Int? = nil, imageData: Data? = nil, progress: Float = 0.0, errorMessage: String? = nil) {
        self.type = type
        self.visCode = visCode
        self.imageData = imageData
        self.progress = progress
        self.errorMessage = errorMessage
    }
}

struct SSTVModeDetector {
    static func modeFromVIS(_ visCode: Int) -> String {
        switch visCode {
        case 60: return "ScottieS1"
        case 56: return "ScottieS2"
        case 40: return "ScottieDX"
        case 44: return "MartinM1"
        case 28: return "MartinM2"
        case 8: return "Robot36"
        default: return "ScottieS1" // Default fallback
        }
    }
}

// MARK: - App Settings

@MainActor
class AppSettings: ObservableObject {
    @Published var displayTheme: DisplayTheme = .cyan
    @Published var chassisTheme: ChassisTheme = .black
    
    enum DisplayTheme {
        case cyan, amber, green
        
        var color: Color {
            switch self {
            case .cyan: return Color(red: 0, green: 1, blue: 1)
            case .amber: return Color(red: 1, green: 0.8, blue: 0)
            case .green: return Color(red: 0, green: 1, blue: 0)
            }
        }
    }
    
    enum ChassisTheme {
        case black, silver
        
        var gradientColors: [Color] {
            switch self {
            case .black:
                return [
                    Color(red: 0.1, green: 0.1, blue: 0.1),
                    Color(red: 0.05, green: 0.05, blue: 0.05)
                ]
            case .silver:
                return [
                    Color(red: 0.9, green: 0.9, blue: 0.9),
                    Color(red: 0.75, green: 0.75, blue: 0.75)
                ]
            }
        }
    }
}

import SwiftUI

extension Color {
    init(red: Double, green: Double, blue: Double) {
        self.init(.sRGB, red: red, green: green, blue: blue, opacity: 1.0)
    }
}