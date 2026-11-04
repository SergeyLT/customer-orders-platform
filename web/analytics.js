// Только события из закрытого списка; значения полей и клавиатура не читаются.
const POLICY = 'orders-analytics-v1';
let consent = false, visit = null, pending = null, queue = [], activeMs = 0;
let lastActivity = performance.now(), lastTick = performance.now(), cursor = null, flushing = false, generation = 0;
const banner = document.createElement('aside'); banner.className = 'analytics-consent'; banner.setAttribute('aria-label', 'Настройка аналитики');
const text = document.createElement('p'); text.textContent = 'Помогите улучшить сайт: разрешите собирать активное время, клики и координаты курсора. Содержимое формы в эту аналитику не передаётся. Сырые события — 30 дней, суточные показатели — 12 месяцев. Отказ не мешает отправить заявку.';
function choice(label, action) { const b = document.createElement('button'); b.type = 'button'; b.className = 'text-button'; b.textContent = label; b.addEventListener('click', action); return b; }
const controls = document.createElement('div'); controls.append(choice('Разрешить', () => setConsent(true)), choice('Отказаться', () => setConsent(false))); banner.append(text, controls); document.body.append(banner);
const settings = choice('Настройки аналитики', () => { banner.hidden = false; }); settings.classList.add('analytics-settings'); document.querySelector('footer').append(settings);
async function post(path, body, keepalive = false) { const r = await fetch('/api/analytics/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), keepalive }); if (!r.ok) { const error = new Error('analytics'); error.status = r.status; throw error; } return r.json(); }
function stored() { try { return localStorage.getItem(POLICY); } catch { return null; } }
function setConsent(value) { consent = value; generation++; visit = null; pending = null; queue = []; activeMs = 0; lastTick = performance.now(); lastActivity = performance.now(); banner.hidden = true; try { localStorage.setItem(POLICY, value ? 'yes' : 'no'); } catch { /* Согласие действует до закрытия страницы. */ } if(value) begin(); }
async function begin() { const id = generation; try { const data = await post('visits', { consent: true, device: innerWidth <= 700 ? 'mobile' : 'desktop', layout: 'orders-v1' }); if (consent && id === generation) visit = data; } catch { /* Аналитика никогда не блокирует форму. */ } }
function event(kind, target = 'page', point = null) { if(!consent || !visit) return; const width = Math.max(200, Math.min(16000, document.documentElement.clientWidth)); const height = Math.max(200, Math.min(100000, document.documentElement.scrollHeight)); const item = { kind, target, width, height }; if(point) { item.x = Math.max(0,Math.min(10000,Math.round(point.x/width*10000))); item.y = Math.max(0,Math.min(10000,Math.round(point.y/height*10000))); } if(queue.length < 30) queue.push(item); }
async function flush(keepalive=false) { if(!consent || !visit || flushing) return; if(!pending) pending = { ...visit, batch_id: crypto.randomUUID(), active_ms: Math.round(activeMs), events: queue.splice(0,30) }; const id=generation; flushing = true; try { await post('batches', pending, keepalive); if(id===generation) pending = null; } catch(error) { if(error.status===403 && id===generation && consent) { generation++; visit=null;pending=null;queue=[];activeMs=0;begin(); } /* Иначе повторяем тот же UUID пакета. */ } finally { flushing = false; } }
document.addEventListener('pointermove',e=>{ lastActivity=performance.now(); cursor={x:e.pageX,y:e.pageY}; },{passive:true});
for(const name of ['pointerdown','scroll','touchstart','input']) document.addEventListener(name,()=>{lastActivity=performance.now();},{passive:true});
document.addEventListener('click', e=>{ const target=e.target.closest('button,a,summary'); if(!target || target.closest('.analytics-consent') || target.classList.contains('analytics-settings')) return; let name='navigation'; if(target.closest('.service-card'))name='service';else if(target.id==='submit-order')name='submit';else if(target.closest('#order-form'))name='form';else if(target.matches('summary'))name='details';else if(target.classList.contains('button'))name='cta';event('click',name,{x:e.pageX,y:e.pageY});if(name==='service')event('selected','service'); });
document.querySelector('[name=service_id]').addEventListener('change',()=>event('selected','service'));
document.querySelector('#order-form').addEventListener('submit',()=>event('attempted','submit'));
document.addEventListener('orders:submitted',()=>{event('submitted','submit');flush();});
setInterval(()=>{ const current=performance.now();if(consent && visit && document.visibilityState==='visible' && current-lastActivity<60000){activeMs+=Math.min(1000,current-lastTick);if(cursor)event('cursor','page',cursor);}lastTick=current; },1000);
setInterval(()=>flush(),10000);
document.addEventListener('visibilitychange',()=>{lastTick=performance.now();if(document.visibilityState==='hidden')flush(true);});
window.addEventListener('pagehide',()=>flush(true));
const saved=stored();banner.hidden=saved!==null;if(saved==='yes'){consent=true;begin();}
