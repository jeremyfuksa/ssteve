import Foundation
import Python

class PythonBridge {
    private var pythonModule: PythonObject?
    private var sstv_engine: PythonObject?
    private var isInitialized = false
    
    // Shared memory for audio data
    private var audioBuffer: UnsafeMutableRawPointer?
    private let bufferSize = 1024 * 1024 // 1MB buffer
    
    init() throws {
        // Set Python path to include our core module
        let coreModulePath = Bundle.main.bundlePath + "/../../core/python"
        
        guard let sysModule = Python.import("sys") else {
            throw PythonBridgeError.importFailed("sys")
        }
        
        sysModule.path.append(coreModulePath)
        
        // Initialize shared memory
        allocateSharedMemory()
    }
    
    deinit {
        cleanup()
    }
    
    // MARK: - Initialization
    
    func initialize() async throws {
        guard !isInitialized else { return }
        
        // Import our SSTV engine
        guard let engine = Python.import("sstv_engine") else {
            throw PythonBridgeError.importFailed("sstv_engine")
        }
        
        sstv_engine = engine
        
        // Initialize the decoder
        let decoder = engine.SSTVDecoder()
        let result = decoder.checkDependencies()
        
        if !Bool(result.success)! {
            let missing = Array(result.missing)?.map(String.init) ?? []
            throw PythonBridgeError.dependenciesMissing(missing)
        }
        
        pythonModule = engine
        isInitialized = true
        
        print("Python bridge initialized successfully")
    }
    
    // MARK: - Audio Processing
    
    func processAudioStream(_ audioData: Data) async throws -> SSTVProcessingResult {
        guard isInitialized, let engine = sstv_engine else {
            throw PythonBridgeError.notInitialized
        }
        
        // Write audio data to shared buffer
        try writeAudioToBuffer(audioData)
        
        // Call Python processing function
        let decoder = engine.SSTVDecoder()
        let result = decoder.processAudioBuffer(
            bufferPtr: Int(bitPattern: audioBuffer),
            bufferSize: audioData.count,
            sampleRate: 22050
        )
        
        return try parseProcessingResult(result)
    }
    
    func decodeAudioFile(_ filePath: String) async throws -> SSTVProcessingResult {
        guard isInitialized, let engine = sstv_engine else {
            throw PythonBridgeError.notInitialized
        }
        
        let decoder = engine.SSTVDecoder()
        let result = decoder.decode(
            audioPath: filePath,
            outputPath: "/tmp/sstv_decode.png"
        )
        
        return try parseProcessingResult(result)
    }
    
    // MARK: - Encoding
    
    func encodeImage(_ imagePath: String, mode: String) async throws -> SSTVProcessingResult {
        guard isInitialized, let engine = sstv_engine else {
            throw PythonBridgeError.notInitialized
        }
        
        let encoder = engine.SSTVEncoder()
        let result = encoder.encode(
            imagePath: imagePath,
            outputPath: "/tmp/sstv_encode.wav",
            mode: mode
        )
        
        return try parseProcessingResult(result)
    }
    
    // MARK: - Shared Memory Management
    
    private func allocateSharedMemory() {
        audioBuffer = UnsafeMutableRawPointer.allocate(
            byteCount: bufferSize,
            alignment: MemoryLayout<Float>.alignment
        )
    }
    
    private func writeAudioToBuffer(_ data: Data) throws {
        guard let buffer = audioBuffer else {
            throw PythonBridgeError.memoryError("Audio buffer not allocated")
        }
        
        guard data.count <= bufferSize else {
            throw PythonBridgeError.memoryError("Audio data exceeds buffer size")
        }
        
        data.withUnsafeBytes { bytes in
            buffer.copyMemory(from: bytes.baseAddress!, byteCount: data.count)
        }
    }
    
    // MARK: - Result Parsing
    
    private func parseProcessingResult(_ pythonResult: PythonObject) throws -> SSTVProcessingResult {
        guard let success = Bool(pythonResult.success) else {
            throw PythonBridgeError.invalidResult("Missing success field")
        }
        
        if !success {
            let errorMsg = String(pythonResult.error) ?? "Unknown Python error"
            return SSTVProcessingResult(type: .error, errorMessage: errorMsg)
        }
        
        // Parse result type
        let resultType = String(pythonResult.type) ?? "unknown"
        
        switch resultType {
        case "spectrum":
            return SSTVProcessingResult(type: .spectrum)
            
        case "vis_detected":
            let visCode = Int(pythonResult.vis_code) ?? 0
            return SSTVProcessingResult(type: .visDetected, visCode: visCode)
            
        case "line_data":
            let progress = Float(pythonResult.progress) ?? 0.0
            let imageData = extractImageData(pythonResult.image_data)
            return SSTVProcessingResult(type: .lineData, imageData: imageData, progress: progress)
            
        case "image_complete":
            let imageData = extractImageData(pythonResult.image_data)
            return SSTVProcessingResult(type: .imageComplete, imageData: imageData, progress: 1.0)
            
        default:
            throw PythonBridgeError.invalidResult("Unknown result type: \(resultType)")
        }
    }
    
    private func extractImageData(_ pythonData: PythonObject?) -> Data? {
        guard let pythonData = pythonData else { return nil }
        
        // Convert Python bytes to Swift Data
        let bytes = Python.bytes(pythonData)
        let length = Int(Python.len(bytes))
        
        return Data(bytes: Array(bytes)!, count: length)
    }
    
    // MARK: - Cleanup
    
    private func cleanup() {
        if let buffer = audioBuffer {
            buffer.deallocate()
            audioBuffer = nil
        }
        
        isInitialized = false
    }
}

// MARK: - Error Types

enum PythonBridgeError: LocalizedError {
    case importFailed(String)
    case dependenciesMissing([String])
    case notInitialized
    case memoryError(String)
    case invalidResult(String)
    case processingError(String)
    
    var errorDescription: String? {
        switch self {
        case .importFailed(let module):
            return "Failed to import Python module: \(module)"
        case .dependenciesMissing(let deps):
            return "Missing Python dependencies: \(deps.joined(separator: ", "))"
        case .notInitialized:
            return "Python bridge not initialized"
        case .memoryError(let msg):
            return "Memory error: \(msg)"
        case .invalidResult(let msg):
            return "Invalid result from Python: \(msg)"
        case .processingError(let msg):
            return "Processing error: \(msg)"
        }
    }
}

// MARK: - Python Integration Extensions

extension PythonBridge {
    static func checkPythonAvailability() -> Bool {
        do {
            let sys = Python.import("sys")
            print("Python version: \(sys.version)")
            return true
        } catch {
            print("Python not available: \(error)")
            return false
        }
    }
    
    func getSupportedModes() async throws -> [String] {
        guard isInitialized, let engine = sstv_engine else {
            throw PythonBridgeError.notInitialized
        }
        
        let decoder = engine.SSTVDecoder()
        let result = decoder.getSupportedModes()
        
        guard let success = Bool(result.success), success else {
            throw PythonBridgeError.processingError("Failed to get supported modes")
        }
        
        return Array(result.modes)?.map(String.init) ?? []
    }
}