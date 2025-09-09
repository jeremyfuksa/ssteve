#!/usr/bin/env node

/**
 * Convert raw RGB data to PNG image
 * Usage: node rgb_to_png.js <input.rgb> <width> <height> [output.png]
 */

const fs = require('fs');
const path = require('path');
const { createCanvas } = require('canvas');

function convertRgbToPng(rgbFile, width, height, outputFile) {
    console.log(`Converting ${rgbFile} (${width}x${height}) to ${outputFile}`);
    
    // Read raw RGB data
    if (!fs.existsSync(rgbFile)) {
        throw new Error(`RGB file not found: ${rgbFile}`);
    }
    
    const rgbData = fs.readFileSync(rgbFile);
    const expectedSize = width * height * 3;
    
    console.log(`RGB file size: ${rgbData.length} bytes, expected: ${expectedSize} bytes`);
    
    if (rgbData.length !== expectedSize) {
        console.warn(`Warning: RGB data size mismatch. Using available data.`);
    }
    
    // Create canvas
    const canvas = createCanvas(width, height);
    const ctx = canvas.getContext('2d');
    
    // Create ImageData
    const imageData = ctx.createImageData(width, height);
    const pixels = imageData.data;
    
    // Convert RGB to RGBA
    for (let i = 0; i < width * height; i++) {
        const rgbIndex = i * 3;
        const rgbaIndex = i * 4;
        
        if (rgbIndex + 2 < rgbData.length) {
            pixels[rgbaIndex] = rgbData[rgbIndex];     // R
            pixels[rgbaIndex + 1] = rgbData[rgbIndex + 1]; // G
            pixels[rgbaIndex + 2] = rgbData[rgbIndex + 2]; // B
            pixels[rgbaIndex + 3] = 255; // A (alpha)
        } else {
            // Fill missing data with black
            pixels[rgbaIndex] = 0;
            pixels[rgbaIndex + 1] = 0;
            pixels[rgbaIndex + 2] = 0;
            pixels[rgbaIndex + 3] = 255;
        }
    }
    
    // Put image data on canvas
    ctx.putImageData(imageData, 0, 0);
    
    // Save as PNG
    const buffer = canvas.toBuffer('image/png');
    fs.writeFileSync(outputFile, buffer);
    
    console.log(`✅ Successfully created ${outputFile}`);
}

function main() {
    if (process.argv.length < 5) {
        console.log('Usage: node rgb_to_png.js <input.rgb> <width> <height> [output.png]');
        console.log('');
        console.log('Example:');
        console.log('  node rgb_to_png.js test_fast.rgb 320 256 test_fast.png');
        process.exit(1);
    }
    
    const rgbFile = process.argv[2];
    const width = parseInt(process.argv[3]);
    const height = parseInt(process.argv[4]);
    const outputFile = process.argv[5] || rgbFile.replace(/\.rgb$/, '.png');
    
    if (isNaN(width) || isNaN(height)) {
        throw new Error('Width and height must be numbers');
    }
    
    try {
        convertRgbToPng(rgbFile, width, height, outputFile);
    } catch (error) {
        console.error('❌ Error:', error.message);
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}