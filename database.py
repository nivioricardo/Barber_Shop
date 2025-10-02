import sqlite3
import json
from datetime import datetime, date
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_path='barbershop.db'):
        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        """Cria e retorna uma conexão com o banco"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Permite acessar colunas por nome
        return conn

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

            # Índices para melhor performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agendamentos_data_horario ON agendamentos(data, horario)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agendamentos_telefone ON agendamentos(telefone)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agendamentos_status ON agendamentos(status)')
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_agendamentos_numero_confirmacao ON agendamentos(numero_confirmacao)')

            # Tabela de configurações
            conn.execute('''
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL,
                    descricao TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Inserir configurações padrão
            configs = [
                ('dias_funcionamento', '[1,2,3,4,5,6]', 'Dias da semana que funciona (0=Domingo, 1=Segunda...)'),
                ('horario_abertura', '09:00', 'Horário de abertura'),
                ('horario_fechamento', '19:00', 'Horário de fechamento'),
                ('intervalo_almoco_inicio', '12:00', 'Início do intervalo de almoço'),
                ('intervalo_almoco_fim', '13:00', 'Fim do intervalo de almoço'),
                ('duracao_padrao', '30', 'Duração padrão dos serviços em minutos'),
                ('feriados',
                 '["2024-01-01", "2024-04-21", "2024-05-01", "2024-09-07", "2024-10-12", "2024-11-02", "2024-11-15", "2024-12-25"]',
                 'Lista de feriados')
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

            # Inserir serviços padrão
            servicos = [
                ('corte', 'Corte Social', 'Corte tradicional masculino', 30, 45.00),
                ('kids', 'Corte Kids', 'Corte especial para crianças', 25, 35.00),
                ('combo', 'Cabelo e Barba', 'Corte completo com acabamento na barba', 50, 70.00),
                ('degrade', 'Degradê Giletado', 'Técnica de degradê com gilete', 40, 60.00)
            ]

            conn.executemany('''
                INSERT OR IGNORE INTO servicos (codigo, nome, descricao, duracao, valor) 
                VALUES (?, ?, ?, ?, ?)
            ''', servicos)

    # Métodos para agendamentos
    def criar_agendamento(self, agendamento_data: Dict) -> Dict:
        """Cria um novo agendamento"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO agendamentos (
                    numero_confirmacao, nome, telefone, servico, codigo_servico,
                    data, horario, valor, duracao, observacoes, ip_cliente, user_agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                agendamento_data.get('observacoes', ''),
                agendamento_data.get('ip_cliente', ''),
                agendamento_data.get('user_agent', '')
            ))

            # Buscar o agendamento criado
            agendamento = conn.execute(
                'SELECT * FROM agendamentos WHERE id = ?',
                (cursor.lastrowid,)
            ).fetchone()

            return dict(agendamento) if agendamento else None

    def buscar_agendamentos_por_data(self, data: str) -> List[Dict]:
        """Busca agendamentos por data"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM agendamentos 
                WHERE data = ? AND status = 'confirmado'
                ORDER BY horario
            ''', (data,))

            return [dict(row) for row in cursor.fetchall()]

    def buscar_agendamentos_por_telefone(self, telefone: str) -> List[Dict]:
        """Busca agendamentos futuros por telefone"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM agendamentos 
                WHERE telefone = ? AND data >= date('now') AND status = 'confirmado'
                ORDER BY data, horario
            ''', (telefone,))

            return [dict(row) for row in cursor.fetchall()]

    def verificar_disponibilidade(self, data: str, horario: str) -> bool:
        """Verifica se um horário está disponível"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT COUNT(*) as count FROM agendamentos 
                WHERE data = ? AND horario = ? AND status = 'confirmado'
            ''', (data, horario))

            result = cursor.fetchone()
            return result['count'] == 0

    def cancelar_agendamento(self, agendamento_id: int, motivo: str = "") -> bool:
        """Cancela um agendamento"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                UPDATE agendamentos 
                SET status = 'cancelado', 
                    cancelado_em = CURRENT_TIMESTAMP,
                    motivo_cancelamento = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'confirmado'
            ''', (motivo, agendamento_id))

            return cursor.rowcount > 0

    # Métodos para configurações
    def obter_configuracao(self, chave: str) -> any:
        """Obtém uma configuração do sistema"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT valor FROM configuracoes WHERE chave = ?',
                (chave,)
            )
            result = cursor.fetchone()
            return json.loads(result['valor']) if result else None

    def atualizar_configuracao(self, chave: str, valor: any):
        """Atualiza uma configuração do sistema"""
        with self.get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO configuracoes (chave, valor, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (chave, json.dumps(valor)))

    # Métodos para serviços
    def obter_servicos(self) -> List[Dict]:
        """Obtém todos os serviços ativos"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM servicos WHERE ativo = 1 ORDER BY valor'
            )
            return [dict(row) for row in cursor.fetchall()]

    def obter_servico(self, codigo: str) -> Optional[Dict]:
        """Obtém um serviço específico"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM servicos WHERE codigo = ? AND ativo = 1',
                (codigo,)
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    # Estatísticas
    def obter_estatisticas(self, data_inicio: str = None, data_fim: str = None) -> Dict:
        """Obtém estatísticas dos agendamentos"""
        with self.get_connection() as conn:
            where_clause = ""
            params = []

            if data_inicio and data_fim:
                where_clause = "WHERE created_at BETWEEN ? AND ?"
                params = [data_inicio, data_fim]

            cursor = conn.execute(f'''
                SELECT 
                    COUNT(*) as total_agendamentos,
                    SUM(CASE WHEN status = 'confirmado' THEN 1 ELSE 0 END) as confirmados,
                    SUM(CASE WHEN status = 'cancelado' THEN 1 ELSE 0 END) as cancelados,
                    SUM(CASE WHEN status = 'concluido' THEN 1 ELSE 0 END) as concluidos,
                    SUM(valor) as faturamento_total,
                    AVG(valor) as ticket_medio
                FROM agendamentos
                {where_clause}
            ''', params)

            stats = dict(cursor.fetchone())

            # Calcular taxa de cancelamento
            if stats['total_agendamentos'] > 0:
                stats['taxa_cancelamento'] = round(
                    (stats['cancelados'] / stats['total_agendamentos']) * 100, 2
                )
            else:
                stats['taxa_cancelamento'] = 0

            return stats


# Instância global do banco de dados
db = Database()