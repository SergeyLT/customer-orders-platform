import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { setImmediate as nextTurn } from 'node:timers/promises';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const html = await readFile(new URL('../admin.html', import.meta.url), 'utf8');
const source = await readFile(new URL('../admin.js', import.meta.url), 'utf8');

async function until(predicate, window) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (predicate()) return;
    await nextTurn();
  }
  assert.fail('Ожидаемое состояние не появилось: ' + window.document.querySelector('#notice').textContent);
}

async function openAdmin(t) {
  const dom = new JSDOM(html, { url: 'https://orders.example.com/admin', runScripts: 'outside-only' });
  const { window } = dom;
  t.after(() => window.close());
  // Диалог и canvas заменены; реальные DOM-свойства input/select/textarea не подменяются.
  window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  window.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new window.Event('close')); };
  window.HTMLCanvasElement.prototype.getContext = () => ({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
    createRadialGradient() { return { addColorStop() {} }; },
  });
  const requests = [];
  const services = [];
  window.fetch = async (path, init = {}) => {
    requests.push({ path, ...init });
    const url = new URL(path, window.location.href);
    let data;
    if (url.pathname === '/api/auth/me') data = { admin: { id: 'test-admin', username: 'operator' }, csrf_token: 'synthetic-csrf' };
    else if (url.pathname === '/api/admin/dashboard') data = { total: 0, statuses: [], services: [] };
    else if (url.pathname === '/api/admin/orders') data = { items: [], total: 0 };
    else if (url.pathname === '/api/admin/services' && init.method === 'GET') data = services;
    else if (url.pathname === '/api/admin/services' && init.method === 'POST') {
      data = { id: 1, ...JSON.parse(init.body) }; services.push(data);
    } else if (url.pathname === '/api/admin/services/1' && init.method === 'PUT') {
      data = { id: 1, ...JSON.parse(init.body) }; services[0] = data;
    } else if (url.pathname === '/api/admin/analytics') {
      assert.ok(['1', '7', '30'].includes(url.searchParams.get('days')));
      data = { periods: [1, 7, 30].map(days => ({ days, visits: 0, average_active_seconds: 0, selected: 0, attempted: 0, submitted: 0 })), heatmap: [], clicks: [] };
    } else throw new Error('Неожиданный запрос: ' + path);
    return { ok: true, status: 200, json: async () => structuredClone(data) };
  };
  // В браузере admin.js подключён как module и выполняется в strict mode.
  window.eval('"use strict";\n' + source);
  await until(() => !window.document.querySelector('#workspace').hidden && window.document.querySelector('#content .pagination'), window);
  return { window, requests };
}

function clickText(window, root, text) {
  const button = [...root.querySelectorAll('button')].find(node => node.textContent === text);
  assert.ok(button, 'Нет кнопки: ' + text);
  button.click();
}

test('Админка открывает форму услуги с textarea, создаёт и редактирует услугу', async t => {
  const { window, requests } = await openAdmin(t);
  const document = window.document;
  document.querySelector('[data-tab="services"]').click();
  await until(() => document.querySelector('#content > button'), window);
  clickText(window, document.querySelector('#content'), 'Добавить услугу');
  await until(() => document.querySelector('#modal').open, window);
  let form = document.querySelector('#modal form');
  assert.equal(form.elements.description.tagName, 'TEXTAREA');
  assert.equal(form.elements.description.type, 'textarea');
  assert.equal(form.elements.budget_min.type, 'number');
  form.elements.title.value = 'Автоматизация документов';
  form.elements.slug.value = 'document-automation';
  form.elements.description.value = 'Создание документов по данным из CRM.';
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await until(() => !document.querySelector('#modal').open && document.querySelector('#notice').textContent === 'Услуга сохранена', window);
  const created = JSON.parse(requests.find(request => request.method === 'POST').body);
  assert.equal(created.description, 'Создание документов по данным из CRM.');
  assert.equal(created.budget_min, 30000);
  clickText(window, document.querySelector('#content'), 'Изменить');
  await until(() => document.querySelector('#modal').open, window);
  form = document.querySelector('#modal form');
  assert.equal(form.elements.description.value, created.description);
  form.elements.description.value = 'Создание и доставка документов по данным из CRM.';
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await until(() => !document.querySelector('#modal').open, window);
  assert.equal(JSON.parse(requests.find(request => request.method === 'PUT').body).description, form.elements.description.value);
});

test('Админка загружает статистику и переключает периоды 1/7/30 дней', async t => {
  const { window, requests } = await openAdmin(t);
  const document = window.document;
  document.querySelector('[data-tab="analytics"]').click();
  await until(() => document.querySelector('#content select[name="days"]'), window);
  for (const days of ['1', '7', '30']) {
    const form = document.querySelector('#content form');
    form.elements.days.value = days;
    const previous = requests.length;
    form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    await until(() => requests.length > previous && document.querySelector('#content form') !== form, window);
    assert.equal(new URL(requests.at(-1).path, window.location.href).searchParams.get('days'), days);
    assert.equal(document.querySelector('#content select[name="days"]').value, days);
  }
  assert.equal(document.querySelector('#notice').textContent, '');
});
