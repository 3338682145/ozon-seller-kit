// 签发卖家端（seller.ozon.ru）cookie jar + uuid，供本地 HTTP 采集器复用
//
// 用法:
//   ego-browser nodejs <<'X'
//     await import('file:///Users/a1234/work/ozon-agent/scripts/mint_seller_cookie.mjs');
//   X
//
// 产物:
//   ~/.config/ozon-seller/cookie.txt      Cookie 头（seller.ozon.ru 视角的完整可用集）
//   ~/.config/ozon-seller/cookie.ua      签发它的浏览器 UA（UA 与 token 绑定，必须成对用）
//   ~/.config/ozon-seller/meta.json       company_id / uuid / 抓取时间 / cookie 名清单
//
// 为什么不能只抄 document.cookie：
//   document.cookie 看不到 HttpOnly（__Secure-token / __Secure-product-user-id），
//   也没有 Domain 归属信息。必须走 CDP Network.getAllCookies。
import fs from 'node:fs';
import path from 'node:path';

const HOME = process.env.HOME;
const DIR = path.join(HOME, '.config', 'ozon-seller');
const COOKIE_FILE = path.join(DIR, 'cookie.txt');
const UA_FILE = path.join(DIR, 'cookie.ua');
const META_FILE = path.join(DIR, 'meta.json');

const ENTRY = 'https://seller.ozon.ru/app/analytics-search/search-results/explainer';

const ts = await taskSpace('seller cookie mint ' + Date.now());
const page = ts.page('p1');

let title = '';
for (let i = 0; i < 10; i++) {
  if (i === 0) await page.goto(ENTRY, { waitUntil: 'networkidle', timeout: 120000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 2500));
  title = await page.evaluate(() => document.title).catch(() => '');
  if (/Ozon/i.test(title) && !/нет соединения|Antibot|Доступ ограничен/i.test(title)) break;
  await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => {});
}
console.log('[mint] title =', title);

const ua = await page.evaluate(() => navigator.userAgent);
const companyId = await page.evaluate(
  () => (document.cookie.match(/sc_company_id=(\d+)/) || [])[1] || null,
);

// 抓 uuid：hook fetch/XHR，然后真的在页面里搜一次，拿真实请求体里的 uuid
await page.evaluate(() => {
  window.__uuid = null;
  function grab(u, b) {
    try {
      if (String(u).indexOf('explanation_by_id') < 0) return;
      const s = typeof b === 'string' ? b : JSON.stringify(b || {});
      const m = s.match(/"uuid"\s*:\s*"([^"]+)"/);
      if (m) window.__uuid = m[1];
    } catch (e) {}
  }
  const of = window.fetch;
  window.fetch = function (i, init) { grab((typeof i === 'string' ? i : (i && i.url) || ''), init && init.body); return of.apply(this, arguments); };
  const ox = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return ox.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) { grab(this.__u, b); return os.apply(this, arguments); };
});

await page.waitForFunction(
  () => [...document.querySelectorAll('input')].some((x) => /搜索|Поиск/.test(x.placeholder || '')),
  { timeout: 45000 },
).catch(() => console.log('[mint] 等搜索框超时'));
await page.evaluate(() => {
  const inp = [...document.querySelectorAll('input')].find((x) => (x.placeholder || '').indexOf('搜索') >= 0);
  if (inp) {
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    set.call(inp, 'антистресс');
    inp.dispatchEvent(new Event('input', { bubbles: true }));
  }
});
await page.waitForTimeout(400);
await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => (x.innerText || '').trim() === '显示结果');
  if (b) b.click();
});
await page.waitForTimeout(9000);
const uuid = await page.evaluate(() => window.__uuid);
console.log('[mint] company_id =', companyId, '| uuid =', uuid ? uuid.slice(0, 8) + '…' : 'NONE');

// 对照组：页内 fetch（已知可用），确认会话真的能出数
const ctrl = await page.fetch(
  '/api/search-query-analytics/v2/external/explanation_by_id',
  {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-o3-app-name': 'seller-ui',
      'x-o3-page-type': 'analytics-search',
      'x-o3-language': 'zh-Hans',
      'x-o3-company-id': String(companyId),
      'x-o3-timezone': 'Asia/Shanghai',
    },
    timeout: 45000,
    body: JSON.stringify({
      sellerId: String(companyId),
      query: 'антистресс',
      uuid,
      skus: [],
      sortOption: { headerKey: 'position', direction: 'SortDirectionAscending' },
      itemsPerPage: '108',
      pageNumber: '1',
      onlyCurSellerItems: false,
      applicationScope: 'SCOPE_BIG_OZON',
    }),
  },
).catch((e) => ({ status: 'ERR', body: e.message }));

let ctrlN = 0;
try { ctrlN = (JSON.parse(ctrl.body).items || []).length; } catch (e) {}
console.log('[mint] 对照组页内 fetch: HTTP', ctrl.status, '| items', ctrlN);

// 落 jar：seller.ozon.ru 会收到 .ozon.ru 与 .seller.ozon.ru 两个域的 cookie
const all = await page.cdp('Network.getAllCookies');
const HOST = 'seller.ozon.ru';
const applies = all.cookies.filter((c) => {
  const d = c.domain.startsWith('.') ? c.domain.slice(1) : c.domain;
  return HOST === d || HOST.endsWith('.' + d);
});

const jar = {};
for (const c of applies) {
  if (c.name === 'abt_data' && jar.abt_data && jar.abt_data.length >= c.value.length) continue;
  jar[c.name] = c.value;
}

if (!companyId) { console.log('[mint] 失败：没有 sc_company_id，卖家端未登录'); process.exit(2); }

// uuid 抓不到就复用 meta 里的旧值（实测可跨会话、跨店铺复用）
let finalUuid = uuid;
if (!finalUuid) {
  try {
    const prev = JSON.parse(fs.readFileSync(META_FILE, 'utf8'));
    if (prev.uuid) { finalUuid = prev.uuid; console.log('[mint] uuid 未抓到，复用旧值', finalUuid.slice(0, 12) + '…'); }
  } catch (e) {}
}
if (!finalUuid) { console.log('[mint] ⚠ 没有可用 uuid，保持 meta 原值不动'); finalUuid = undefined; }
if (!finalUuid) console.log('[mint] ⚠ 没有 uuid，p8 explainer 会 400；需在有搜索框的页面手动触发一次');

fs.mkdirSync(DIR, { recursive: true });
fs.writeFileSync(COOKIE_FILE, Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; '), { mode: 0o600 });
fs.writeFileSync(UA_FILE, ua, { mode: 0o600 });
let prevMeta = {};
try { prevMeta = JSON.parse(fs.readFileSync(META_FILE, 'utf8')); } catch (e) {}
fs.writeFileSync(META_FILE, JSON.stringify({
  minted_at: new Date().toISOString(),
  company_id: companyId,
  uuid: finalUuid !== undefined ? finalUuid : (prevMeta.uuid || null),
  ua,
  entry: ENTRY,
  cookie_count: Object.keys(jar).length,
  cookie_names: Object.keys(jar),
  control_items: ctrlN,
}, null, 1), { mode: 0o600 });

console.log('[mint] 写入', COOKIE_FILE, '| cookies', Object.keys(jar).length, '| abt_data', (jar.abt_data || '').length);
console.log('[mint] 关键 cookie:', ['__Secure-token', '__Secure-product-user-id', 'sc_company_id', 'abt_data', 'xcid']
  .map((n) => `${n}=${jar[n] ? 'Y' : '-'}`).join(' '));
