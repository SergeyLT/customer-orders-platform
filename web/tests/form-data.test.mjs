import test from 'node:test';
import assert from 'node:assert/strict';
import { applicationPayload, contactError, errorMessage } from '../form-data.js';

test('Нужна оценка отправляется как null, необязательные пустые поля не становятся строками', () => {
  const fields = new FormData();
  fields.set('service_id', '3'); fields.set('name', ' Сергей '); fields.set('email', 'sergey@example.com'); fields.set('estimate', 'on');
  const result = applicationPayload(fields, { elapsed_ms: 100, submission_attempts: 1, returning_visitor: false });
  assert.equal(result.budget, null); assert.equal(result.company, null); assert.equal(result.name, 'Сергей'); assert.equal(result.service_id, 3);
  assert.equal(contactError(result), '');
});
test('Выбранный канал связи требует соответствующий контакт', () => {
  assert.match(contactError({ email: 'a@example.com', preferred_contact: 'telegram' }), /выбранного/);
  assert.match(contactError({ preferred_contact: 'any' }), /хотя бы один/);
});
test('Сообщения валидации извлекаются без вывода исходных данных', () => {
  assert.equal(errorMessage({ detail: [{ field: 'phone', message: 'Проверьте телефон' }] }), 'Проверьте телефон');
});
