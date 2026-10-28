import { expect, test } from '@playwright/test';

test('chat replays the recorded session and its citations open the document view', async ({ page }) => {
  await page.goto('chat');
  await expect(page.getByText('Replay of recorded sessions')).toBeVisible();
  const session = page.locator('[data-replay="mcp_demo_round1"]');
  await expect(session.locator('[data-question="d2"]')).not.toBeEmpty();
  await expect(session.locator('[data-question="d3"]')).toBeVisible();
  await expect(session.locator('[data-question="d4"]')).toBeVisible();
  await expect(session.locator('.chat-call [data-tier]').first()).toBeVisible();

  const citation = session.locator('a.citation').first();
  await expect(citation).toBeVisible();
  const target = await citation.getAttribute('href');
  expect(target).toMatch(/^\/ui\/docs\/[^/]+\/pages\/\d+$/);
  await citation.click();
  await expect(page).toHaveURL(new RegExp(`${target}$`));
  await expect(page).toHaveURL(/\/ui\/docs\/ocbc-group_ar_2025_en\/pages\/98$/);
  await expect(page.locator('[data-view="document"]')).toBeVisible();
});
