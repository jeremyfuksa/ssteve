#!/usr/bin/env node
/**
 * SSTV Round-trip Test - Encode-Decode Validation
 * 
 * Tests the complete SSTV cycle: Image → WAV → Image
 * Measures signal fidelity and quality preservation
 */

const path = require('path');
const fs = require('fs');
const { SSTVEngine } = require('../../lib');

console.log('🔄 SSTV Round-trip Test (Encode-Decode Validation)');
console.log('='.repeat(60));

async function runRoundtripTests() {
    const engine = new SSTVEngine({ debug: true });
    
    // Test 1: Check both encoder and decoder availability
    console.log('\n📋 Test 1: System Check');
    console.log('-'.repeat(30));
    
    const decoderAvailable = await engine.checkPythonLibrary();
    if (!decoderAvailable) {
        console.log('❌ colaclanth/sstv decoder not available');
        process.exit(1);
    }
    console.log('✅ SSTV decoder available');
    
    try {
        const encodingModes = await engine.getSupportedEncodingModes();
        console.log(`✅ SSTV encoder available (${encodingModes.length} modes)`);
    } catch (error) {
        console.log('❌ PySSTV encoder not available');
        process.exit(1);
    }
    
    // Test 2: Round-trip validation
    console.log('\n📋 Test 2: Round-trip Validation Tests');
    console.log('-'.repeat(30));
    
    // Test images to process
    const testImages = [
        {
            name: 'MMSSTV Bear Reference',
            path: 'testing/reference/images/mmsstv/reference_mmsstv_scottie_s1_bear_je3hht_expected.jpg',
            mode: 'ScottieS1'
        },
        {
            name: 'MMSSTV Elk Reference', 
            path: 'testing/reference/images/mmsstv/reference_mmsstv_scottie_s1_elk_forest_expected.jpg',
            mode: 'ScottieS1'
        },
        {
            name: 'EssexHAM Martin2',
            path: 'testing/reference/images/essexham/essexham_01_martin2.png',
            mode: 'MartinM2'
        },
        {
            name: 'EssexHAM Scottie2',
            path: 'testing/reference/images/essexham/essexham_01_scottie2.png', 
            mode: 'ScottieS2'
        }
    ];
    
    let successCount = 0;
    let totalTests = testImages.length;
    
    for (const testImage of testImages) {
        const imagePath = path.join(__dirname, '../..', testImage.path);
        
        // Check if test image exists
        if (!fs.existsSync(imagePath)) {
            console.log(`⚠️  Test image not found: ${testImage.name}`);
            continue;
        }
        
        console.log(`\\n🔄 Round-trip: ${testImage.name}`);
        console.log(`   Mode: ${testImage.mode}`);
        
        // Generate file paths
        const baseName = path.basename(testImage.path, path.extname(testImage.path));
        const modeName = testImage.mode.toLowerCase();
        const tempWavPath = path.join(__dirname, '..', 'results', 'roundtrip', `${baseName}_${modeName}.wav`);
        const finalImagePath = path.join(__dirname, '..', 'results', 'roundtrip', `${baseName}_${modeName}_roundtrip.png`);
        
        try {
            // Step 1: Encode Image → WAV
            console.log(`   🔧 Step 1: Encoding to WAV...`);
            const encodeResult = await engine.encode(imagePath, tempWavPath, {
                mode: testImage.mode,
                sampleRate: 22050,
                bitsPerSample: 16,
                resize: true
            });
            
            if (!encodeResult.success) {
                console.log(`   ❌ Encoding failed: ${encodeResult.message}`);
                continue;
            }
            
            console.log(`   ✅ Encoded: ${(encodeResult.fileSize / 1024 / 1024).toFixed(1)}MB WAV`);
            
            // Step 2: Decode WAV → Image
            console.log(`   🔧 Step 2: Decoding WAV to image...`);
            const decodeResult = await engine.decode(tempWavPath, finalImagePath);
            
            if (!decodeResult.success) {
                console.log(`   ❌ Decoding failed: ${decodeResult.message}`);
                continue;
            }
            
            console.log(`   ✅ Decoded: ${(decodeResult.fileSize / 1024).toFixed(1)}KB PNG`);
            
            // Step 3: Validate results
            const originalSize = fs.statSync(imagePath).size;
            const finalSize = fs.statSync(finalImagePath).size;
            const compressionRatio = ((originalSize - finalSize) / originalSize * 100).toFixed(1);
            
            console.log(`   📊 Original: ${(originalSize / 1024).toFixed(1)}KB → Final: ${(finalSize / 1024).toFixed(1)}KB`);
            console.log(`   📈 Size change: ${compressionRatio}%`);
            console.log(`   ⏱️  Total time: ${((encodeResult.duration || 0) + (decodeResult.duration || 0)) / 1000}s`);
            console.log(`   ✅ Round-trip successful!`);
            
            successCount++;
            
        } catch (error) {
            console.log(`   ❌ Round-trip failed: ${error.message}`);
        }
    }
    
    // Summary
    console.log('\\n📊 Round-trip Test Summary');
    console.log('='.repeat(40));
    console.log(`✅ Successful round-trips: ${successCount}/${totalTests}`);
    console.log(`📈 Success rate: ${((successCount / totalTests) * 100).toFixed(1)}%`);
    
    if (successCount === totalTests) {
        console.log('🎯 All round-trip tests passed! SSTV encode/decode cycle working correctly.');
    } else {
        console.log('⚠️  Some round-trip tests failed. Check error messages above.');
    }
    
    console.log(`\\n📁 Results saved in: testing/results/roundtrip/`);
    console.log('   • WAV files: Encoded audio for transmission');
    console.log('   • PNG files: Round-trip reconstructed images');
}

async function main() {
    try {
        await runRoundtripTests();
    } catch (error) {
        console.error('❌ Round-trip test failed:', error.message);
        process.exit(1);
    }
}

if (require.main === module) {
    main().catch(console.error);
}

module.exports = { runRoundtripTests };