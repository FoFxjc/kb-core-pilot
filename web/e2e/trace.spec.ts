import { expect, test } from '@playwright/test';

test('a UI search is traced: detail shows request, route ranks, coverage gate and templates; the list shows it',
  async ({ page, request }) => {
    const res = await request.post('/v1/search', { data: { query: 'NPL ratio 2025' }, headers: { 'X-KB-Source': 'ui' } });
    expect(res.ok()).toBeTruthy();
    const { trace_id: traceId } = (await res.json()) as { trace_id: string };
    expect(traceId).toMatch(/^tr_/);

    await page.goto(`trace/${traceId}`);
    const view = page.locator('[data-view="trace"]');
    const request_ = view.getByRole('region', { name: 'Request' });
    await expect(request_).toBeVisible();
    await expect(request_.getByText('"query": "NPL ratio 2025"')).toBeVisible();
    await expect(request_.getByText(traceId)).toBeVisible();

    const ranks = view.getByRole('region', { name: 'Per-route ranks' });
    await expect(ranks).toBeVisible();
    await expect(ranks.getByRole('columnheader', { name: 'title_tok' })).toBeVisible();
    await expect(ranks.locator('tr.tr-kept').first()).toBeVisible();

    const gate = view.getByRole('region', { name: 'Coverage gate' });
    await expect(gate).toBeVisible();
    await expect(gate.getByText(/\d+ fail/)).toBeVisible();

    const queries = view.getByRole('region', { name: 'Executed queries' });
    await expect(queries.getByText('S1_node_title_bm25.v1')).toBeVisible();

    await page.getByRole('link', { name: 'All traces' }).click();
    await expect(page).toHaveURL(/\/ui\/trace$/);
    await page.getByLabel('Source').selectOption('ui');
    await expect(page.locator(`tr[data-trace-id="${traceId}"]`)).toBeVisible();
    await expect(page.locator(`tr[data-trace-id="${traceId}"]`).getByRole('link', { name: 'NPL ratio 2025' })).toBeVisible();
  });
