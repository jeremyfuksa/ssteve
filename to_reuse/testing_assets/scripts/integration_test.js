#!/usr/bin/env node
/**
 * Integration Test for SSTV Engine using colaclanth/sstv
 * 
 * Tests the complete engine functionality against known test files
 */

const path = require('path');
const fs = require('fs');
const { SSTVEngine } = require('../../lib');

console.log('🧪 SSTV Engine Integration Test');
console.log('='.repeat(50));

async function runTests() {
    const engine = new SSTVEngine({ debug: true, pythonPath: 'python3' });
    
    // Test 1: Check Python library availability
    console.log('\n📋 Test 1: Python Library Check');
    console.log('-'.repeat(30));
    
    const libraryAvailable = await engine.checkPythonLibrary();
    if (libraryAvailable) {
        console.log('✅ colaclanth/sstv library is available');
    } else {
        console.log('❌ colaclanth/sstv library not found');
        console.log('💡 Run: pip install sstv');
        process.exit(1);
    }

    // Test 2: Get supported modes
    console.log('\n📋 Test 2: Supported Modes');
    console.log('-'.repeat(30));
    
    try {
        const modes = await engine.getSupportedModes();
        console.log('✅ Supported modes:', modes.length);
        modes.forEach(mode => console.log(`   • ${mode}`));
    } catch (error) {
        console.log('❌ Failed to get modes:', error.message);
    }

    // Test 3: Decode test files
    console.log('\n📋 Test 3: SSTV Decode Tests');
    console.log('-'.repeat(30));

    const testFiles = [
        // Primary Scottie S1 tests (MMSSTV reference quality)
        'testing/reference/audio/mmsstv/scottie_s1_bear_je3hht.wav',
        'testing/reference/audio/mmsstv/scottie_s1_elk_forest.wav', 
        'testing/reference/audio/mmsstv/scottie_s1_operator_shack.wav',
        'testing/reference/audio/mmsstv/scottie_s1_radio_desk.wav',
        'testing/reference/audio/mmsstv/scottie_s1_winter_creek.wav',
        // EssexHAM tests (converted to WAV)
        'testing/reference/audio/essexham/essexham_01_martin2.wav',
        'testing/reference/audio/essexham/essexham_02_martin2.wav',
        'testing/reference/audio/essexham/essexham_01_scottie2.wav',
        'testing/reference/audio/essexham/essexham_02_scottie2.wav'
        // Note: ARISS files excluded - use unsupported SSTV mode (VIS: 95)
    ];

    let successCount = 0;
    let totalTests = testFiles.length;

    for (const testFile of testFiles) {
        const audioPath = path.join(__dirname, '../..', testFile);
        const outputPath = path.join(__dirname, '..', 'results', 'decode', `${path.basename(testFile).replace(/\.wav$/, '')}.png`);
        
        if (!fs.existsSync(audioPath)) {
            console.log(`⚠️  Test file not found: ${testFile}`);
            continue;
        }

        // Ensure output directory exists
        const outputDir = path.dirname(outputPath);
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }

        console.log(`\n🔬 Testing: ${path.basename(testFile)}`);
        
        // Set up callbacks
        engine.setModeDetectedCallback((mode) => {
            console.log(`   📡 Detected mode: ${mode}`);
        });
        
        engine.setProgressCallback((progress) => {
            if (progress % 25 === 0) { // Only log every 25%
                console.log(`   🔄 Progress: ${progress}%`);
            }
        });

        try {
            const startTime = Date.now();
            const result = await engine.decode(audioPath, outputPath);
            
            if (result.success) {
                console.log(`   ✅ Success: ${result.mode} (${Date.now() - startTime}ms)`);
                console.log(`   📁 Output: ${result.outputPath}`);
                console.log(`   📊 Size: ${result.fileSize} bytes`);
                successCount++;
            } else {
                console.log(`   ❌ Failed: ${result.message}`);
            }
        } catch (error) {
            console.log(`   ❌ Error: ${error.message}`);
        }
    }

    // Test Summary
    console.log('\n📊 Test Summary');
    console.log('='.repeat(50));
    console.log(`✅ Successful decodes: ${successCount}/${totalTests}`);
    console.log(`📈 Success rate: ${((successCount/totalTests) * 100).toFixed(1)}%`);
    
    if (successCount === totalTests) {
        console.log('🎉 All tests passed! Engine is working perfectly.');
        process.exit(0);
    } else {
        console.log('⚠️  Some tests failed. Check error messages above.');
        process.exit(1);
    }
}

// Run the tests
runTests().catch(error => {
    console.error('💥 Test suite failed:', error.message);
    process.exit(1);
});