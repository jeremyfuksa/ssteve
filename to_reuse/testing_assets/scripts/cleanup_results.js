#!/usr/bin/env node
/**
 * Test Results Cleanup Script
 * 
 * Cleans up generated test result images based on age and patterns
 * Preserves historical evaluation results and reference images
 */

const fs = require('fs');
const path = require('path');

const RESULTS_DIR = path.join(__dirname, '..', 'results');
const PRESERVE_DIRS = ['colaclanth-sstv', 'decode', 'encode']; // Historical results and organized dirs to preserve
const MAX_AGE_DAYS = 7; // Delete files older than this
const MAX_FILES = 50; // Keep only most recent N files

function getFileAge(filePath) {
    const stats = fs.statSync(filePath);
    const now = new Date();
    const fileTime = new Date(stats.mtime);
    return (now - fileTime) / (1000 * 60 * 60 * 24); // days
}

function cleanupByAge(directory, maxDays) {
    console.log(`🧹 Cleaning files older than ${maxDays} days in ${directory}`);
    
    if (!fs.existsSync(directory)) {
        console.log(`⚠️  Directory ${directory} does not exist`);
        return { removed: 0, preserved: 0 };
    }

    const files = fs.readdirSync(directory);
    let removed = 0;
    let preserved = 0;

    for (const file of files) {
        const filePath = path.join(directory, file);
        const stat = fs.statSync(filePath);
        
        // Skip directories and preserved directories - also clean inside them
        if (stat.isDirectory()) {
            if (PRESERVE_DIRS.includes(file)) {
                console.log(`🔒 Preserving directory: ${file}`);
                // Recursively clean inside preserved directories
                const subResult = cleanupByAge(filePath, maxDays);
                removed += subResult.removed;
                preserved += subResult.preserved;
            }
            continue;
        }

        // Only clean image and audio files
        if (!/\.(png|jpg|jpeg|wav|mp3|m4a)$/i.test(file)) {
            continue;
        }

        const age = getFileAge(filePath);
        if (age > maxDays) {
            try {
                fs.unlinkSync(filePath);
                console.log(`🗑️  Removed: ${file} (${age.toFixed(1)} days old)`);
                removed++;
            } catch (error) {
                console.error(`❌ Failed to remove ${file}:`, error.message);
            }
        } else {
            preserved++;
        }
    }

    return { removed, preserved };
}

function cleanupByCount(directory, maxFiles) {
    console.log(`🧹 Keeping only ${maxFiles} most recent files in ${directory}`);
    
    if (!fs.existsSync(directory)) {
        return { removed: 0, preserved: 0 };
    }

    const files = fs.readdirSync(directory)
        .map(file => ({
            name: file,
            path: path.join(directory, file),
            mtime: fs.statSync(path.join(directory, file)).mtime
        }))
        .filter(file => {
            const stat = fs.statSync(file.path);
            return stat.isFile() && /\.(png|jpg|jpeg)$/i.test(file.name);
        })
        .sort((a, b) => b.mtime - a.mtime); // newest first

    let removed = 0;
    let preserved = 0;

    if (files.length > maxFiles) {
        const toRemove = files.slice(maxFiles);
        for (const file of toRemove) {
            try {
                fs.unlinkSync(file.path);
                console.log(`🗑️  Removed: ${file.name} (excess file)`);
                removed++;
            } catch (error) {
                console.error(`❌ Failed to remove ${file.name}:`, error.message);
            }
        }
        preserved = maxFiles;
    } else {
        preserved = files.length;
    }

    return { removed, preserved };
}

function getDirectorySize(directory) {
    if (!fs.existsSync(directory)) return 0;
    
    let size = 0;
    const files = fs.readdirSync(directory);
    
    for (const file of files) {
        const filePath = path.join(directory, file);
        const stat = fs.statSync(filePath);
        
        if (stat.isFile()) {
            size += stat.size;
        } else if (stat.isDirectory() && !PRESERVE_DIRS.includes(file)) {
            size += getDirectorySize(filePath);
        }
    }
    
    return size;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function main() {
    console.log('🧹 SSTV Test Results Cleanup');
    console.log('='.repeat(50));
    
    const sizeBefore = getDirectorySize(RESULTS_DIR);
    console.log(`📊 Size before cleanup: ${formatBytes(sizeBefore)}`);
    
    // Cleanup by age
    const ageResults = cleanupByAge(RESULTS_DIR, MAX_AGE_DAYS);
    
    // Cleanup by count  
    const countResults = cleanupByCount(RESULTS_DIR, MAX_FILES);
    
    const sizeAfter = getDirectorySize(RESULTS_DIR);
    const saved = sizeBefore - sizeAfter;
    
    console.log('\n📊 Cleanup Summary');
    console.log('-'.repeat(30));
    console.log(`🗑️  Files removed by age: ${ageResults.removed}`);
    console.log(`🗑️  Files removed by count: ${countResults.removed}`);
    console.log(`🔒 Files preserved: ${ageResults.preserved + countResults.preserved}`);
    console.log(`💾 Space saved: ${formatBytes(saved)}`);
    console.log(`📊 Size after cleanup: ${formatBytes(sizeAfter)}`);
    
    if (ageResults.removed > 0 || countResults.removed > 0) {
        console.log('\n✅ Cleanup completed successfully');
    } else {
        console.log('\n✨ No cleanup needed - all files are recent');
    }
}

if (require.main === module) {
    main();
}

module.exports = { cleanupByAge, cleanupByCount, getDirectorySize };