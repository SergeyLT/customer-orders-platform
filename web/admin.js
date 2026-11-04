const $ = (s) => document.querySelector(s);
const content = $('#content');
let csrf = '', user = null, inviteCode = '', tab = 'orders', offset = 0;
let filters = { q: '', status: '', priority: '', sort: 'priority', service_id: '' };
const labels = { high: 'Высокий', medium: 'Средний', low: 'Низкий', unknown: 'Не определена', matched: 'Подходит по признакам', clarify: 'Нужно уточнить', new: 'Новая', in_progress: 'В работе', completed: 'Завершена', cancelled: 'Отменена', desktop: 'Компьютер', mobile: 'Мобильное устройство' };
const money = (n) => n == null ? 'Нужна оценка' : new Intl.NumberFormat('ru-RU').format(n) + ' ₽';
const date = (v) => new Date(v).toLocaleString('ru-RU');
function el(tag, text, cls) { const node = document.createElement(tag); if (text != null) node.textContent = String(text); if (cls) node.className = cls; return node; }
function message(text) { $('#notice').textContent = text; }
function button(text, action, cls = 'secondary') { const node = el('button', text, cls); node.type = 'button'; node.addEventListener('click', () => Promise.resolve().then(action).catch(showError)); return node; }
function showError(error) { const text=error.message || 'Не удалось выполнить действие'; message(text); if($('#modal').open) { let node=$('#modal-error'); if(!node) { node=el('p',null,'modal-error');node.id='modal-error';node.setAttribute('role','alert');node.tabIndex=-1;$('#modal-body').prepend(node); }node.textContent=text;node.focus(); } }
async function api(path, method = 'GET', body) {
  const headers = { Accept: 'application/json', 'X-Requested-With': 'CustomerOrders' };
  if (csrf) headers['X-CSRF-Token'] = csrf;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch('/api' + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin', cache: 'no-store' });
  let data=null;
  if(response.status!==204) { try { data=await response.json(); } catch { throw new Error('Сервис временно недоступен. Повторите действие позже.'); } }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/login') && path !== '/auth/me') signedOut();
    const detail = data?.detail;
    throw new Error(Array.isArray(detail) ? detail.map(x => `${x.field}: ${x.message}`).join('; ') : typeof detail === 'string' ? detail : 'Сервис временно недоступен');
  }
  return data;
}
async function refreshSetupAvailability() {
  $('#have-invite').hidden = true;
  let available = false;
  try { available = (await api('/auth/setup/status')).setup_available === true && !user; } catch { /* При недоступной проверке регистрация скрыта. */ }
  $('#have-invite').hidden = !available;
  if (!available) {
    inviteCode = '';
    $('#invite-form').hidden = true;
    $('#setup-form').hidden = true;
    $('#invite-form').reset();
    $('#setup-form').reset();
  }
  return available;
}
function signedOut() { csrf = ''; user = null; $('#workspace').hidden = true; $('#login').hidden = false; $('#identity').replaceChildren(); $('#modal').close(); refreshSetupAvailability(); }
async function signedIn(data) {
  user = data.admin; csrf = data.csrf_token; inviteCode = '';
  $('#have-invite').hidden = true;
  $('#login').hidden = true; $('#workspace').hidden = false;
  for (const form of document.querySelectorAll('#login form')) form.reset();
  $('#setup-form').hidden = true; $('#invite-form').hidden = true;
  $('#identity').replaceChildren(el('span', user.username + ' '), button('Выйти', async () => { await api('/auth/logout', 'POST'); signedOut(); message('Вы вышли из системы'); }));
  message(''); await render();
}
function formHandler(form, action) { form.addEventListener('submit', async event => { event.preventDefault(); const submit = form.querySelector('button[type=submit], button:not([type])'); if (submit) submit.disabled = true; try { await action(new FormData(form)); } catch (e) { showError(e); } finally { if (submit) submit.disabled = false; } }); }
formHandler($('#login-form'), async data => signedIn(await api('/auth/login', 'POST', Object.fromEntries(data))));
$('#have-invite').addEventListener('click', async () => { if (!await refreshSetupAvailability()) return; $('#invite-form').hidden = !$('#invite-form').hidden; $('#setup-form').hidden = true; inviteCode = ''; });
window.addEventListener('focus', () => { if (!user) refreshSetupAvailability(); });
formHandler($('#invite-form'), async data => { const code = data.get('code'); await api('/auth/setup/check', 'POST', { code }); inviteCode = code; $('#invite-form').reset(); $('#invite-form').hidden = true; $('#setup-form').hidden = false; message('Приглашение подтверждено. Создайте первый аккаунт.'); });
formHandler($('#setup-form'), async data => { if (data.get('password') !== data.get('confirm')) throw new Error('Пароли не совпадают'); await signedIn(await api('/auth/setup', 'POST', { username: data.get('username'), password: data.get('password'), code: inviteCode })); });
$('#close-modal').addEventListener('click', () => $('#modal').close());
$('#modal').addEventListener('close', () => $('#modal-body').replaceChildren());
function modal(title, body) { $('#modal-title').textContent = title; $('#modal-body').replaceChildren(body); if (!$('#modal').open) $('#modal').showModal(); }
function field(form, name, title, value = '', options = {}) {
  const label = el('label', title);
  const input = options.choices ? document.createElement('select') : document.createElement(options.textarea ? 'textarea' : 'input');
  input.name = name;
  if (options.choices) for (const [val, text] of options.choices) input.add(new Option(text, val));
  else input.type = options.type || 'text';
  for (const key of ['required', 'min', 'max', 'minLength', 'maxLength', 'pattern', 'autocomplete']) if (options[key] !== undefined) input[key] = options[key];
  input.value = value ?? '';
  label.append(input); form.append(label); return input;
}
function submit(form, text) { const b = el('button', text); b.type = 'submit'; form.append(b); }
function table(heads, rows) { const wrap = el('div', null, 'table-scroll'), table = el('table'), head = el('thead'), tr = el('tr'); heads.forEach(h => tr.append(el('th', h))); head.append(tr); const body = el('tbody'); rows.forEach(row => { const tr = el('tr'); row.forEach(value => { const td = el('td'); td.append(value instanceof Node ? value : el('span', value ?? '—')); tr.append(td); }); body.append(tr); }); table.append(head, body); wrap.append(table); return wrap; }
function badge(value) { return el('span', labels[value] || value, `badge ${value}`); }
function stat(label, value) { const n = el('div', null, 'stat'); n.append(el('span', label), el('strong', value)); return n; }
async function summary() { const data = await api('/admin/dashboard'); $('#summary').replaceChildren(stat('Всего заявок', data.total), ...['new', 'in_progress', 'completed'].map(status => stat(labels[status], data.statuses.find(x => x.label === status)?.count || 0))); $('#breakdown').replaceChildren(table(['Услуга','Заявки'],data.services.map(x=>[x.label,x.count])),table(['Статус','Заявки'],data.statuses.map(x=>[labels[x.label]||x.label,x.count]))); }
async function render() {
  message(''); content.replaceChildren(el('p', 'Загружаем…')); document.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-current', String(b.dataset.tab === tab)));
  await summary();
  if (tab === 'orders') await orders(); else if (tab === 'services') await services(); else if (tab === 'admins') await admins(); else if (tab === 'password') password(); else await analytics();
}
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { tab = b.dataset.tab; render().catch(showError); }));
async function orders() {
  const params = new URLSearchParams({ offset, limit: 20, ...Object.fromEntries(Object.entries(filters).filter(([,v]) => v)) });
  const [data, catalog] = await Promise.all([api('/admin/orders?' + params), api('/admin/services')]);
  const toolbar = el('form', null, 'toolbar');
  field(toolbar, 'q', 'Поиск по имени, компании, задаче, email', filters.q, { maxLength: 100 });
  field(toolbar, 'status', 'Статус', filters.status, { choices: [['', 'Все'], ...['new','in_progress','completed','cancelled'].map(x => [x, labels[x]])] });
  field(toolbar, 'service_id', 'Услуга', filters.service_id, { choices: [['', 'Все'], ...catalog.map(x => [x.id, x.title])] });
  field(toolbar, 'priority', 'Приоритет', filters.priority, { choices: [['','Все'], ...['high','medium','low'].map(x => [x,labels[x]])] });
  field(toolbar, 'sort', 'Порядок', filters.sort, { choices: [['priority','Приоритет → старые первыми'],['newest','Сначала новые'],['oldest','Сначала старые']] });
  submit(toolbar, 'Применить'); formHandler(toolbar, async fd => { filters = Object.fromEntries(fd); offset = 0; await orders(); });
  const rows = data.items.map(item => { const actions = el('div'); actions.append(button('Просмотр', () => detail(item.id))); const name = el('div'); name.append(el('strong', item.name), el('p', item.company || 'Компания не указана')); const priority = el('div'); priority.append(badge(item.effective_priority)); if (item.manual_priority) priority.append(el('p','Изменён вручную','muted')); return [name,item.service_title,money(item.budget),badge(item.status),priority,date(item.created_at),actions]; });
  const pager = el('div', null, 'pagination'); const prev = button('← Назад', async () => { offset = Math.max(0,offset-20); await orders(); }); prev.disabled = offset === 0;
  const next = button('Далее →', async () => { offset += 20; await orders(); }); next.disabled = offset+20 >= data.total;
  pager.append(prev,el('span',`${data.total ? offset+1 : 0}–${Math.min(offset+20,data.total)} из ${data.total}`),next);
  content.replaceChildren(toolbar, data.items.length ? table(['Клиент','Услуга','Бюджет','Статус','Приоритет','Создана','Действия'], rows) : el('div','Заявок по выбранным условиям пока нет','empty'),pager);
}
async function detail(id) {
  const item = await api('/admin/orders/' + id), box = el('div'), dl = el('dl');
  const names = { id:'Номер',name:'Имя',service_title:'Услуга',email:'Email',phone:'Телефон',telegram:'Telegram',company:'Компания',niche:'Ниша',company_size:'Размер команды',role:'Роль',budget:'Бюджет',desired_deadline:'Желаемый срок',preferred_contact:'Канал связи',contact_time:'Удобное время',task_description:'Описание задачи',comment:'Комментарий' };
  for (const [key,label] of Object.entries(names)) { const dd = el('dd'); const value = item[key]; if (key === 'email' && value) { const link = el('a', value); link.href = 'mailto:' + encodeURIComponent(value); dd.append(link); } else if (key === 'phone' && value) { const link = el('a', value); link.href = 'tel:' + value.replace(/[^+0-9]/g,''); dd.append(link); } else if (key === 'telegram' && value) { const link = el('a','@'+value); link.href = 'https://t.me/' + encodeURIComponent(value); link.target='_blank'; link.rel='noopener noreferrer'; dd.append(link); } else dd.textContent = key === 'budget' ? money(value) : value || '—'; dl.append(el('dt',label),dd); }
  box.append(dl,el('h3','Автоматическая оценка')); const p=item.priority; if(p) { box.append(el('p',`Приоритет: ${labels[p.level]}; срочность: ${labels[p.urgency]}; соответствие: ${labels[p.fit]}; готовность: ${labels[p.readiness]}. Баллы: ${p.score}. Правила v${p.version}.`)); box.append(el('p',`Рекомендуемое направление: ${p.recommended_team}. Персональный менеджер: ${p.personal_manager_recommended?'рекомендуется':'по решению администратора'}.`)); const ul=el('ul'); p.reasons.forEach(x=>ul.append(el('li',x))); box.append(ul); }
  box.append(el('p',`Метрики заявки: ${(item.metrics.elapsed_ms/1000).toFixed(1)} с до отправки; попыток ${item.metrics.submission_attempts}; повторное посещение: ${item.metrics.returning_visitor?'да':'нет'}.`));
  const update=el('form',null,'grid'); field(update,'status','Статус',item.status,{choices:['new','in_progress','completed','cancelled'].map(x=>[x,labels[x]])}); field(update,'priority','Ручной приоритет',item.manual_priority||'',{choices:[['','Автоматический'],...['high','medium','low'].map(x=>[x,labels[x]])]}); field(update,'comment','Причина изменения',item.priority_comment||'',{maxLength:500}); submit(update,'Сохранить');
  formHandler(update,async fd=>{ if(fd.get('priority')&&!fd.get('comment').trim()) throw new Error('Укажите причину изменения приоритета'); await api('/admin/applications/'+id,'PATCH',{status:fd.get('status')}); await api('/admin/applications/'+id+'/priority','PATCH',{priority:fd.get('priority')||null,comment:fd.get('comment')}); $('#modal').close(); await render(); message('Заявка обновлена'); });
  box.append(update); modal('Заявка · '+item.name,box);
}
async function services() {
  const data=await api('/admin/services');
  content.replaceChildren(button('Добавить услугу',()=>serviceForm(),''),table(['Название / slug','Диапазон бюджета','Состояние','Действия'],data.map(item=>{const title=el('div');title.append(el('strong',item.title),el('p',item.slug,'muted'));const actions=el('div');actions.append(button('Изменить',()=>serviceForm(item)));if(item.is_active) actions.append(button('Деактивировать',async()=>{if(!confirm('Услуга исчезнет с сайта. Старые заявки сохранятся. Продолжить?'))return;await api('/admin/services/'+item.id,'DELETE');await services();},'danger'));return[title,`${money(item.budget_min)} — ${money(item.budget_max)}`,item.is_active?'Активна':'Неактивна',actions];})));
}
function serviceForm(item={}) {
  const f=el('form');field(f,'title','Название',item.title,{required:true,minLength:2,maxLength:160});field(f,'slug','Slug · латиница и дефисы',item.slug,{required:true,pattern:'[a-z0-9]+(-[a-z0-9]+)*',minLength:2,maxLength:80});field(f,'description','Описание',item.description,{textarea:true,required:true,minLength:10,maxLength:2000});field(f,'budget_min','Бюджет от, ₽',item.budget_min??30000,{type:'number',required:true,min:0,max:1000000000});field(f,'budget_max','Бюджет до, ₽',item.budget_max??120000,{type:'number',required:true,min:0,max:1000000000});field(f,'is_active','Публикация',String(item.is_active??true),{choices:[['true','Активна'],['false','Неактивна']]});submit(f,'Сохранить');formHandler(f,async fd=>{await api('/admin/services'+(item.id?'/'+item.id:''),item.id?'PUT':'POST',{title:fd.get('title'),slug:fd.get('slug'),description:fd.get('description'),budget_min:Number(fd.get('budget_min')),budget_max:Number(fd.get('budget_max')),currency:'RUB',is_active:fd.get('is_active')==='true'});$('#modal').close();await services();message('Услуга сохранена');});modal(item.id?'Редактирование услуги':'Новая услуга',f);
}
async function admins() {
  const data=await api('/admin/admins');
  content.replaceChildren(el('p','Все администраторы имеют одинаковые права. Последний активный аккаунт защищён от деактивации.'),button('Добавить администратора',()=>adminForm(),''),table(['Логин','Состояние','Создан','Действия'],data.map(item=>{const actions=el('div');actions.append(button('Сбросить пароль',()=>adminForm(item)));actions.append(button(item.is_active?'Деактивировать':'Активировать',async()=>{if(!confirm('Изменить доступ '+item.username+'? При деактивации его сеансы будут завершены.'))return;await api('/admin/admins/'+item.id,'PATCH',{is_active:!item.is_active});await admins();}));return[item.username+(item.id===user.id?' · вы':''),item.is_active?'Активен':'Отключён',date(item.created_at),actions];})));
}
function adminForm(item) { const f=el('form');if(!item)field(f,'username','Логин','',{required:true,pattern:'[a-zA-Z0-9_.\\-]{3,80}',minLength:3,maxLength:80,autocomplete:'off'});field(f,'password','Новый пароль · от 16 символов','',{type:'password',required:true,minLength:16,maxLength:128,autocomplete:'new-password'});field(f,'confirm','Повторите пароль','',{type:'password',required:true,minLength:16,maxLength:128,autocomplete:'new-password'});submit(f,item?'Сменить пароль':'Создать');formHandler(f,async fd=>{if(fd.get('password')!==fd.get('confirm'))throw new Error('Пароли не совпадают');await api('/admin/admins'+(item?'/'+item.id:''),item?'PATCH':'POST',item?{password:fd.get('password')}:{username:fd.get('username'),password:fd.get('password')});$('#modal').close();if(item?.id===user.id){signedOut();message('Пароль изменён. Войдите заново.');}else{await admins();message('Аккаунт сохранён. Передайте пароль адресату по защищённому каналу.');}});modal(item?'Сброс пароля · '+item.username:'Новый администратор',f); }
function password() {const f=el('form');field(f,'current_password','Текущий пароль','',{type:'password',required:true,maxLength:128,autocomplete:'current-password'});field(f,'new_password','Новый пароль','',{type:'password',required:true,minLength:16,maxLength:128,autocomplete:'new-password'});field(f,'confirm','Повторите новый пароль','',{type:'password',required:true,minLength:16,maxLength:128,autocomplete:'new-password'});submit(f,'Изменить пароль и завершить сеансы');formHandler(f,async fd=>{if(fd.get('new_password')!==fd.get('confirm'))throw new Error('Пароли не совпадают');await api('/auth/password','POST',{current_password:fd.get('current_password'),new_password:fd.get('new_password')});signedOut();message('Пароль изменён. Войдите заново.');});content.replaceChildren(el('h2','Мой пароль'),f);}
async function analytics(device='desktop',days='7',kind='cursor') {
  const data=await api(`/admin/analytics?device=${device}&days=${days}&kind=${kind}`), toolbar=el('form',null,'toolbar');
  field(toolbar,'device','Устройство',device,{choices:[['desktop','Компьютер'],['mobile','Мобильное устройство']]});field(toolbar,'days','Период',days,{choices:[['1','Сегодня'],['7','7 дней'],['30','30 дней']]});field(toolbar,'kind','Карта',kind,{choices:[['cursor','Движения курсора'],['click','Клики']]});submit(toolbar,'Показать');formHandler(toolbar,fd=>analytics(fd.get('device'),fd.get('days'),fd.get('kind')));
  const stats=el('div',null,'stats');data.periods.forEach(p=>stats.append(stat(`Среднее активное время · ${p.days} дн.`,p.average_active_seconds+' с')));
  const period=data.periods.find(x=>String(x.days)===String(days)), funnel=el('div',null,'stats');[['Посещения',period.visits],['Выбрали услугу',period.selected],['Попытка отправки',period.attempted],['Подтверждение отправки',period.submitted]].forEach(([l,v])=>funnel.append(stat(l,v)));
  const chart=el('div',null,'chart');chart.append(el('h2',kind==='cursor'?'Карта движений курсора':'Карта кликов'),el('p','Нормализованные координаты всей страницы: слева направо и сверху вниз. Это сетка активности, а не снимок страницы. Устройства разделены; макет orders-v1.','muted'));
  const canvas=el('canvas');canvas.width=600;canvas.height=700;canvas.setAttribute('aria-label','Тепловая карта активности: '+data.heatmap.length+' заполненных ячеек');canvas.setAttribute('role','img');const ctx=canvas.getContext('2d');ctx.fillStyle='#f5f7f0';ctx.fillRect(0,0,600,700);ctx.strokeStyle='#e0e5d8';for(let x=0;x<=600;x+=60){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,700);ctx.stroke();}for(let y=0;y<=700;y+=70){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(600,y);ctx.stroke();}const max=Math.max(1,...data.heatmap.map(p=>p.count));data.heatmap.forEach(p=>{const x=(Math.min(p.x,39)+.5)/40*600,y=(Math.min(p.y,59)+.5)/60*700;const g=ctx.createRadialGradient(x,y,0,x,y,24);g.addColorStop(0,`rgba(190,105,42,${.2+.7*p.count/max})`);g.addColorStop(1,'rgba(190,105,42,0)');ctx.fillStyle=g;ctx.fillRect(x-24,y-24,48,48);});chart.append(canvas);if(!data.heatmap.length)chart.append(el('p','Данных для карты пока нет. Они появятся после посещений с согласием на аналитику.'));
  content.replaceChildren(toolbar,stats,el('p','Периоды считаются по UTC, включая сегодня. Среднее — активное время на посещение за сутки. Повтор в разные дни учитывается отдельно. События и воронка переданы браузером и не являются аудитом. Сырые данные хранятся 30 дней, агрегаты — 365 дней.','muted'),funnel,chart,el('h3','Клики по элементам'),table(['Элемент','Клики'],data.clicks.map(x=>[x.target,x.count])));
}
api('/auth/me').then(signedIn).catch(() => signedOut());
