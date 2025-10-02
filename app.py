from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import os
from functools import wraps
import logging
import sqlite3
from contextlib import contextmanager
import re

# Configuração do Flask
app = Flask(__name__)
app.secret_key = 'barbershop_secret_key_2024'

# Configuração CORS
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5000", "http://127.0.0.1:5000"],
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type"]
    }
})

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAÇÕES DO WHATSAPP
# =============================================================================

WHATSAPP_CONFIG = {
    'enabled': True,
    'api_url': 'https://api.whatsapp.com/send',
    'phone_number': '5516997034690',
    'message_template': '''🪒 *Novo Agendamento - Barber&Shop* 🪒

*Cliente:* {nome}
*Telefone:* {telefone}
*Serviço:* {servico}
*Data:* {data}
*Horário:* {horario}
*Valor:* R$ {valor}
*Duração:* {duracao}min

*Nº Confirmação:* {numero_confirmacao}

📍 Avenida São João, 777 - Centro, Ibaté/SP'''
}


# =============================================================================
# BANCO DE DADOS SQLite
# =============================================================================

class Database:
    def __init__(self, db_path='barbershop.db'):
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def get_connection(self):
        """Gerenciador de contexto para conexões com o banco"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_database(self):
        """Inicializa o banco de dados com as tabelas necessárias"""
        with self.get_connection() as conn:
            # Tabela de agendamentos
            conn.execute('''
                CREATE TABLE IF NOT EXISTS agendamentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_confirmacao TEXT UNIQUE NOT NULL,
                    nome TEXT NOT NULL,
                    telefone TEXT NOT NULL,
                    servico TEXT NOT NULL,
                    codigo_servico TEXT NOT NULL,
                    data DATE NOT NULL,
                    horario TEXT NOT NULL,
                    valor REAL NOT NULL,
                    duracao INTEGER NOT NULL,
                    status TEXT DEFAULT 'confirmado',
                    observacoes TEXT,
                    ip_cliente TEXT,
                    user_agent TEXT,
                    cancelado_em DATETIME,
                    motivo_cancelamento TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Índices para performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agendamentos_data_horario ON agendamentos(data, horario)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agendamentos_telefone ON agendamentos(telefone)')

            # Tabela de configurações
            conn.execute('''
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL,
                    descricao TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Configurações padrão
            configs = [
                ('dias_funcionamento', '[1,2,3,4,5,6]', 'Dias de funcionamento (0=Domingo)'),
                ('horario_abertura', '09:00', 'Horário de abertura'),
                ('horario_fechamento', '19:00', 'Horário de fechamento'),
                ('intervalo_almoco_inicio', '12:00', 'Início do almoço'),
                ('intervalo_almoco_fim', '13:00', 'Fim do almoço'),
                ('duracao_padrao', '30', 'Duração padrão em minutos'),
                ('feriados', '[]', 'Lista de feriados')
            ]

            conn.executemany('''
                INSERT OR IGNORE INTO configuracoes (chave, valor, descricao) 
                VALUES (?, ?, ?)
            ''', configs)

            # Tabela de serviços
            conn.execute('''
                CREATE TABLE IF NOT EXISTS servicos (
                    codigo TEXT PRIMARY KEY,
                    nome TEXT NOT NULL,
                    descricao TEXT,
                    duracao INTEGER NOT NULL,
                    valor REAL NOT NULL,
                    ativo BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Serviços padrão
            servicos = [
                ('corte', 'Corte Social', 'Corte tradicional masculino', 30, 45.00),
                ('kids', 'Corte Kids', 'Corte especial para crianças', 25, 35.00),
                ('combo', 'Cabelo e Barba', 'Corte completo com barba', 50, 70.00),
                ('degrade', 'Degradê Giletado', 'Técnica de degradê com gilete', 40, 60.00)
            ]

            conn.executemany('''
                INSERT OR IGNORE INTO servicos (codigo, nome, descricao, duracao, valor) 
                VALUES (?, ?, ?, ?, ?)
            ''', servicos)

    def criar_agendamento(self, agendamento_data):
        """Cria um novo agendamento"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO agendamentos (
                    numero_confirmacao, nome, telefone, servico, codigo_servico,
                    data, horario, valor, duracao, ip_cliente, user_agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                agendamento_data['numero_confirmacao'],
                agendamento_data['nome'],
                agendamento_data['telefone'],
                agendamento_data['servico'],
                agendamento_data['codigo_servico'],
                agendamento_data['data'],
                agendamento_data['horario'],
                agendamento_data['valor'],
                agendamento_data['duracao'],
                agendamento_data.get('ip_cliente', ''),
                agendamento_data.get('user_agent', '')
            ))

            agendamento = conn.execute(
                'SELECT * FROM agendamentos WHERE id = ?',
                (cursor.lastrowid,)
            ).fetchone()

            return dict(agendamento) if agendamento else None

    def buscar_agendamentos_por_data(self, data):
        """Busca agendamentos por data"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM agendamentos 
                WHERE data = ? AND status = 'confirmado'
                ORDER BY horario
            ''', (data,))
            return [dict(row) for row in cursor.fetchall()]

    def buscar_agendamentos_por_telefone(self, telefone):
        """Busca agendamentos por telefone"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM agendamentos 
                WHERE telefone = ? AND data >= date('now') AND status = 'confirmado'
                ORDER BY data, horario
            ''', (telefone,))
            return [dict(row) for row in cursor.fetchall()]

    def verificar_disponibilidade(self, data, horario):
        """Verifica disponibilidade de horário"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT COUNT(*) as count FROM agendamentos 
                WHERE data = ? AND horario = ? AND status = 'confirmado'
            ''', (data, horario))
            result = cursor.fetchone()
            return result['count'] == 0

    def obter_configuracao(self, chave):
        """Obtém configuração do sistema"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT valor FROM configuracoes WHERE chave = ?',
                (chave,)
            )
            result = cursor.fetchone()
            if result:
                try:
                    return json.loads(result['valor'])
                except:
                    return result['valor']
            return None

    def obter_servicos(self):
        """Obtém todos os serviços"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM servicos WHERE ativo = 1 ORDER BY valor'
            )
            return [dict(row) for row in cursor.fetchall()]

    def obter_servico(self, codigo):
        """Obtém um serviço específico"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM servicos WHERE codigo = ? AND ativo = 1',
                (codigo,)
            )
            result = cursor.fetchone()
            return dict(result) if result else None


# Instância do banco
db = Database()


# =============================================================================
# FUNÇÕES AUXILIARES CORRIGIDAS
# =============================================================================

def rate_limit(max_requests=5, window=900):
    """Decorator para rate limiting CORRIGIDO"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            now = datetime.now()
            window_start = now - timedelta(seconds=window)

            # ✅ CORREÇÃO: Converter para timestamp para comparação consistente
            window_start_ts = window_start.timestamp()

            if 'requests' not in session:
                session['requests'] = []

            # ✅ CORREÇÃO: Comparar timestamps (float) com timestamps (float)
            session['requests'] = [req_time for req_time in session['requests']
                                   if req_time > window_start_ts]

            if len(session['requests']) >= max_requests:
                return jsonify({
                    'success': False,
                    'message': 'Muitas requisições. Tente novamente em 15 minutos.'
                }), 429

            # ✅ CORREÇÃO: Adicionar timestamp (float)
            session['requests'].append(now.timestamp())
            session.modified = True

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def formatar_telefone(telefone):
    """Formata telefone para o padrão (XX) XXXXX-XXXX"""
    numeros = re.sub(r'\D', '', telefone)

    if numeros.startswith('55'):
        numeros = numeros[2:]

    if len(numeros) == 11:
        return f"({numeros[0:2]}) {numeros[2:7]}-{numeros[7:11]}"
    elif len(numeros) == 10:
        return f"({numeros[0:2]}) {numeros[2:6]}-{numeros[6:10]}"
    else:
        return None


