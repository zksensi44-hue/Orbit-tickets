# Orbit Apps Transcripts — Render

Servidor independente para hospedar os HTMLs de tickets. O código do bot envia arquivos para `/api/v1/transcript/upload`; os links públicos ficam em `/transcript/<id>`.

## Importante: armazenamento

O sistema usa MongoDB para que as transcrições não dependam do disco temporário do Render. Crie um banco MongoDB acessível pelo servidor (por exemplo, um cluster MongoDB Atlas) e configure `TRANSCRIPT_MONGODB_URI` no Render. Não coloque a URI no GitHub nem no código.

## Publicar no Render

1. Envie o projeto ao seu repositório GitHub, mantendo a pasta `orbit_transcript_server`.
2. No Render, crie um Web Service ligado ao repositório. Use o `render.yaml` que fica na raiz do repositório para criar o serviço como Blueprint. Se criar manualmente, configure Root Directory `orbit_transcript_server`, Build Command `pip install -r requirements.txt` e Start Command `gunicorn app:app`.
3. Escolha Free. O Render dará um endereço `https://NOME-DO-SERVICO.onrender.com`.
4. Em Environment, configure `TRANSCRIPT_MONGODB_URI` com a connection string do seu MongoDB. O token `TRANSCRIPT_UPLOAD_TOKEN` é gerado pelo Blueprint; copie o mesmo valor para o ambiente em que o bot roda. Nunca publique esse token.
5. Abra `https://SEU-SERVICO.onrender.com/health`; deve aparecer `{"status":"ok","service":"orbit-apps-transcripts"}`.
6. No bot, configure a variável de ambiente `TRANSCRIPT_API_URL` com `https://SEU-SERVICO.onrender.com` e `TRANSCRIPT_UPLOAD_TOKEN` com o mesmo token do Render. Alternativamente, coloque a URL real no campo `transcripts` de `configs/config_api.json`. Reinicie o bot.
7. Feche um ticket de teste e clique em **Ver transcript**.

## Configurações do servidor

- `TRANSCRIPT_MONGODB_URI` (obrigatória): URI privada do banco MongoDB.
- `TRANSCRIPT_UPLOAD_TOKEN` (obrigatória para upload): token compartilhado entre bot e servidor.
- `TRANSCRIPT_DB_NAME` (opcional, padrão `orbit_transcripts`).
- `TRANSCRIPT_TTL_DAYS` (opcional, padrão `3`).
- `PUBLIC_BASE_URL` (opcional): URL pública fixa do serviço se precisar substituir a URL detectada automaticamente.
- `MAX_TRANSCRIPT_BYTES` (opcional, padrão 8 MiB).

O Render Free pode dormir após inatividade, então o primeiro acesso pode demorar. O serviço usa política de segurança para bloquear scripts em conteúdo de transcrição, pois mensagens do Discord são conteúdo não confiável.
