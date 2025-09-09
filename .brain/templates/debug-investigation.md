# Debug Investigation Template - SSTV Project

## Context Required
- **Layer**: L1+L2+L4 (Core + Development + Deep)
- **Files**: Load relevant source files for the component being debugged
- **Logs**: Check both Tauri console and Python subprocess outputs

## Investigation Pattern

### 1. Problem Identification
- **Symptom**: [Describe what's not working]
- **Expected**: [What should happen]
- **Scope**: [Which component: Frontend, Rust backend, Python subprocess]

### 2. Component Isolation
- **Frontend Issues**: Check browser console in Tauri dev mode
- **Rust Backend**: Check Tauri command responses and error handling
- **Python Subprocess**: Check stderr/stdout from Python calls
- **Audio Pipeline**: Verify CPAL → file → Python decoder chain

### 3. Common Issue Patterns
- **UI Not Updating**: Check DOM timing, await patterns in JS
- **Python Errors**: Verify subprocess arguments and file paths
- **Audio Issues**: Check CPAL permissions and device availability
- **File Path Issues**: Ensure absolute paths, proper escaping

### 4. Testing Strategy
- **Isolated Testing**: Test individual components separately
- **Reference Files**: Use known-good test files from `core/shared/testing/reference/`
- **Incremental**: Start with simplest case, add complexity

### 5. Fix Validation
- **Unit Test**: Verify fix with minimal test case
- **Integration**: Test full workflow
- **Edge Cases**: Test error conditions and boundary cases