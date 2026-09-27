const form = document.querySelector('#request-form');
const list = document.querySelector('#request-list');
const feedback = document.querySelector('#feedback');
const button = document.querySelector('#create-button');
const keyField = document.querySelector('#key-field');
const keyInput = document.querySelector('#api-key');
const originInput = document.querySelector('#origin');
const destinationInput = document.querySelector('#destination');
const cargoInput = document.querySelector('#cargo');
const tracked = JSON.parse(localStorage.getItem('fleetRequests') || '[]').slice(0, 12);
let localKey = '';

async function configure() {
  try {
    const response = await fetch('/dev-config');
    if (response.ok) localKey = (await response.json()).api_key;
    else keyField.classList.remove('hidden');
  } catch {
    keyField.classList.remove('hidden');
  }
  if (tracked.length) refresh();
}

function show(message, success = false) {
  feedback.textContent = message;
  feedback.classList.toggle('success', success);
}

function authHeaders() {
  return { 'X-API-Key': localKey || keyInput.value.trim() };
}

async function refresh() {
  if (!tracked.length) return;
  const results = await Promise.all(tracked.map(async (id) => {
    try {
      const response = await fetch(`/requests/${encodeURIComponent(id)}`, { headers: authHeaders() });
      if (!response.ok) return null;
      return await response.json();
    } catch { return null; }
  }));
  const records = results.filter(Boolean);
  if (!records.length) return;
  list.replaceChildren(...records.map(card));
}

function card(item) {
  const node = document.createElement('article');
  node.className = `request ${item.status.toLowerCase()}`;
  const top = document.createElement('div');
  top.className = 'request-top';
  const id = document.createElement('span');
  id.className = 'request-label';
  id.textContent = `PEDIDO ${item.id.slice(0, 8).toUpperCase()}`;
  const status = document.createElement('span');
  status.className = 'badge';
  status.textContent = { CREATED: 'AGUARDANDO', ASSIGNED: 'VEÍCULO ALOCADO', REJECTED: 'SEM VEÍCULO' }[item.status] || item.status;
  top.append(id, status);
  const route = document.createElement('div');
  route.className = 'request-route';
  const from = document.createElement('span');
  from.textContent = item.origin;
  const arrow = document.createElement('span');
  arrow.className = 'arrow';
  arrow.textContent = '→';
  const to = document.createElement('span');
  to.textContent = item.destination;
  route.append(from, arrow, to);
  const meta = document.createElement('p');
  meta.className = 'request-meta';
  meta.textContent = `${Number(item.cargo_kg).toLocaleString('pt-BR')} kg · ${item.vehicle_id || 'Alocação em andamento'}`;
  if (item.status === 'REJECTED') meta.textContent = `${Number(item.cargo_kg).toLocaleString('pt-BR')} kg · Nenhum veículo disponível com essa capacidade`;
  node.append(top, route, meta);
  return node;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  if (!localKey && !keyInput.value.trim()) return show('Informe a chave de API definida no .env.');
  button.disabled = true;
  show('Registrando solicitação...', true);
  const data = {
    origin: originInput.value.trim(),
    destination: destinationInput.value.trim(),
    cargo_kg: Number(cargoInput.value),
  };
  try {
    const response = await fetch('/requests', {
      method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(response.status === 401 ? 'Chave de API incorreta.' : `Não foi possível criar a solicitação: ${result.error || response.status}`);
    tracked.unshift(result.request_id);
    tracked.splice(12);
    localStorage.setItem('fleetRequests', JSON.stringify(tracked));
    show('Solicitação criada. Aguardando alocação do veículo.', true);
    originInput.value = '';
    destinationInput.value = '';
    cargoInput.value = '';
    refresh();
  } catch (error) {
    show(error.message || 'Conexão indisponível. Verifique se os serviços estão em execução.');
  } finally {
    button.disabled = false;
  }
});

keyInput.addEventListener('change', refresh);
configure();
setInterval(() => { if (document.visibilityState === 'visible') refresh(); }, 1500);
