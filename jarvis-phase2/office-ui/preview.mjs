import { chromium } from 'playwright';
import { createServer } from 'vite';

const server = await createServer({ configFile: 'vite.config.js', server: { host: '127.0.0.1', port: 5173, strictPort: true } });
await server.listen();

const names = ['Yönetim', 'Tasarım', 'Web', 'SEO', 'Marka', 'Pazarlama', 'Satış', 'Finans', 'Güvenlik', 'Ürün'];
const departments = Array.from({ length: 40 }, (_, i) => {
  const count = i === 1 ? 16 : i % 5 + 1;
  const kadro = Array.from({ length: count }, (_, j) => ({ key: `m${i}_${j}`, name: `Çalışan ${i + 1}.${j + 1}`, job: `Birim ${i + 1} görev alanı`, status: j % 5 === 0 ? 'KONUŞTU' : 'GİRDİ BEKLER', statement: 'Son ölçümde kaynak verileri incelendi.', reads: ['system'], sorumlu_mu: j === 0 }));
  return { kod: `D${i}`, ad: `${names[i % names.length]} ${Math.floor(i / 10) + 1}`, aile: 'ŞİRKET', misyon: 'Birim faaliyetleri ve veri analizi.', kisi: count, sorumlu: { key: kadro[0].key, name: kadro[0].name }, kadro };
});
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', args: ['--use-gl=angle', '--use-angle=swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 950 }, deviceScaleFactor: 1 });
const errors = [];
page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
page.on('response', (r) => { if (r.status() >= 400) errors.push(r.status() + ' ' + r.url()); });
page.on('pageerror', (error) => errors.push(error.message));
await page.route('**/api/**', async (route) => {
  const path = new URL(route.request().url()).pathname;
  if (path === '/api/office/events') {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: snapshot\ndata: {"active":{}}\n\n' });
    return;
  }
  const data = path === '/api/session' ? { authenticated: true } :
    path === '/api/panel/ajanlar' ? { departmanlar: departments } :
    path === '/api/panel/ekip' ? { departmanlar: departments } :
    path === '/api/office/activity' ? { generated_at: new Date().toISOString(), members: { m7_0: { status: 'WORKED', task: 'Şirket verisini oku', result: 'Ölçüm tamamlandı', finished_at: new Date().toISOString() } } } :
    path === '/api/orchestration' ? { runs: [], total: 0 } : { pending: [] };
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
});
await page.goto('http://127.0.0.1:5173/office.html');
await page.waitForTimeout(5000);
await page.screenshot({ path: 'preview.png', fullPage: true });
await page.locator('.department-row').first().click();
await page.waitForTimeout(500);
await page.screenshot({ path: 'preview-detail.png', fullPage: true });
await page.locator('.member-card').first().click();
const memberName = await page.locator('.member-detail h3').textContent();
const activityVisible = await page.locator('.member-activity').count();
await page.locator('#closeDetail').click();
await page.locator('#showChart').click();
const chartCount = await page.locator('.chart-unit').count();
await page.screenshot({ path: 'preview-chart.png', fullPage: true });
await page.locator('#closeChart').click();
await page.locator('#walkMode').click();
await page.waitForTimeout(300);
const walkActive = await page.locator('#walkHint').isVisible();
await page.keyboard.press('Escape');
await page.locator('#search').fill('Çalışan 2.2');
const searchCount = await page.locator('.department-row').count();
const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
await mobile.route('**/api/**', async (route) => {
  const path = new URL(route.request().url()).pathname;
  if (path === '/api/office/events') { await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: snapshot\ndata: {"active":{}}\n\n' }); return; }
  const data = path === '/api/session' ? { authenticated: true } : path === '/api/panel/ajanlar' || path === '/api/panel/ekip' ? { departmanlar: departments } : path === '/api/orchestration' ? { runs: [] } : path === '/api/office/activity' ? { generated_at: new Date().toISOString(), members: {} } : { pending: [] };
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
});
await mobile.goto('http://127.0.0.1:5173/office.html');
await mobile.waitForTimeout(1500);
await mobile.screenshot({ path: 'preview-mobile.png', fullPage: true });
console.log(JSON.stringify({ errors, searchCount, memberName, activityVisible, chartCount, walkActive, mobileOverflow: await mobile.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), title: await page.title() }));
await browser.close();
await server.close();
