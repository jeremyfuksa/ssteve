import { test, expect } from '@playwright/test';

test.describe('SSTV Station UI', () => {
  test('loads receive mode and status panel', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.sstv-station')).toBeVisible();
    await expect(page.locator('.function-btn.active')).toHaveAttribute('data-mode', 'RECEIVE');
    await expect(page.locator('#status-text')).toBeVisible();
    await expect(page.locator('#toast-container')).toBeVisible();
  });

  test('switches between modes and reveals controls', async ({ page }) => {
    await page.goto('/');

    const transmitBtn = page.locator('.function-btn[data-mode="TRANSMIT"]');
    await transmitBtn.click();
    await expect(page.locator('#encode-audio')).toBeVisible();
    await expect(page.locator('#save-audio')).toBeHidden();

    const galleryBtn = page.locator('.function-btn[data-mode="GALLERY"]');
    await galleryBtn.click();
    await expect(page.locator('#gallery-prev')).toBeVisible();
    await expect(page.locator('#gallery-next')).toBeVisible();
  });

  test('decode flow is gated to Tauri bridge (reference audio)', async ({ page }) => {
    test.skip(!process.env.E2E_AUDIO_PATH, 'Set E2E_AUDIO_PATH to run Tauri decode flow');
    await page.goto('/');

    const result = await page.evaluate(async (audioPath) => {
      if (!(window as any).__TAURI_INTERNALS__?.invoke) {
        throw new Error('Tauri bridge not available');
      }
      return (window as any).__TAURI_INTERNALS__.invoke('decode_sstv_file', { audioPath });
    }, process.env.E2E_AUDIO_PATH);

    expect(result).toBeDefined();
  });
});
