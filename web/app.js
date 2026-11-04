import { applicationPayload, contactError, errorMessage } from './form-data.js';

const form = document.querySelector('#order-form');
const select = form.elements.service_id;
const catalog = document.querySelector('#services-list');
const submit = document.querySelector('#submit-order');
const message = document.querySelector('#form-message');
const range = form.elements.budget;
const estimate = form.elements.estimate;
const budgetValue = document.querySelector('#budget-value');
const started = performance.now();
let services = [];
let attempts = 0;
let busy = false;
let idempotencyKey = null;
let returning = false;
try {
  returning = localStorage.getItem('orders-visited') === '1';
  localStorage.setItem('orders-visited', '1');
} catch { /* Сайт продолжает работать без localStorage. */ }

const money = (value) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value);
const element = (tag, className, text) => {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
};

function updateBudget() {
  const service = services.find((item) => item.id === Number(select.value));
  range.disabled = !service || estimate.checked;
  if (service) {
    range.min = service.budget_min;
    range.max = service.budget_max;
    range.step = 1;
    if (Number(range.value) < service.budget_min || Number(range.value) > service.budget_max) range.value = service.budget_min;
    document.querySelector('#budget-min').textContent = money(service.budget_min);
    document.querySelector('#budget-max').textContent = money(service.budget_max);
  } else {
    document.querySelector('#budget-min').textContent = 'Выберите услугу';
    document.querySelector('#budget-max').textContent = '';
  }
  budgetValue.textContent = estimate.checked ? 'Нужна оценка' : money(Number(range.value));
  for (const card of catalog.querySelectorAll('.service-card')) card.setAttribute('aria-pressed', String(card.dataset.id === select.value));
}

async function loadServices() {
  catalog.replaceChildren(element('div', 'catalog-state', 'Загружаем услуги…'));
  submit.disabled = true;
  try {
    const response = await fetch('/api/services', { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!response.ok) throw new Error('catalog');
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error('catalog');
    services = data;
    select.replaceChildren(new Option('Выберите услугу', ''));
    catalog.replaceChildren();
    if (!services.length) {
      catalog.append(element('div', 'catalog-state', 'Каталог услуг готовится к публикации. Приём заявок пока недоступен.'));
      select.disabled = true;
      return;
    }
    services.forEach((service, index) => {
      select.add(new Option(service.title, String(service.id)));
      const card = element('button', 'service-card');
      card.type = 'button';
      card.dataset.id = String(service.id);
      card.setAttribute('aria-pressed', 'false');
      card.append(element('span', 'service-number', `${String(index + 1).padStart(2, '0')} / НАПРАВЛЕНИЕ`), element('h3', '', service.title), element('p', '', service.description));
      const price = element('span', 'service-price');
      price.append(element('strong', '', `${money(service.budget_min)} — ${money(service.budget_max)}`), element('span', 'arrow', '↗'));
      card.append(price);
      card.addEventListener('click', () => {
        select.value = String(service.id);
        idempotencyKey = null;
        updateBudget();
        document.querySelector('#request').scrollIntoView({ behavior: 'smooth' });
        select.focus({ preventScroll: true });
      });
      catalog.append(card);
    });
    select.disabled = false;
    submit.disabled = false;
    updateBudget();
  } catch {
    const state = element('div', 'catalog-state', 'Не удалось загрузить услуги. ');
    const retry = element('button', 'text-button', 'Попробовать ещё раз');
    retry.type = 'button';
    retry.addEventListener('click', loadServices);
    state.append(retry);
    catalog.replaceChildren(state);
    select.disabled = true;
  }
}

form.addEventListener('input', () => { idempotencyKey = null; message.textContent = ''; });
select.addEventListener('change', updateBudget);
estimate.addEventListener('change', updateBudget);
range.addEventListener('input', updateBudget);

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  attempts = Math.min(attempts + 1, 100);
  message.textContent = '';
  if (!form.reportValidity()) return;
  const payload = applicationPayload(new FormData(form), {
    elapsed_ms: Math.min(Math.round(performance.now() - started), 86400000),
    submission_attempts: attempts,
    returning_visitor: returning,
  });
  const problem = contactError(payload);
  if (problem) { message.textContent = problem; message.focus(); return; }
  if (!idempotencyKey) idempotencyKey = crypto.randomUUID();
  busy = true;
  submit.disabled = true;
  submit.textContent = 'Отправляем…';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch('/api/applications', {
      method: 'POST', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(payload),
    });
    let data;
    try { data = await response.json(); } catch { throw new Error('Сервис временно недоступен. Повторите отправку позже.'); }
    if (!response.ok) throw new Error(errorMessage(data));
    if (typeof data.id !== 'string') throw new Error('Не удалось получить подтверждение. Повторите отправку.');
    document.dispatchEvent(new Event('orders:submitted'));
    document.querySelector('#form-fields').hidden = true;
    document.querySelector('#receipt-id').textContent = data.id;
    const success = document.querySelector('#success-panel');
    success.hidden = false;
    success.focus();
  } catch (error) {
    message.textContent = error instanceof TypeError || error.name === 'AbortError'
      ? 'Не удалось получить подтверждение от сервера. Повторите отправку — повторная заявка не будет создана.'
      : error.message;
    message.focus();
  } finally {
    clearTimeout(timer);
    busy = false;
    submit.disabled = false;
    submit.innerHTML = 'Отправить заявку <span class="arrow" aria-hidden="true">↗</span>';
  }
});

document.querySelector('#new-order').addEventListener('click', () => {
  form.reset();
  attempts = 0;
  idempotencyKey = null;
  message.textContent = '';
  document.querySelector('#success-panel').hidden = true;
  document.querySelector('#form-fields').hidden = false;
  updateBudget();
  select.focus();
});

loadServices();
