import { expect, test } from '@playwright/test';

test('document view: tree, page image with region boxes, page navigation and the picker', async ({ page }) => {
  await page.goto('docs/ocbc-group_ar_2025_en/pages/98');
  const view = page.locator('[data-view="document"]');
  await expect(view).toBeVisible();

  // The tree, with the nodes covering page 98 highlighted (the deepest is "Overview" under MD&A).
  await expect(page.getByRole('list', { name: 'Primary tree' })).toBeVisible();
  await expect(page.locator('.outline-row.deepest')).toContainText('Overview');

  // The page image has loaded and its region boxes are drawn.
  const img = page.getByRole('img', { name: 'Page image' });
  await expect(img).toHaveAttribute('src', '/v1/docs/ocbc-group_ar_2025_en/pages/98.png');
  await expect(img).toHaveAttribute('data-state', 'loaded');
  expect(await img.evaluate((e: HTMLImageElement) => e.naturalWidth)).toBeGreaterThan(0);
  await expect(page.locator('.region-box').first()).toBeVisible();
  expect(await page.locator('.region-box').count()).toBeGreaterThan(5);
  await expect(page.getByText(/printed page 96/)).toBeVisible();

  // The page's table, rendered as HTML.
  await expect(page.getByRole('cell', { name: 'Net interest income' }).first()).toBeVisible();

  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page).toHaveURL(/\/pages\/99$/);
  await expect(page.getByText(/physical page 99 /)).toBeVisible();

  await page.goto('docs');
  await expect(page.locator('table.doc-picker tbody tr')).toHaveCount(6);
});
