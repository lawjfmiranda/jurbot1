# 🚀 Como Importar Workflows no n8n

## 📋 PASSO A PASSO PARA IMPORTAR

### 1. Acessar n8n
- Abra: `https://n8n-n8n.c9ewnj.easypanel.host/`
- Faça login na interface

### 2. Importar Workflow Principal
1. Clique em **"+ New Workflow"**
2. Clique no menu **"..."** no canto superior direito
3. Selecione **"Import from file"**
4. Faça upload do arquivo: `qualificacao_geral.json`
5. Clique em **"Save"** 
6. **IMPORTANTE:** Clique no toggle **"Activate"** (canto superior direito)

### 3. Repetir para Outros Workflows
Importe na seguinte ordem:
- ✅ `qualificacao_geral.json` (principal - casos gerais)
- ✅ `qualificacao_criminal.json` (⚖️ especialidade Dr. JM - flagrantes, inquéritos, processos, recursos)
- ✅ `qualificacao_familia.json` (🏠 direito das famílias - divórcio, guarda, pensão, medidas protetivas)  
- ✅ `qualificacao_acidente.json` (💥 responsabilidade civil - acidentes, indenizações)
- ✅ `qualificacao_fies.json` (🎓 especialidade JM - financiamento estudantil)

### 4. Verificar Webhooks Criados
Após importar, você deve ter estes endpoints:
- `https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_geral`
- `https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_criminal` ⚖️
- `https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_familia` 🏠
- `https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_acidente` 💥
- `https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_fies` 🎓

### 5. Configurar Variável de Ambiente
No seu `.env`, adicione:
```bash
N8N_BASE_URL=https://n8n-n8n.c9ewnj.easypanel.host
N8N_ENABLED=true
```

## 🧪 TESTE RÁPIDO

### Teste via CURL:
```bash
curl -X POST https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_geral \
  -H "Content-Type: application/json" \
  -d '{
    "user_number": "5511999999999",
    "message": "Sofri acidente de carro ontem",
    "case_type": "acidente",
    "timestamp": "2024-01-15T10:30:00Z"
  }'
```

### Resposta Esperada:
```json
{
  "user_number": "5511999999999",
  "case_type": "acidente", 
  "priority": "normal",
  "response": "🚗 Acidente de trânsito... [resposta completa]",
  "processed_at": "2024-01-15T10:30:05Z"
}
```

## 🔧 TROUBLESHOOTING

### ❌ Erro "Webhook not found"
- Verifique se o workflow está **ativado** (toggle verde)
- Confirme o path do webhook

### ❌ Erro de conexão
- Verifique se n8n está acessível no EasyPanel
- Confirme o domínio está correto
- Teste: `curl https://n8n-n8n.c9ewnj.easypanel.host/healthz`

### ❌ Bot não chama n8n
- Verifique a variável `N8N_BASE_URL` no `.env`
- Confirme que `N8N_ENABLED=true`
- Veja os logs: procure por "🔥 Triggering n8n workflow"

## 📊 LOGS E DEBUG

### Ver logs do n8n:
```bash
docker logs nome-container-n8n
```

### Ver logs do bot:
Procure por estas mensagens:
- `🔥 Triggering n8n workflow: qualificacao_familia`
- `✅ n8n workflow success: qualificacao_familia`
- `❌ n8n workflow failed: qualificacao_familia`

## 🎯 PRÓXIMOS PASSOS

Depois que funcionar:
1. **Criar workflows avançados** (trabalhista, criminal)
2. **Integrar com Google Calendar** para agendamento automático
3. **Conectar com CRM** para salvar leads
4. **Adicionar email automático** para follow-up
5. **Dashboard de métricas** em tempo real

## 🆘 PRECISA DE AJUDA?

Se algo não funcionar:
1. Verifique os logs do n8n
2. Teste os webhooks via CURL
3. Confirme as variáveis de ambiente
4. Reinicie o bot Python

---

**🚀 Depois que importar, me avise para testarmos juntos!**
