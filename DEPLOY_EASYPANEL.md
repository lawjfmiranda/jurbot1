# Deploy no EasyPanel - Instruções

## 🚨 IMPORTANTE: Persistência de Dados

Para evitar perda de dados dos clientes e agendamentos a cada deploy, é ESSENCIAL configurar um volume persistente.

### Configuração no EasyPanel:

1. **Acesse seu projeto** no EasyPanel
2. **Vá em "Volumes"** 
3. **Crie um novo volume:**
   - Nome: `jurbot_data`
   - Mount Path: `/app/data`
   - Tipo: Persistent Volume

4. **Configure as variáveis de ambiente:**
   ```
   DB_PATH=/app/data/advocacia.db
   FAQ_PATH=/app/faq.json
   ```

5. **Outras variáveis necessárias:**
   ```
   PORT=8000
   TIMEZONE=America/Sao_Paulo
   
   # Evolution API
   EVOLUTION_API_BASE_URL=https://evolution.yourdomain.com/api
   EVOLUTION_INSTANCE_ID=instance123
   EVOLUTION_API_KEY=your_api_key
   EVOLUTION_WEBHOOK_TOKEN=optional_shared_secret
   ADMIN_WHATSAPP=554499999999
   
   # Google Calendar
   GOOGLE_CALENDAR_ID=primary_or_calendar_id
   GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
   CALENDAR_ALLOW_ATTENDEES=0
   
   # IA (Gemini)
   GEMINI_API_KEY=your_gemini_api_key
   GEMINI_MODEL=gemini-1.5-flash
   GEMINI_MODEL_QUALITY=gemini-1.5-pro
   ```

## ✅ Comandos Admin

Após deploy, teste os comandos admin pelo WhatsApp:

- `#pause` - Pausa o bot indefinidamente
- `#pause 30` - Pausa por 30 minutos
- `#resume` - Retoma o bot
- `#status` - Verifica status atual

## 🧪 Teste de Funcionalidades

1. **Saudação personalizada**: Cliente existente deve ser reconhecido
2. **Agendamento completo**: Nome → Período → Data → Horário → Confirmação
3. **Consulta de agendamentos**: "Qual minha consulta?" deve mostrar agendamentos
4. **Respostas jurídicas**: Devem terminar oferecendo consulta no JM ADVOGADOS
5. **Persistência**: Dados devem permanecer após restart/redeploy

## 📊 Logs para Debug

Para monitorar o funcionamento:
```bash
# Ver logs em tempo real
docker logs -f <container_name>

# Filtrar logs específicos
docker logs <container_name> | grep "AI Decision"
docker logs <container_name> | grep "ERROR"
```

## 🔧 Troubleshooting

### Problema: Dados perdidos após deploy
**Solução**: Verificar se volume persistente está configurado corretamente

### Problema: Comandos admin não funcionam  
**Solução**: Verificar se ADMIN_WHATSAPP está configurado com número correto

### Problema: Bot em loop
**Solução**: Verificar logs para "AI Decision" e classificação incorreta

### Problema: IA muito informal
**Solução**: Verificar se GEMINI_API_KEY está configurada e funcionando
