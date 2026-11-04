// Swagger использует тот же HttpOnly-сеанс, что и /admin.
const originalFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const url = new URL(typeof input === 'string' ? input : input.url, location.href);
  if(url.origin === location.origin && url.pathname.startsWith('/api/') && !['GET','HEAD'].includes((init.method || input.method || 'GET').toUpperCase())) {
    const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
    headers.set('X-Requested-With','CustomerOrders');
    const response = await originalFetch('/api/auth/me');
    if(response.ok) headers.set('X-CSRF-Token',(await response.json()).csrf_token);
    init = { ...init, headers };
  }
  return originalFetch(input,init);
};
