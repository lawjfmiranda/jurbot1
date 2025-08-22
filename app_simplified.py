"""
🚀 BOT SIMPLIFICADO - Tudo centralizado no n8n!

Este arquivo substitui todo o app.py complexo.
Agora o n8n faz TUDO: conversa, agendamento, qualificação, banco de dados!
"""

from flask import Flask, request, jsonify
import requests
import logging
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n-n8n.c9ewnj.easypanel.host")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE_NAME")

def send_whatsapp_message(number: str, message: str):
    """Enviar mensagem via Evolution API."""
    try:
        url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
        
        payload = {
            "number": number,
            "text": message
        }
        
        headers = {
            "Content-Type": "application/json",
            "apikey": EVOLUTION_API_KEY
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Mensagem enviada para {number}")
            return True
        else:
            logger.error(f"❌ Erro ao enviar mensagem: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Erro no WhatsApp: {e}")
        return False

@app.route('/webhook/evolution', methods=['POST'])
def webhook_evolution():
    """
    🎯 WEBHOOK ULTRA-SIMPLIFICADO
    
    Apenas recebe a mensagem e manda para o n8n.
    O n8n faz TODO o resto!
    """
    try:
        data = request.json
        logger.info(f"📨 Webhook recebido: {data}")
        
        # Extrair dados da mensagem
        if not data or 'data' not in data:
            return jsonify({"status": "ignored", "reason": "no_data"}), 200
            
        message_data = data['data']
        
        # Verificar se é mensagem de texto
        if message_data.get('messageType') != 'textMessage':
            return jsonify({"status": "ignored", "reason": "not_text"}), 200
        
        # Extrair informações
        user_number = message_data.get('key', {}).get('remoteJid', '').replace('@s.whatsapp.net', '')
        message_text = message_data.get('message', {}).get('conversation', '')
        
        if not user_number or not message_text:
            return jsonify({"status": "ignored", "reason": "missing_data"}), 200
        
        logger.info(f"📱 Processando: {user_number} -> {message_text[:50]}...")
        
        # 🚀 ENVIAR TUDO PARA O N8N MASTER!
        n8n_response = send_to_n8n_master(user_number, message_text)
        
        if n8n_response and 'reply' in n8n_response:
            # Enviar resposta via WhatsApp
            success = send_whatsapp_message(user_number, n8n_response['reply'])
            
            return jsonify({
                "status": "processed",
                "n8n_response": n8n_response,
                "whatsapp_sent": success
            }), 200
        else:
            logger.error("❌ n8n não retornou resposta válida")
            return jsonify({"status": "error", "reason": "n8n_failed"}), 500
            
    except Exception as e:
        logger.error(f"💥 Erro no webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def send_to_n8n_master(user_number: str, message: str, current_state: str = "FREE"):
    """
    🎯 ENVIAR PARA O N8N MASTER
    
    O n8n faz TUDO:
    - Classifica a mensagem
    - Gerencia estados
    - Faz agendamento
    - Salva no banco
    - Retorna resposta pronta
    """
    try:
        url = f"{N8N_BASE_URL}/webhook/master_bot"
        
        payload = {
            "user_number": user_number,
            "message": message,
            "current_state": current_state,
            "timestamp": "2024-01-15T10:30:00Z"
        }
        
        logger.info(f"🚀 Enviando para n8n master: {payload}")
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ n8n master respondeu: {result}")
            return result
        else:
            logger.error(f"❌ n8n master erro: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"💥 Erro ao chamar n8n master: {e}")
        return None

@app.route('/health', methods=['GET'])
def health_check():
    """Health check simplificado."""
    return jsonify({
        "status": "healthy",
        "version": "2.0-n8n-centralized",
        "n8n_url": N8N_BASE_URL,
        "features": [
            "n8n master workflow",
            "centralized conversation",
            "automatic scheduling",
            "case qualification",
            "database integration"
        ]
    }), 200

@app.route('/', methods=['GET'])
def home():
    """Página inicial."""
    return """
    <h1>🤖 JustIA Bot 2.0 - n8n Centralized</h1>
    <p><strong>Status:</strong> ✅ Ativo</p>
    <p><strong>Arquitetura:</strong> n8n Master Workflow</p>
    <p><strong>Funcionalidades:</strong></p>
    <ul>
        <li>🧠 Inteligência centralizada no n8n</li>
        <li>📅 Agendamento automático</li>
        <li>⚖️ Qualificação especializada</li>
        <li>💾 Banco de dados integrado</li>
        <li>📧 Notificações automáticas</li>
    </ul>
    <p><strong>n8n URL:</strong> <a href="{}">{}</a></p>
    """.format(N8N_BASE_URL, N8N_BASE_URL)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    logger.info(f"🚀 Iniciando JustIA Bot 2.0 - n8n Centralized")
    logger.info(f"🔗 n8n URL: {N8N_BASE_URL}")
    logger.info(f"🌐 Porta: {port}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
