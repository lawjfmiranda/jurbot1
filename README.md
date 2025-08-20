# JustIA - Chatbot de WhatsApp para Escritório de Advocacia

Projeto Flask com integrações ao WhatsApp (Evolution API), Google Calendar e SQLite.

## 🔒 **MELHORIAS DE SEGURANÇA IMPLEMENTADAS**
- **Proteção contra SQL Injection** em consultas do banco
- **Validação e sanitização** completa de inputs
- **Rate limiting robusto** e persistente
- **Logs seguros** com mascaramento de dados sensíveis
- **Sistema de configuração** centralizado com validação
- **Métricas e monitoramento** básico

## Estrutura
- `app.py`: inicialização Flask, endpoint webhook `/webhook/evolution`, healthcheck, scheduler.
- `chatbot_logic.py`: lógica conversacional, qualificação de leads, agendamento, estados.
- `database.py`: criação e acesso ao SQLite (`advocacia.db`).
- `calendar_service.py`: integração Google Calendar (freebusy, criação de evento).
- `whatsapp_service.py`: envio de mensagens via Evolution API.
- `notification_service.py`: notificação interna (webhook ou SMTP).
- `scheduler.py`: lembretes e follow-ups.
- `faq.json`: conteúdo editável de FAQs, com saudação, bio, áreas e informações do escritório (JM ADVOGADOS).
- `ai_service.py`: integração com IA (Gemini) para intenção e respostas informativas.
- `config.py`: sistema de configuração centralizado com validação.
- **`utils/`**: utilitários de segurança e monitoramento
  - `validators.py`: validação e sanitização de inputs
  - `secure_logging.py`: logs seguros com mascaramento
  - `rate_limiter.py`: rate limiting robusto e persistente
  - `metrics.py`: sistema de métricas e health checks

## Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto com:

```
PORT=8000
TIMEZONE=America/Sao_Paulo
DB_PATH=./advocacia.db
FAQ_PATH=./faq.json

# Evolution API
EVOLUTION_API_BASE_URL=https://evolution.yourdomain.com/api
EVOLUTION_INSTANCE_ID=instance123
EVOLUTION_API_KEY=your_api_key
EVOLUTION_WEBHOOK_TOKEN=optional_shared_secret
ADMIN_WHATSAPP=554499999999  # número admin com comandos: #pause [min], #resume, #status

# Google
GOOGLE_CALENDAR_ID=primary_or_calendar_id
# Conteúdo JSON do service account (tudo em uma linha ou multiline suportado)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account", "project_id":"...", "private_key_id":"...", "private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n", "client_email":"...", "client_id":"...", "token_uri":"https://oauth2.googleapis.com/token"}

# Notificações internas (opcional)
INTERNAL_WEBHOOK_URL=https://hooks.yourdomain.com/lead
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_user
SMTP_PASS=your_pass
EMAIL_FROM=bot@yourdomain.com
EMAIL_TO=suporte@yourdomain.com
# Calendar (opcional)
# Para evitar erro 403 com contas de serviço sem delegação ampla, não convidamos participantes por padrão
CALENDAR_ALLOW_ATTENDEES=0

# IA (Gemini)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-flash
GEMINI_MODEL_QUALITY=gemini-1.5-pro

# Segurança e Rate Limiting
MAX_REQUESTS_PER_MINUTE=20
RATE_LIMIT_BLOCK_DURATION=300
MASK_SENSITIVE_DATA=1

# Monitoramento (opcional)
ADMIN_TOKEN=your_secret_admin_token
```

## Instalação
```
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell
pip install -r requirements.txt
python -m app
```

## Webhook Evolution
Você pode configurar via painel ou API. URL recomendada: `https://seu-dominio/webhook/evolution?token=EVOLUTION_WEBHOOK_TOKEN`.
Ou use a API oficial ([set webhook](https://doc.evolution-api.com/v2/api-reference/webhook/set)) com:
```bash
curl --request POST \
  --url "$EVOLUTION_API_BASE_URL/webhook/set/$EVOLUTION_INSTANCE_ID" \
  --header 'Content-Type: application/json' \
  --header "apikey: $EVOLUTION_API_KEY" \
  --data '{
  "enabled": true,
  "url": "https://seu-dominio/webhook/evolution?token='"$EVOLUTION_WEBHOOK_TOKEN"'",
  "webhookByEvents": true,
  "webhookBase64": false,
  "events": ["MESSAGE"]
}'
```

## 📊 **Novos Endpoints de Monitoramento**

### Health Checks
- `GET /health` - Health check básico
- `GET /health/detailed` - Health check detalhado com status de todos os serviços
- `GET /metrics` - Métricas completas do sistema (requer ADMIN_TOKEN)

### Exemplo de Resposta de Métricas:
```json
{
  "timestamp": "2025-01-20T12:00:00",
  "uptime_seconds": 3600,
  "counters": {
    "webhook_requests": 150,
    "messages_processed": 142,
    "chatbot_success": 140,
    "chatbot_errors": 2
  },
  "rates": {
    "messages_processed_per_minute": 2.3
  },
  "service_health": {
    "database": {"status": "healthy"},
    "evolution_api": {"status": "healthy"},
    "google_calendar": {"status": "healthy"}
  }
}
```

## Observações
- Datas são persistidas em UTC no banco.
- Slots de agenda consideram dias úteis (9h–18h) e verificam free/busy.
- Lembretes são enviados 24h antes; follow-up é enviado diariamente às 09:00.
- Se `GEMINI_API_KEY` não estiver definido, o chatbot usa heurísticas simples; com a chave, ativa respostas de IA com limite de extensão e disclaimers.
- **Rate limiting**: 20 requests/minuto por usuário (configurável)
- **Dados sensíveis**: Automaticamente mascarados nos logs
- **Validação**: Todos os inputs são sanitizados contra ataques
