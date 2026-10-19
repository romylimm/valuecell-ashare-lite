const $ = (id) => document.getElementById(id);
let report = null;
let busy = false;
let modelConfigured = false;
const labels = { quote: '行情', history: '日线', financials: '财务', news: '新闻' };

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function link(url, text, className) {
  const node = element('a', text, className);
  try {
    const parsed = new URL(url);
    if (['https:', 'http:'].includes(parsed.protocol)) {
      node.href = parsed.href; node.target = '_blank'; node.rel = 'noopener noreferrer';
    }
  } catch { /* Invalid provider URLs remain plain text. */ }
  return node;
}
const fmt = (value, digits = 2) => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString('zh-CN', { maximumFractionDigits: digits }) : '—';
function source(key, data) {
  const box = $(key + '-source'); box.replaceChildren();
  box.append(link(data.url, data.source), element('div', '获取时间：' + data.fetched_at));
  if (data.status !== 'ok') box.append(element('div', data.message, 'missing'));
}
function list(id, values) {
  $(id).replaceChildren(...values.map((text) => element('li', text)));
}
function chart(rows) {
  const canvas = $('chart'); const scale = window.devicePixelRatio || 1;
  const width = canvas.clientWidth; const height = 220;
  canvas.width = width * scale; canvas.height = height * scale;
  const ctx = canvas.getContext('2d'); ctx.scale(scale, scale);
  const points = rows.filter((row) => typeof row.close === 'number' && row.close > 0);
  if (points.length < 2) {
    ctx.fillStyle = '#8a9b96'; ctx.font = '12px sans-serif';
    ctx.fillText('暂无足够日线数据', 20, 100); return;
  }
  const values = points.map((row) => row.close);
  const low = Math.min(...values); const high = Math.max(...values);
  const range = high - low || Math.max(high * 0.01, 1);
  const x = (i) => 52 + i * (width - 64) / (points.length - 1);
  const y = (v) => 185 - (v - low) / range * 150;
  ctx.font = '10px sans-serif';
  for (let i = 0; i < 4; i++) {
    const v = low + range * i / 3; const py = y(v);
    ctx.strokeStyle = '#edf3ef'; ctx.beginPath(); ctx.moveTo(49, py); ctx.lineTo(width, py); ctx.stroke();
    ctx.fillStyle = '#8a9b96'; ctx.fillText(v.toFixed(2), 0, py + 3);
  }
  ctx.strokeStyle = '#087e74'; ctx.lineWidth = 2; ctx.beginPath();
  values.forEach((v, i) => i === 0 ? ctx.moveTo(x(i), y(v)) : ctx.lineTo(x(i), y(v)));
  ctx.stroke(); ctx.fillStyle = '#8a9b96';
  ctx.fillText(String(points[0].date).slice(0, 10), 52, 213);
  ctx.fillText(String(points.at(-1).date).slice(0, 10), Math.max(52, width - 76), 213);
}
function render(data) {
  $('empty').hidden = true; $('report').hidden = false;
  const quote = data.datasets.quote.data[0];
  $('report-code').textContent = data.symbol.toUpperCase() + ' / CNY';
  $('stock-name').textContent = quote?.name || data.symbol.slice(2);
  $('report-time').textContent = '生成于 ' + data.generated_at + (data.cached ? ' · 数据来自 5 分钟内缓存' : '');
  $('metrics').replaceChildren();
  const metrics = [
    ['最新报价 / 元', quote?.price, quote?.quote_time ? '行情时间 ' + quote.quote_time : '行情暂缺'],
    ['涨跌幅 / %', quote?.change_percent, '相对前收盘价'],
    ['市盈率 TTM', quote?.pe_ttm, '源站口径'],
    ['市净率', quote?.pb, '源站口径'],
  ];
  for (const [label, value, note] of metrics) {
    const card = element('div', null, 'metric');
    card.append(element('label', label), element('strong', fmt(value)), element('div', note, 'muted'));
    $('metrics').append(card);
  }
  list('observations', data.observations); list('warnings', data.warnings);
  for (const key of Object.keys(labels)) source(key, data.datasets[key]);
  const history = [...data.datasets.history.data].sort((a,b) => String(a.date).localeCompare(String(b.date)));
  chart(history);
  $('chart-caption').textContent = history.length
    ? `共 ${history.length} 个交易日；截至 ${String(history.at(-1).date).slice(0,10)}。报价与日线时间可能不同。` : '日线获取失败，未填充模拟数据。';
  $('financials').replaceChildren();
  for (const row of data.datasets.financials.data) {
    const tr = element('tr');
    const value = row.value == null ? null : Number(row.value);
    const cell = value === null || !Number.isFinite(value) ? '—' : fmt(value, 4);
    tr.append(element('td', String(row.report_date).slice(0,10)), element('td', row.metric_label || row.metric_name), element('td', cell + ' ' + (row.unit || '')));
    $('financials').append(tr);
  }
  if (!data.datasets.financials.data.length) {
    const tr = element('tr'); const td = element('td', '财务数据暂缺，请查看来源或稍后重试。'); td.colSpan = 3; tr.append(td); $('financials').append(tr);
  }
  $('news').replaceChildren();
  for (const row of data.datasets.news.data) {
    const item = link(row['新闻链接'], row['新闻标题'], 'news-item');
    item.append(element('small', (row['发布时间'] || '') + ' · ' + (row['文章来源'] || ''))); $('news').append(item);
  }
  if (!data.datasets.news.data.length) $('news').append(element('p', '本次未获取到新闻，不代表没有相关新闻。', 'muted'));
  $('ai-card').hidden = data.ai_status === '未启用';
  $('ai-status').textContent = data.ai_status;
  $('ai-text').textContent = data.ai_text || data.ai_status;
}
async function analyze(event) {
  event?.preventDefault(); if (busy) return;
  const code = $('symbol').value.trim();
  if (!code) { $('symbol').focus(); return; }
  busy = true; $('submit').disabled = true; $('use-ai').disabled = true;
  $('report').hidden = true; $('empty').hidden = true;
  $('status').className = ''; $('status').textContent = '正在并行获取行情、日线、财务和新闻，通常需要 10–35 秒…';
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 110000);
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: code, use_ai: $('use-ai').checked }), signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请输入有效的六位 A 股代码。');
    report = data; render(data);
    const available = Object.values(data.datasets).filter((item) => item.status === 'ok').length;
    $('status').textContent = available ? `分析完成 · ${available}/4 类数据可用` : '暂未获取到有效数据，请检查股票代码或稍后重试。';
    if (!available) $('status').className = 'error';
  } catch (error) {
    $('status').className = 'error';
    $('status').textContent = error.name === 'AbortError' ? '分析超时，请稍后重试。' : error.message;
    $('empty').hidden = false;
  } finally {
    clearTimeout(timer); busy = false; $('submit').disabled = false; $('use-ai').disabled = !modelConfigured;
  }
}
$('form').addEventListener('submit', analyze);
document.querySelectorAll('[data-code]').forEach((button) => button.addEventListener('click', () => {
  $('symbol').value = button.dataset.code; analyze();
}));
$('download').addEventListener('click', () => {
  if (!report) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = report.symbol + '-analysis.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
window.addEventListener('resize', () => { if (report && !$('report').hidden) chart(report.datasets.history.data); });
fetch('/api/health').then((response) => response.json()).then((data) => {
  $('health').textContent = '● 数据服务已连接';
  modelConfigured = data.model_configured; $('use-ai').disabled = !modelConfigured;
  $('model-label').textContent = modelConfigured ? '模型已配置' : '未配置模型';
}).catch(() => { $('health').textContent = '数据服务未连接'; });