def validar_telefone(telefone):
    """Valida e formata telefone"""
    telefone_formatado = formatar_telefone(telefone)
    if telefone_formatado:
        return telefone_formatado
    else:
        return None


def validar_data(data_str):
    """Valida se a data é válida e futura"""
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date()
        hoje = datetime.now().date()
        return data >= hoje
    except ValueError:
        return False


def gerar_numero_confirmacao():
    """Gera número de confirmação único"""
    from random import choices
    from string import ascii_uppercase, digits
    timestamp = datetime.now().strftime('%y%m%d%H%M%S')
    random_chars = ''.join(choices(ascii_uppercase + digits, k=3))
    return f'BS{timestamp}{random_chars}'


def gerar_horarios_disponiveis(data_str):
    """Gera horários disponíveis para uma data"""
    try:
        if not validar_data(data_str):
            return []

        dias_funcionamento = db.obter_configuracao('dias_funcionamento') or [1, 2, 3, 4, 5, 6]
        data = datetime.strptime(data_str, '%Y-%m-%d').date()

        if data.weekday() not in dias_funcionamento:
            return []

        agendamentos = db.buscar_agendamentos_por_data(data_str)
        horarios_ocupados = [ag['horario'] for ag in agendamentos]

        horario_abertura = db.obter_configuracao('horario_abertura') or '09:00'
        horario_fechamento = db.obter_configuracao('horario_fechamento') or '19:00'
        intervalo_inicio = db.obter_configuracao('intervalo_almoco_inicio') or '12:00'
        intervalo_fim = db.obter_configuracao('intervalo_almoco_fim') or '13:00'
        duracao_padrao = int(db.obter_configuracao('duracao_padrao') or 30)

        horarios = []
        base_date = datetime(2000, 1, 1)

        hora_atual = base_date.replace(
            hour=int(horario_abertura.split(':')[0]),
            minute=int(horario_abertura.split(':')[1])
        )

        hora_fechamento_dt = base_date.replace(
            hour=int(horario_fechamento.split(':')[0]),
            minute=int(horario_fechamento.split(':')[1])
        )

        intervalo_inicio_dt = base_date.replace(
            hour=int(intervalo_inicio.split(':')[0]),
            minute=int(intervalo_inicio.split(':')[1])
        )

        intervalo_fim_dt = base_date.replace(
            hour=int(intervalo_fim.split(':')[0]),
            minute=int(intervalo_fim.split(':')[1])
        )

        while hora_atual < hora_fechamento_dt:
            horario_str = hora_atual.strftime('%H:%M')

            if not (intervalo_inicio_dt <= hora_atual < intervalo_fim_dt):
                if horario_str not in horarios_ocupados:
                    horarios.append(horario_str)

            hora_atual += timedelta(minutes=duracao_padrao)

        return horarios

    except Exception as e:
        logger.error(f"Erro ao gerar horários: {e}")
        return []


