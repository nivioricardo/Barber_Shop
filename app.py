from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import os
from functools import wraps
import logging
import sqlite3
from contextlib import contextmanager
import re
from werkzeug.middleware.proxy_fix import ProxyFix
import urllib.parse

# Configuração do Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'barbershop_secret_key_2024')

# Configuração CORS para produção
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "https://barber-shop.onrender.com",
            "https://*.onrender.com"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type"]
    }
})

# Configuração de logging para produção
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAÇÕES DO WHATSAPP - ATUALIZADA
# =============================================================================

WHATSAPP_CONFIG = {
    'enabled': True,
    'api_url': 'https://api.whatsapp.com/send',
    'phone_number': '5516997034690',  # Seu número
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

            # Serviços padrão atualizados
            servicos = [
                ('corte', 'Corte Social', 'Corte tradicional masculino', 30, 30.00),
                ('barba', 'Aparar Barba', 'Aparar e modelar barba', 20, 15.00),
                ('cabelo-barba', 'Cabelo + Barba', 'Corte completo com barba', 50, 40.00),
                ('sobrancelha', 'Sobrancelha', 'Design de sobrancelha', 15, 10.00),
                ('pezinho', 'Pezinho', 'Acabamento no pezinho', 15, 10.00),
                ('corte-kids', 'Corte Infantil', 'Corte especial para crianças', 25, 25.00)
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

    def verificar_disponibilidade(self, data, horario, duracao):
        """Verifica disponibilidade de horário considerando a duração do serviço"""
        with self.get_connection() as conn:
            # Busca agendamentos no mesmo dia
            agendamentos = conn.execute('''
                SELECT horario, duracao FROM agendamentos 
                WHERE data = ? AND status = 'confirmado'
            ''', (data,)).fetchall()

            horario_solicitado = datetime.strptime(horario, '%H:%M')
            fim_solicitado = horario_solicitado + timedelta(minutes=duracao)

            for ag in agendamentos:
                horario_ag = datetime.strptime(ag['horario'], '%H:%M')
                fim_ag = horario_ag + timedelta(minutes=ag['duracao'])

                # Verifica sobreposição de horários
                if (horario_solicitado < fim_ag and fim_solicitado > horario_ag):
                    return False

            return True

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

    def cancelar_agendamento(self, numero_confirmacao, motivo="Cancelado pelo cliente"):
        """Cancela um agendamento"""
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE agendamentos 
                SET status = 'cancelado', 
                    cancelado_em = CURRENT_TIMESTAMP,
                    motivo_cancelamento = ?
                WHERE numero_confirmacao = ? AND status = 'confirmado'
            ''', (motivo, numero_confirmacao))

            return conn.total_changes > 0

    def buscar_agendamento_por_codigo(self, numero_confirmacao):
        """Busca um agendamento pelo código de confirmação"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM agendamentos WHERE numero_confirmacao = ?',
                (numero_confirmacao,)
            )
            result = cursor.fetchone()
            return dict(result) if result else None


# Instância do banco
db = Database()


# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def rate_limit(max_requests=10, window=900):
    """Decorator para rate limiting - aumentado para 10 requisições"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            now = datetime.now()
            window_start = now - timedelta(seconds=window)
            window_start_ts = window_start.timestamp()

            if 'requests' not in session:
                session['requests'] = []

            session['requests'] = [req_time for req_time in session['requests']
                                   if req_time > window_start_ts]

            if len(session['requests']) >= max_requests:
                return jsonify({
                    'success': False,
                    'message': 'Muitas requisições. Tente novamente em 15 minutos.'
                }), 429

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


def gerar_horarios_disponiveis(data_str, servico_codigo=None):
    """Gera horários disponíveis para uma data considerando a duração do serviço"""
    try:
        if not validar_data(data_str):
            return []

        dias_funcionamento = db.obter_configuracao('dias_funcionamento') or [1, 2, 3, 4, 5, 6]
        data = datetime.strptime(data_str, '%Y-%m-%d').date()

        if data.weekday() not in dias_funcionamento:
            return []

        # Obter duração do serviço se especificado
        duracao_servico = int(db.obter_configuracao('duracao_padrao') or 30)
        if servico_codigo:
            servico = db.obter_servico(servico_codigo)
            if servico:
                duracao_servico = servico['duracao']

        agendamentos = db.buscar_agendamentos_por_data(data_str)

        horario_abertura = db.obter_configuracao('horario_abertura') or '09:00'
        horario_fechamento = db.obter_configuracao('horario_fechamento') or '19:00'
        intervalo_inicio = db.obter_configuracao('intervalo_almoco_inicio') or '12:00'
        intervalo_fim = db.obter_configuracao('intervalo_almoco_fim') or '13:00'

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
            fim_servico = hora_atual + timedelta(minutes=duracao_servico)

            # Verificar se está dentro do horário de almoço
            if (hora_atual >= intervalo_inicio_dt and hora_atual < intervalo_fim_dt) or \
                    (fim_servico > intervalo_inicio_dt and fim_servico <= intervalo_fim_dt):
                hora_atual += timedelta(minutes=30)
                continue

            # Verificar se ultrapassa o horário de fechamento
            if fim_servico > hora_fechamento_dt:
                hora_atual += timedelta(minutes=30)
                continue

            # Verificar disponibilidade considerando a duração
            disponivel = True
            for agendamento in agendamentos:
                ag_horario = datetime.strptime(agendamento['horario'], '%H:%M')
                ag_fim = ag_horario + timedelta(minutes=agendamento['duracao'])

                # Verificar sobreposição
                if (hora_atual < ag_fim and fim_servico > ag_horario):
                    disponivel = False
                    break

            if disponivel:
                horarios.append(horario_str)

            hora_atual += timedelta(minutes=30)

        return horarios

    except Exception as e:
        logger.error(f"Erro ao gerar horários: {e}")
        return []


def enviar_whatsapp(agendamento):
    """Envia notificação via WhatsApp - VERSÃO ATUALIZADA"""
    if not WHATSAPP_CONFIG['enabled']:
        logger.info("WhatsApp desativado nas configurações")
        return None

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

        # Usando urllib.parse.quote que é mais confiável no Render
        mensagem_codificada = urllib.parse.quote(mensagem, safe='')

        whatsapp_url = f"{WHATSAPP_CONFIG['api_url']}?phone={WHATSAPP_CONFIG['phone_number']}&text={mensagem_codificada}"

        logger.info(f"📱 Link WhatsApp gerado com sucesso")
        logger.info(f"🔗 URL: {whatsapp_url[:100]}...")  # Log parcial para debug

        return whatsapp_url

    except Exception as e:
        logger.error(f"❌ Erro ao gerar link WhatsApp: {e}")
        return None


# =============================================================================
# ROTAS PRINCIPAIS
# =============================================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


@app.route('/horarios')
def obter_horarios():
    data = request.args.get('data')
    servico = request.args.get('servico')

    if not data:
        return jsonify({'error': 'Data é obrigatória'}), 400

    try:
        datetime.strptime(data, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Data inválida. Use YYYY-MM-DD'}), 400

    horarios = gerar_horarios_disponiveis(data, servico)
    return jsonify(horarios)


@app.route('/agendar', methods=['POST'])
@rate_limit(max_requests=10, window=900)
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

        logger.info(f"📝 Novo agendamento solicitado: {dados.get('nome')}")

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

        # Verificar disponibilidade considerando a duração do serviço
        if not db.verificar_disponibilidade(dados['data'], dados['horario'], servico_info['duracao']):
            return jsonify({
                'success': False,
                'message': 'Horário indisponível'
            }), 409

        # REMOVIDO: Limite de 3 agendamentos por telefone para facilitar testes

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
            logger.info(f"✅ Agendamento criado com sucesso: {numero_confirmacao}")

            # Gerar link do WhatsApp
            whatsapp_link = enviar_whatsapp(novo_agendamento)

            if not whatsapp_link:
                logger.warning("⚠️  Link WhatsApp não foi gerado, mas agendamento foi salvo")

            response_data = {
                'success': True,
                'message': 'Agendamento confirmado com sucesso!',
                'numero_confirmacao': numero_confirmacao,
                'whatsapp_link': whatsapp_link,
                'agendamento': {
                    'nome': novo_agendamento['nome'],
                    'servico': novo_agendamento['servico'],
                    'data': novo_agendamento['data'],
                    'horario': novo_agendamento['horario'],
                    'valor': novo_agendamento['valor']
                }
            }

            return jsonify(response_data), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Erro ao salvar agendamento'
            }), 500

    except Exception as e:
        logger.error(f"❌ Erro no agendamento: {e}")
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


@app.route('/consultar/<numero_confirmacao>')
def consultar_agendamento(numero_confirmacao):
    """Consulta um agendamento pelo número de confirmação"""
    try:
        agendamento = db.buscar_agendamento_por_codigo(numero_confirmacao)

        if not agendamento:
            return jsonify({
                'success': False,
                'message': 'Agendamento não encontrado'
            }), 404

        return jsonify({
            'success': True,
            'agendamento': agendamento
        })

    except Exception as e:
        logger.error(f"Erro ao consultar agendamento: {e}")
        return jsonify({
            'success': False,
            'message': 'Erro interno do servidor'
        }), 500


@app.route('/cancelar/<numero_confirmacao>', methods=['POST'])
def cancelar_agendamento(numero_confirmacao):
    """Cancela um agendamento"""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': 'Content-Type deve ser application/json'
            }), 400

        dados = request.get_json() or {}
        motivo = dados.get('motivo', 'Cancelado pelo cliente')

        sucesso = db.cancelar_agendamento(numero_confirmacao, motivo)

        if sucesso:
            logger.info(f"Agendamento cancelado: {numero_confirmacao}")
            return jsonify({
                'success': True,
                'message': 'Agendamento cancelado com sucesso'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Agendamento não encontrado ou já cancelado'
            }), 404

    except Exception as e:
        logger.error(f"Erro ao cancelar agendamento: {e}")
        return jsonify({
            'success': False,
            'message': 'Erro interno do servidor'
        }), 500


@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'environment': 'production'
    })


@app.route('/debug')
def debug():
    """Rota para debug"""
    amanha = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    horarios_amanha = gerar_horarios_disponiveis(amanha)

    return jsonify({
        'data_teste': amanha,
        'horarios_gerados': horarios_amanha,
        'environment': 'production',
        'timestamp': datetime.now().isoformat()
    })


# Nova rota para testar WhatsApp
@app.route('/test-whatsapp')
def test_whatsapp():
    """Rota para testar a geração do link do WhatsApp"""
    try:
        agendamento_teste = {
            'nome': 'Cliente Teste',
            'telefone': '(16) 99999-9999',
            'servico': 'Corte Social',
            'data': '2024-12-25',
            'horario': '10:00',
            'valor': 30.00,
            'duracao': 30,
            'numero_confirmacao': 'BSTEST123'
        }

        whatsapp_link = enviar_whatsapp(agendamento_teste)

        if whatsapp_link:
            return jsonify({
                'success': True,
                'message': 'Link WhatsApp gerado com sucesso',
                'whatsapp_link': whatsapp_link
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Falha ao gerar link WhatsApp'
            }), 500

    except Exception as e:
        logger.error(f"Erro no teste WhatsApp: {e}")
        return jsonify({
            'success': False,
            'message': f'Erro: {str(e)}'
        }), 500


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint não encontrado'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erro 500: {error}")
    return jsonify({'error': 'Erro interno do servidor'}), 500


# =============================================================================
# CONFIGURAÇÃO PARA PRODUÇÃO
# =============================================================================

class ProductionConfig:
    DEBUG = False
    TESTING = False


# Aplicar configurações de produção
app.config.from_object(ProductionConfig)

# Handler específico para o Gunicorn
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

if __name__ == '__main__':
    print("=" * 60)
    print("🪒 Barber&Shop - Modo Desenvolvimento")
    print("=" * 60)
    print("✅ Para produção, use: gunicorn app:app")
    print("🌐 Servidor: http://localhost:5000")
    print("=" * 60)

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )