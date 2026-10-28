import { expect, test } from '@playwright/test';

test('the shell renders the three tabs and deep links resolve to their view', async ({ page }) => {
  await page.goto('./');
  await expect(page.getByRole('link', { name: 'Chat' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Retrieval trace' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Document & evidence' })).toBeVisible();
  await page.goto('docs/ocbc-group_ar_2025_en/pages/98');
  await expect(page.locator('[data-view="document"]')).toBeVisible();
  await page.getByRole('link', { name: 'Retrieval trace' }).click();
  await expect(page).toHaveURL(/\/ui\/trace$/);
  await expect(page.locator('[data-view="trace"]')).toBeVisible();
});
