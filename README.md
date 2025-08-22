# 🤖 JustIA Bot 2.0 - n8n Centralized

**Sistema revolucionário com toda a inteligência centralizada no n8n!**

## 🚀 **ARQUITETURA NOVA**

```
WhatsApp → app.py (150 linhas) → n8n Master Workflow → Resposta Inteligente
```

### **✅ O QUE FAZ:**
- 📱 **Recebe mensagens** via Evolution API
- 🚀 **Envia tudo para n8n** Master Workflow  
- 🤖 **n8n faz TODA a inteligência**
- 📤 **Retorna resposta** via WhatsApp

## 🧠 **INTELIGÊNCIA NO N8N:**

### **🤖 Master Workflow:**
- 🎯 Classificação inteligente (criminal, família, FIES, acidentes)
- 📅 Agendamento completo (Google Calendar integrado)
- 🔄 Gerenciamento de estados de conversa
- 💾 Banco de dados SQLite automático

### **⚖️ Workflows Especializados:**
- **Criminal:** Dr. JM especialista (flagrante, inquérito, recursos)
- **Família:** Divórcio, guarda, pensão, medidas protetivas  
- **FIES:** Desbloqueio, documentação, quitação
- **Acidentes:** Trânsito, trabalho, erro médico

## 📁 **ESTRUTURA LIMPA:**

```
ADV/
├── app.py                     # 🚀 App simplificado (150 linhas)
├── requirements.txt           # 📦 Apenas 4 dependências
├── .env                       # ⚙️ Variáveis de ambiente
├── README.md                  # 📚 Esta documentação
└── n8n_workflows/            # 🤖 Workflows n8n
    ├── master_conversation.json      # 🧠 Workflow principal
    ├── super_advanced_criminal.json  # ⚖️ Criminal especialista
    ├── qualificacao_familia.json     # 🏠 Família completo
    ├── qualificacao_fies.json        # 🎓 FIES especialista
    └── qualificacao_acidente.json    # 💥 Acidentes detalhado
```

## ⚙️ **CONFIGURAÇÃO:**

### **1. Variáveis de Ambiente (.env):**
```bash
# n8n
N8N_BASE_URL=https://n8n-n8n.c9ewnj.easypanel.host
N8N_ENABLED=true

# Evolution API
EVOLUTION_API_URL=https://api.evolution.com
EVOLUTION_API_KEY=sua_api_key
EVOLUTION_INSTANCE_NAME=JustIA_Bot

# APIs (configuradas no n8n)
GEMINI_API_KEY=sua_gemini_key
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

### **2. Instalar Dependências:**
```bash
pip install -r requirements.txt
```

### **3. Importar Workflows no n8n:**
1. Acesse: https://n8n-n8n.c9ewnj.easypanel.host
2. Importe todos os arquivos .json da pasta `n8n_workflows/`
3. **ATIVE** cada workflow (toggle verde)

### **4. Executar:**
```bash
python app.py
```

## 🎯 **BENEFÍCIOS:**

### **🧠 Inteligência 10x Maior:**
- **Análise completa** por caso (urgência, viabilidade, custos)
- **Estratégias jurídicas** automáticas
- **Credenciais Dr. JM** destacadas por especialidade
- **Detecção de urgência** com alertas automáticos

### **⚡ Automação Total:**
- **Agendamento end-to-end** (Google Calendar)
- **Qualificação especializada** por área
- **Alertas automáticos** para Dr. JM
- **Follow-up inteligente**

### **🔧 Manutenção Simples:**
- **Interface visual** (n8n drag & drop)
- **Apenas 150 linhas** Python
- **4 dependências** apenas
- **Updates visuais** nos workflows

## 📊 **EXEMPLO REAL:**

### **Cliente:** *"Fui preso em flagrante"*

### **Resposta Automática:**
```
🚨 PRISÃO EM FLAGRANTE - URGÊNCIA MÁXIMA

👨‍⚖️ SEU ADVOGADO:
• Dr. JM Miranda - Professor de Direito Penal
• Coordenador Curso de Direito FAM
• Especialista em Investigação Criminal

📊 ANÁLISE DO SEU CASO:
• Tipo: FLAGRANTE
• Urgência: 5/5 (MÁXIMA)
• Viabilidade: muito alta
• Chance sucesso: 90%
• Prazo ação: 24 horas

⚡ AÇÕES IMEDIATAS:
1. Contato imediato com delegacia
2. Habeas Corpus preventivo
3. Audiência de custódia
4. Pedido liberdade provisória

🎯 ESTRATÉGIA JURÍDICA:
• Questionar legalidade da prisão
• Verificar vícios no flagrante
• Medidas cautelares alternativas

💰 INVESTIMENTO: R$ 3.000 - R$ 8.000

🔴 URGENTE: Dr. JM precisa falar com você HOJE!
📞 Vou agendar contato IMEDIATO!
```

### **Automações Paralelas:**
- 📧 **Email automático** para Dr. JM: "FLAGRANTE URGENTE"
- 📱 **WhatsApp automático** para Dr. JM: "Cliente preso - ação hoje!"
- 💾 **Banco automático:** Caso salvo com análise completa
- 📅 **Agendamento prioritário** se necessário

## 🏆 **ESPECIALIDADES JM ADVOGADOS:**

- ⚖️ **Ação Penal** (Dr. JM Professor)
- 🚨 **Flagrantes** (Urgência máxima)
- 🔍 **Inquérito Policial** (Fase crucial)
- 📜 **Recursos** (Especialidade)
- 🏠 **Direito das Famílias**
- 🛡️ **Medida Protetiva**
- 💥 **Responsabilidade Civil**
- 🎓 **FIES** (Especialidade JM)

## 📞 **CONTATO:**

- **WhatsApp:** Integrado via Evolution API
- **Email:** Notificações automáticas
- **Agendamento:** Google Calendar integrado

---

**🚀 Sistema profissional completo com inteligência artificial especializada!**