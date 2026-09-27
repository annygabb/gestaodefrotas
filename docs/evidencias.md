# Roteiro de evidências para entrega

O projeto inclui código e um teste automatizado, mas **não contém prints fabricados**. Execute os passos no próprio computador, capture as saídas e anexe os arquivos à submissão se o professor pedir imagens ou vídeo.

1. Execute `npm run dev`, abra `http://localhost:8100` e capture a tela e o terminal com os serviços em execução. Alternativamente execute `docker compose up --build -d` e capture `docker compose ps` com gateway, broker, Solicitações, Frota, Notificações e duas instâncias de Despacho.
2. Faça `POST /requests` conforme README e capture o HTTP `202` com `request_id` e `correlation_id`.
3. Consulte `GET /requests/{uuid}` até aparecer `ASSIGNED` ou `REJECTED`; registre a mudança de status. O tempo de `CREATED` pode ser curto demais para capturar por polling manual.
4. Capture `docker compose logs --tail=80 requests broker dispatch-a dispatch-b fleet notifications` e mostre o mesmo `correlation_id` em múltiplos serviços. Use as consultas internas do README para mostrar `peer_seen: true` e o mesmo ID no cache das duas instâncias.
5. Mostre `401` removendo `X-API-Key` e `400` com `cargo_kg: -1`.
6. Execute `python3 tests/smoke.py` em ambiente onde as portas 8100–8106, 8200 e 8301–8302 estejam livres (não rode simultaneamente ao `npm run dev` ou Compose). Registre a linha `PASS`, que inclui teste de DLQ. Alternativamente faça uma gravação de tela de até cinco minutos dessas operações.

Para testar indisponibilidade de consumidor com Compose, pare `notifications` usando `docker compose stop notifications`, crie uma solicitação e confirme o status; reinicie com `docker compose start notifications` e confira que a notificação pendente foi registrada. Para testar múltiplas instâncias, faça mais de uma solicitação e procure `assignment_decided` nos logs de ambas. A atribuição individual entre os dois consumidores não é garantida em um lote pequeno, embora ambos estejam aptos a competir.
