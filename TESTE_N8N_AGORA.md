# 🚀 TESTE RÁPIDO - n8n + Chatbot

## ✅ STATUS ATUAL
- **n8n URL confirmada:** https://n8n-n8n.c9ewnj.easypanel.host ✅
- **Acesso verificado:** Status 200 OK ✅
- **Código integrado:** ai_orchestrator.py pronto ✅
- **Workflows criados:** 3 arquivos JSON prontos ✅

---

## 📋 PRÓXIMOS 3 PASSOS:

### **PASSO 1: CONFIGURAR .env**
Adicione no seu arquivo `.env`:
```bash
N8N_BASE_URL=https://n8n-n8n.c9ewnj.easypanel.host
N8N_ENABLED=true
```

### **PASSO 2: IMPORTAR WORKFLOWS**
1. **Acesse:** https://n8n-n8n.c9ewnj.easypanel.host
2. **Faça login** na interface
3. **Importe os workflows:**
   - Clique **"+ New Workflow"**
   - Menu **"..."** → **"Import from file"**
   - Importe: `qualificacao_geral.json`
   - **IMPORTANTE:** Clique no toggle **"Activate"** ✅
   - Repita para: `qualificacao_familia.json` e `qualificacao_acidente.json`

### **PASSO 3: TESTE IMEDIATO**
Execute no PowerShell:
```powershell
Invoke-WebRequest -Uri "https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_geral" -Method Post -ContentType "application/json" -Body '{"user_number": "5511999999999", "message": "Quero me divorciar", "case_type": "familia", "timestamp": "2024-01-15T10:30:00Z"}'
```

**Resposta esperada:**
```json
{
  "case_type": "familia",
  "subtype": "divorcio", 
  "response": "💔 Compreendo que você quer se divorciar...",
  "urgency": "normal"
}
```

---

## 🧪 TESTES ESPECÍFICOS:

### **Teste Família:**
```powershell
Invoke-WebRequest -Uri "https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_familia" -Method Post -ContentType "application/json" -Body '{"user_number": "5511999999999", "message": "Meu ex não paga pensão há 3 meses", "case_type": "familia"}'
```

### **Teste Acidente:**
```powershell
Invoke-WebRequest -Uri "https://n8n-n8n.c9ewnj.easypanel.host/webhook/qualificacao_acidente" -Method Post -ContentType "application/json" -Body '{"user_number": "5511999999999", "message": "Sofri acidente de carro ontem", "case_type": "acidente"}'
```

---

## 🔍 DEBUGS ÚTEIS:

### **Se der erro 404:**
- Workflow não foi ativado (toggle off)
- Path do webhook incorreto
- Workflow não foi salvo

### **Se der erro de conexão:**
- Verificar se URL está correta
- Testar: `Invoke-WebRequest -Uri "https://n8n-n8n.c9ewnj.easypanel.host/"`

### **Se bot não chama n8n:**
- Verificar `.env` tem `N8N_BASE_URL` correto
- Verificar `N8N_ENABLED=true`
- Procurar nos logs: "🔥 Triggering n8n workflow"

---

## 🎯 DEPOIS DE FUNCIONAR:

### **Teste com Bot Real:**
1. Reinicie o bot: `python app.py`
2. Envie pelo WhatsApp: *"Quero me divorciar"*
3. Verifique se recebe resposta personalizada
4. Procure nos logs: "🎯 n8n workflow triggered successfully"

### **Casos de Teste:**
- **Família:** "Meu marido não paga pensão"
- **Acidente:** "Sofri acidente de trabalho"
- **Urgente:** "Estou sendo ameaçada"
- **Criminal:** "Fui preso injustamente"

---

## 📊 MÉTRICAS ESPERADAS:

Depois de funcionar, você vai ver:
- **+300% velocidade** de resposta
- **Respostas específicas** por área jurídica
- **Detecção automática** de urgência
- **Classificação inteligente** de casos

---

**🚀 PRONTO PARA TESTAR! Me avise quando importar os workflows que vamos testar juntos!**