def enviar_whatsapp(agendamento):
    """Envia notificação via WhatsApp"""
    if not WHATSAPP_CONFIG['enabled']:
        logger.info("WhatsApp desativado nas configurações")
        return True

    try:
        mensagem = WHATSAPP_CONFIG['message_template'].format(
            nome=agendamento['nome'],
            telefone=agendamento['telefone'],
            servico=agendamento['servico'],
            data=agendamento['data'],
            horario=agendamento['horario'],
            valor=agendamento['valor'],
            duracao=agendamento['duracao'],
            numero_confirmacao=agendamento['numero_confirmacao']
        )

        import requests
        mensagem_codificada = requests.utils.quote(mensagem)
        whatsapp_url = f"{WHATSAPP_CONFIG['api_url']}?phone={WHATSAPP_CONFIG['phone_number']}&text={mensagem_codificada}"

        logger.info(f"📱 Link WhatsApp gerado")
        return whatsapp_url

    except Exception as e:
        logger.error(f"Erro ao gerar link WhatsApp: {e}")
        return None


# =============================================================================
# ROTAS PRINCIPAIS
# =============================================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/horarios')
def obter_horarios():
    data = request.args.get('data')

    if not data:
        return jsonify({'error': 'Data é obrigatória'}), 400

    try:
        datetime.strptime(data, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Data inválida. Use YYYY-MM-DD'}), 400

    horarios = gerar_horarios_disponiveis(data)
    return jsonify(horarios)


@app.route('/agendar', methods=['POST'])
@rate_limit(max_requests=5, window=900)
def agendar():
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': 'Content-Type deve ser application/json'
            }), 400

        dados = request.get_json()

        if not dados:
            return jsonify({
                'success': False,
                'message': 'Dados não fornecidos'
            }), 400

        logger.info(f"Novo agendamento: {dados.get('nome')}")

        campos_obrigatorios = ['nome', 'telefone', 'servico', 'data', 'horario']
        campos_faltantes = [campo for campo in campos_obrigatorios if not dados.get(campo)]

        if campos_faltantes:
            return jsonify({
                'success': False,
                'message': f'Campos obrigatórios: {", ".join(campos_faltantes)}'
            }), 400

        if len(dados['nome']) < 2 or len(dados['nome']) > 100:
            return jsonify({
                'success': False,
                'message': 'Nome deve ter entre 2 e 100 caracteres'
            }), 400

        telefone_validado = validar_telefone(dados['telefone'])
        if not telefone_validado:
            return jsonify({
                'success': False,
                'message': 'Telefone inválido. Use (XX) XXXXX-XXXX'
            }), 400

        servico_info = db.obter_servico(dados['servico'])
        if not servico_info:
            return jsonify({
                'success': False,
                'message': 'Serviço inválido'
            }), 400

        if not validar_data(dados['data']):
            return jsonify({
                'success': False,
                'message': 'Data inválida ou passada'
            }), 400

        if not db.verificar_disponibilidade(dados['data'], dados['horario']):
            return jsonify({
                'success': False,
                'message': 'Horário indisponível'
            }), 409

        agendamentos_recentes = db.buscar_agendamentos_por_telefone(telefone_validado)
        if len(agendamentos_recentes) >= 3:
            return jsonify({
                'success': False,
                'message': 'Limite de 3 agendamentos por telefone'
            }), 429

        numero_confirmacao = gerar_numero_confirmacao()

        agendamento_data = {
            'numero_confirmacao': numero_confirmacao,
            'nome': dados['nome'].strip(),
            'telefone': telefone_validado,
            'servico': servico_info['nome'],
            'codigo_servico': dados['servico'],
            'data': dados['data'],
            'horario': dados['horario'],
            'valor': servico_info['valor'],
            'duracao': servico_info['duracao'],
            'ip_cliente': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', '')
        }

        novo_agendamento = db.criar_agendamento(agendamento_data)

        if novo_agendamento:
            logger.info(f"Agendamento criado: {numero_confirmacao}")

            whatsapp_link = enviar_whatsapp(novo_agendamento)

            response_data = {
                'success': True,
                'message': 'Agendamento confirmado com sucesso!',
                'numero_confirmacao': numero_confirmacao,
                'whatsapp_link': whatsapp_link,
                'agendamento': {
                    'nome': novo_agendamento['nome'],
                    'servico': novo_agendamento['servico'],
                    'data': novo_agendamento['data'],
                    'horario': novo_agendamento['horario']
                }
            }

            return jsonify(response_data), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Erro ao salvar agendamento'
            }), 500

    except Exception as e:
        logger.error(f"Erro no agendamento: {e}")
        return jsonify({
            'success': False,
            'message': 'Erro interno do servidor'
        }), 500


