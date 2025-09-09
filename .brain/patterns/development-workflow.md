# Development Workflow Patterns - SSTV Project

## "Good Enough" Philosophy
1. **Simple First**: Try the straightforward approach
2. **Optimize Later**: Only if needed for real-world usage
3. **Working > Perfect**: Ship functional features
4. **User-Driven**: Build what actually gets used

## Phase-based Development
- **Each Phase**: Separate branch for major features
- **Verification**: Test thoroughly before merging to main
- **Documentation**: Update CLAUDE.md with architecture changes

## Development Cycle
```bash
# 1. Make changes
npm run build          # Update frontend dist
npm run tauri dev      # Launch with fresh UI

# 2. Test with reference files
# Use files in core/shared/testing/reference/

# 3. Commit working code
git add -A
git commit -m "Descriptive message"
```

## Testing Strategy
- **Reference Files**: Known-good MMSSTV, Essex Ham, ARISS samples
- **Real Signals**: Test with actual SSTV transmissions
- **Cross-platform**: Verify on target platforms
- **Edge Cases**: Noise, partial signals, timing issues

## Code Organization
- **TODO Comments**: Leave TODO markers for future work
- **TODO.md**: Central tracking of outstanding tasks
- **Incremental**: Small, focused commits
- **Documentation**: Update CLAUDE.md for major changes

## Performance Validation
- **Audio Timing**: Critical for SSTV decode quality
- **Real-time**: No dropouts in live processing
- **Memory**: Proper cleanup of temporary files
- **UI Responsiveness**: Non-blocking long operations