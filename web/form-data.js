export function applicationPayload(values, metrics) {
  const optional = (key) => String(values.get(key) ?? '').trim() || null;
  const estimate = values.get('estimate') === 'on';
  return {
    service_id: Number(values.get('service_id')),
    name: String(values.get('name') ?? '').trim(),
    email: optional('email'), phone: optional('phone'), telegram: optional('telegram'),
    task_description: String(values.get('task_description') ?? '').trim(),
    company: optional('company'), niche: optional('niche'), company_size: optional('company_size'),
    role: optional('role'), budget: estimate ? null : Number(values.get('budget')),
    desired_deadline: optional('desired_deadline'), preferred_contact: values.get('preferred_contact') || 'any',
    contact_time: optional('contact_time'), comment: optional('comment'), metrics,
  };
}

export function contactError(payload) {
  if (!payload.email && !payload.phone && !payload.telegram) return 'Укажите хотя бы один контакт: email, телефон или Telegram.';
  if (payload.preferred_contact !== 'any' && !payload[payload.preferred_contact]) return 'Заполните контакт для выбранного способа связи.';
  return '';
}

export function errorMessage(data) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item.message || 'Проверьте заполнение полей.').join(' ');
  return 'Не удалось отправить заявку. Попробуйте ещё раз.';
}