@app.route('/servicos')
def listar_servicos():
    servicos = db.obter_servicos()
    return jsonify({
        'success': True,
        'servicos': servicos
    })


@app.route('/config')
def config():
    configs = {
        'horarios_config': {
            'dias_funcionamento': db.obter_configuracao('dias_funcionamento'),
            'horario_abertura': db.obter_configuracao('horario_abertura'),
            'horario_fechamento': db.obter_configuracao('horario_fechamento'),
            'intervalo_almoco': {
                'inicio': db.obter_configuracao('intervalo_almoco_inicio'),
                'fim': db.obter_configuracao('intervalo_almoco_fim')
            },
            'duracao_padrao': db.obter_configuracao('duracao_padrao')
        },
        'servicos': db.obter_servicos(),
        'whatsapp_enabled': WHATSAPP_CONFIG['enabled']
    }
    return jsonify(configs)


@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/debug')
def debug():
    """Rota para debug"""
    amanha = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    horarios_amanha = gerar_horarios_disponiveis(amanha)

    return jsonify({
        'data_teste': amanha,
        'horarios_gerados': horarios_amanha,
        'configuracoes': {
            'dias_funcionamento': db.obter_configuracao('dias_funcionamento'),
            'horario_abertura': db.obter_configuracao('horario_abertura'),
            'horario_fechamento': db.obter_configuracao('horario_fechamento'),
            'intervalo_almoco': {
                'inicio': db.obter_configuracao('intervalo_almoco_inicio'),
                'fim': db.obter_configuracao('intervalo_almoco_fim')
            }
        }
    })


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint não encontrado'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erro 500: {error}")
    return jsonify({'error': 'Erro interno do servidor'}), 500


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)

    print("=" * 50)
    print("🪒 Barber&Shop - Sistema Corrigido!")
    print("=" * 50)
    print("✅ Rate Limiting Corrigido")
    print("✅ Sistema 100% Funcional")
    print("🌐 Servidor: http://localhost:5000")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=True)