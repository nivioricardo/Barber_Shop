from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
import sqlite3
import os
import urllib.parse
import random
import string

app = Flask(__name__)

# Configuração do banco de dados
DATABASE = 'barbearia.db'


def init_db():
    """Inicializa o banco de dados"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Tabela de agendamentos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL,
            servico TEXT NOT NULL,
            data TEXT NOT NULL,
            horario TEXT NOT NULL,
            confirmado BOOLEAN DEFAULT FALSE,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela de horários disponíveis
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS horarios_disponiveis (
            data TEXT NOT NULL,
            horario TEXT NOT NULL,
            disponivel BOOLEAN DEFAULT TRUE,
            PRIMARY KEY (data, horario)
        )
    ''')

    conn.commit()
    conn.close()


def get_db_connection():
    """Cria conexão com o banco de dados"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def popular_horarios_disponiveis():
    """Popula a tabela de horários disponíveis"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Horários de funcionamento
    horarios_base = [
        '08:00', '08:30', '09:00', '09:30', '10:00', '10:30',
        '11:00', '11:30', '14:00', '14:30', '15:00', '15:30',
        '16:00', '16:30', '17:00', '17:30', '18:00', '18:30'
    ]

    # Popular horários para os próximos 30 dias
    hoje = datetime.now().date()
    for i in range(30):
        data = hoje + timedelta(days=i)
        data_str = data.isoformat()

        # Verificar se é domingo (fechado)
        if data.weekday() == 6:  # Domingo
            continue

        # Sábado tem horário reduzido
        horarios_do_dia = horarios_base.copy()
        if data.weekday() == 5:  # Sábado
            horarios_do_dia = [h for h in horarios_do_dia if int(h.split(':')[0]) <= 12]

        for horario in horarios_do_dia:
            cursor.execute('''
                INSERT OR IGNORE INTO horarios_disponiveis (data, horario, disponivel)
                VALUES (?, ?, ?)
            ''', (data_str, horario, True))

    conn.commit()
    conn.close()


def gerar_numero_confirmacao():
    """Gera um número de confirmação no formato BS + Data + Hora + Random"""
    agora = datetime.now()
    data_str = agora.strftime("%d%m%y")  # DDMMYY
    hora_str = agora.strftime("%H%M%S")  # HHMMSS
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"BS{data_str}{hora_str}{random_chars}"


def formatar_data_brasileira(data_str):
    """Formata data de YYYY-MM-DD para DD/MM/YYYY"""
    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d')
        return data_obj.strftime('%d/%m/%Y')
    except ValueError:
        return data_str


def obter_valor_servico(servico):
    """Retorna o valor do serviço"""
    valores = {
        'corte': 45.00,
        'kids': 35.00,
        'combo': 70.00,
        'degrade': 60.00
    }
    return valores.get(servico, 0.00)


def obter_duracao_servico(servico):
    """Retorna a duração do serviço"""
    duracoes = {
        'corte': '30min',
        'kids': '25min',
        'combo': '50min',
        'degrade': '40min'
    }
    return duracoes.get(servico, '')


def obter_nome_servico(servico):
    """Retorna o nome formatado do serviço"""
    servicos_nomes = {
        'corte': 'Corte Social',
        'kids': 'Corte Kids',
        'combo': 'Cabelo e Barba',
        'degrade': 'Degradê Giletado'
    }
    return servicos_nomes.get(servico, servico)


@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')


@app.route('/horarios')
def get_horarios():
    """Retorna horários disponíveis para uma data específica"""
    data = request.args.get('data')

    if not data:
        return jsonify({'error': 'Data não fornecida'}), 400

    try:
        # Validar formato da data
        datetime.strptime(data, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Formato de data inválido'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Buscar horários disponíveis para a data
    cursor.execute('''
        SELECT horario FROM horarios_disponiveis 
        WHERE data = ? AND disponivel = TRUE
        ORDER BY horario
    ''', (data,))

    horarios = [row['horario'] for row in cursor.fetchall()]
    conn.close()

    return jsonify(horarios)


@app.route('/agendar', methods=['POST'])
def agendar():
    """Processa um novo agendamento"""
    try:
        data = request.get_json()

        # Validar campos obrigatórios
        campos_obrigatorios = ['nome', 'telefone', 'servico', 'data', 'horario']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'success': False,
                    'message': f'Campo {campo} é obrigatório'
                }), 400

        nome = data['nome'].strip()
        telefone = data['telefone'].strip()
        servico = data['servico']
        data_agendamento = data['data']
        horario = data['horario']

        # Validar formato da data
        try:
            datetime.strptime(data_agendamento, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Formato de data inválido'
            }), 400

        # Validar se a data não é no passado
        hoje = datetime.now().date()
        data_obj = datetime.strptime(data_agendamento, '%Y-%m-%d').date()
        if data_obj < hoje:
            return jsonify({
                'success': False,
                'message': 'Não é possível agendar para datas passadas'
            }), 400

        # Validar se é domingo
        if data_obj.weekday() == 6:
            return jsonify({
                'success': False,
                'message': 'A barbearia não funciona aos domingos'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verificar se o horário ainda está disponível
        cursor.execute('''
            SELECT disponivel FROM horarios_disponiveis 
            WHERE data = ? AND horario = ?
        ''', (data_agendamento, horario))

        resultado = cursor.fetchone()
        if not resultado or not resultado['disponivel']:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Horário indisponível. Por favor, selecione outro horário.'
            }), 400

        # Gerar número de confirmação
        numero_confirmacao = gerar_numero_confirmacao()

        # Inserir agendamento
        cursor.execute('''
            INSERT INTO agendamentos (nome, telefone, servico, data, horario)
            VALUES (?, ?, ?, ?, ?)
        ''', (nome, telefone, servico, data_agendamento, horario))

        # Marcar horário como indisponível
        cursor.execute('''
            UPDATE horarios_disponiveis 
            SET disponivel = FALSE 
            WHERE data = ? AND horario = ?
        ''', (data_agendamento, horario))

        conn.commit()

        # Buscar o ID do agendamento criado
        agendamento_id = cursor.lastrowid
        conn.close()

        # Preparar dados para a mensagem
        nome_servico = obter_nome_servico(servico)
        valor_servico = obter_valor_servico(servico)
        duracao_servico = obter_duracao_servico(servico)
        data_formatada = formatar_data_brasileira(data_agendamento)

        # MENSAGEM PROFISSIONAL
        mensagem_profissional = f"""✂️ *GUELFI-Barber&Shop* ✂️

*CONFIRMAÇÃO DE AGENDAMENTO*

👤 *Cliente:* {nome}
📞 *Telefone:* {telefone}
✂️ *Serviço:* {nome_servico}
📅 *Data:* {data_formatada}
⏰ *Horário:* {horario}
💰 *Valor:* R$ {valor_servico:.2f}
⏱️ *Duração:* {duracao_servico}

🔢 *Nº de Confirmação:* {numero_confirmacao}

📍 *Endereço:*
Avenida São João, 777 - Centro, Ibaté/SP
Obrigado pela preferência! 💈"""

        # Mensagem simples para mobile (fallback)
        mensagem_simples = f"Agendamento GUELFI-Barber: {nome} - {nome_servico} - {data_formatada} - {horario} - Código: {numero_confirmacao}"

        # Codificação para WhatsApp
        mensagem_codificada = urllib.parse.quote(mensagem_profissional)
        mensagem_simples_codificada = urllib.parse.quote(mensagem_simples)

        # Links otimizados para WhatsApp
        whatsapp_links = {
            # Para mobile - mensagem profissional
            'mobile_profissional': f"https://wa.me/5516997455195?text={mensagem_codificada}",
            # Para mobile - mensagem simples (fallback)
            'mobile_simples': f"https://wa.me/5516997455195?text={mensagem_simples_codificada}",
            # Fallback para desktop
            'desktop': f"https://web.whatsapp.com/send?phone=5516997455195&text={mensagem_codificada}"
        }

        return jsonify({
            'success': True,
            'numero_confirmacao': numero_confirmacao,
            'whatsapp_links': whatsapp_links,
            'mensagem_direct': mensagem_profissional,
            'mensagem_simples': mensagem_simples,
            'telefone_whatsapp': '5516997455195',
            'agendamento_id': agendamento_id,
            'detalhes_agendamento': {
                'nome': nome,
                'telefone': telefone,
                'servico': nome_servico,
                'data': data_formatada,
                'horario': horario,
                'valor': valor_servico,
                'duracao': duracao_servico
            },
            'message': 'Agendamento realizado com sucesso!'
        })

    except Exception as e:
        print(f"Erro no agendamento: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Erro interno do servidor. Tente novamente.'
        }), 500


@app.route('/agendamentos')
def listar_agendamentos():
    """Lista todos os agendamentos (para administração)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM agendamentos 
        ORDER BY data, horario
    ''')

    agendamentos = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(agendamentos)


@app.route('/health')
def health_check():
    """Endpoint para verificar se a API está funcionando"""
    return jsonify({'status': 'OK', 'timestamp': datetime.now().isoformat()})


# Inicializar o banco de dados quando a aplicação iniciar
with app.app_context():
    init_db()
    popular_horarios_disponiveis()

if __name__ == '__main__':
    # Criar pasta de templates se não existir
    if not os.path.exists('templates'):
        os.makedirs('templates')

    # HTML simplificado e correto (mantendo o mesmo HTML anterior)
    html_content = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Barber&Shop — Agenda Online</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { 
      font-family: Arial, sans-serif; 
      background: #f5f5f5; 
      color: #333; 
      line-height: 1.6;
      font-size: 16px;
      transition: font-size 0.3s ease;
    }
    .container { max-width: 900px; margin: 2rem auto; padding: 1rem; background: #fff; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }
    header { 
      background: #111; 
      color: #fff; 
      padding: 1rem; 
      text-align: center; 
      position: relative;
    }
    header h1 { margin: 0; color: #d4af37; }
    nav a { color: #fff; margin: 0 0.5rem; text-decoration: none; }
    .card { padding: 1rem; border: 1px solid #ddd; border-radius: 6px; margin: 0.5rem 0; }
    form { margin-top: 2rem; }
    .form-group { margin-bottom: 1rem; }
    label { display: block; margin-bottom: 0.3rem; font-weight: bold; }
    .required { color: #e74c3c; }
    input, select, button { padding: 0.6rem; border: 1px solid #ccc; border-radius: 4px; width: 100%; font-size: 1rem; }
    button { background: #111; color: #fff; cursor: pointer; }
    button:disabled { background: #777; }
    .field-error { color: #e74c3c; font-size: 0.8rem; }
    .msg { padding: 0.8rem; border-radius: 4px; margin-top: 1rem; display: none; }
    .msg.sucesso { background: #d4edda; color: #155724; }
    .msg.erro { background: #f8d7da; color: #721c24; }
    .whatsapp-btn { background: #25D366; color: white; border: none; padding: 0.8rem; border-radius: 6px; cursor: pointer; margin: 0.5rem 0; width: 100%; }
    .copy-btn { background: #28a745; color: white; border: none; padding: 0.5rem; border-radius: 4px; cursor: pointer; margin: 0.5rem 0; width: 100%; }

    /* Controles de Acessibilidade */
    .accessibility-controls {
      position: absolute;
      top: 10px;
      right: 10px;
      display: flex;
      gap: 5px;
    }
    .zoom-btn {
      background: #d4af37;
      color: #111;
      border: none;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      font-size: 18px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background-color 0.3s;
    }
    .zoom-btn:hover {
      background: #f0c850;
    }
    .zoom-btn:focus {
      outline: 2px solid white;
      outline-offset: 2px;
    }
    .reset-btn {
      background: #555;
      color: white;
      border: none;
      border-radius: 4px;
      padding: 5px 10px;
      font-size: 12px;
      cursor: pointer;
    }

    @media (max-width: 768px) { 
      .container { margin: 1rem; padding: 1rem; } 
      .accessibility-controls {
        position: static;
        justify-content: center;
        margin-top: 10px;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>GUELFI-Barber&Shop</h1>
    <nav>
      <a href="#servicos">Serviços</a>
      <a href="#agendar">Agendar</a>
      <a href="#contato">Contato</a>
    </nav>
    <!-- Controles de Acessibilidade -->
    <div class="accessibility-controls" aria-label="Controles de acessibilidade">
      <button class="zoom-btn" id="zoom-out" aria-label="Diminuir tamanho da fonte">A-</button>
      <button class="reset-btn" id="reset-font" aria-label="Restaurar tamanho padrão da fonte">Padrão</button>
      <button class="zoom-btn" id="zoom-in" aria-label="Aumentar tamanho da fonte">A+</button>
    </div>
  </header>
  <main class="container">
    <section id="servicos">
      <h2>Nossos Serviços</h2>
      <div class="card">
        <h3>Corte Social</h3>
        <p>R$ 45,00 — Duração: 30min</p>
      </div>
      <div class="card">
        <h3>Corte Kids</h3>
        <p>R$ 35,00 — Duração: 25min</p>
      </div>
      <div class="card">
        <h3>Cabelo e Barba</h3>
        <p>R$ 70,00 — Duração: 50min</p>
      </div>
      <div class="card">
        <h3>Degradê Giletado</h3>
        <p>R$ 60,00 — Duração: 40min</p>
      </div>
    </section>

    <section id="agendar">
      <h2>Agendar Horário</h2>
      <form id="bookingForm">
        <div class="form-group">
          <label for="nome" class="required">Nome</label>
          <input type="text" id="nome" name="nome" required>
          <span class="field-error" id="nome-error"></span>
        </div>
        <div class="form-group">
          <label for="telefone" class="required">Telefone</label>
          <input type="tel" id="telefone" name="telefone" placeholder="(16) 99999-9999" required>
          <span class="field-error" id="telefone-error"></span>
        </div>
        <div class="form-group">
          <label for="servico" class="required">Serviço</label>
          <select id="servico" name="servico" required>
            <option value="">Selecione...</option>
            <option value="corte">Corte Social</option>
            <option value="kids">Corte Kids</option>
            <option value="combo">Cabelo e Barba</option>
            <option value="degrade">Degradê Giletado</option>
          </select>
          <span class="field-error" id="servico-error"></span>
        </div>
        <div class="form-group">
          <label for="data" class="required">Data</label>
          <input type="date" id="data" name="data" required>
          <span class="field-error" id="data-error"></span>
        </div>
        <div class="form-group">
          <label for="hora" class="required">Horário</label>
          <select id="hora" name="hora" required>
            <option value="">Selecione a data primeiro</option>
          </select>
          <span class="field-error" id="hora-error"></span>
        </div>
        <button type="submit" id="submit-btn">Confirmar Agendamento</button>
      </form>
      <div id="msg" class="msg"></div>
    </section>

    <section id="contato">
      <h2>Contato</h2>
      <p>📍 Avenida São João, 777 - Centro, Ibaté/SP</p>
      <p>📞 (16) 99745-5195</p>
      <p>📧 fernandoguelfi.silva@gmail.com</p>
    </section>
  </main>

  <script>
    // Controles de Acessibilidade - Zoom de Fonte
    function inicializarControlesAcessibilidade() {
      const zoomInBtn = document.getElementById('zoom-in');
      const zoomOutBtn = document.getElementById('zoom-out');
      const resetBtn = document.getElementById('reset-font');

      const tamanhosFonte = [100, 110, 120, 130, 140, 150];
      let indiceFonteAtual = 0;

      const tamanhoSalvo = localStorage.getItem('tamanhoFonte');
      if (tamanhoSalvo) {
        indiceFonteAtual = parseInt(tamanhoSalvo);
        aplicarTamanhoFonte();
      }

      zoomInBtn.addEventListener('click', () => {
        if (indiceFonteAtual < tamanhosFonte.length - 1) {
          indiceFonteAtual++;
          aplicarTamanhoFonte();
        }
      });

      zoomOutBtn.addEventListener('click', () => {
        if (indiceFonteAtual > 0) {
          indiceFonteAtual--;
          aplicarTamanhoFonte();
        }
      });

      resetBtn.addEventListener('click', () => {
        indiceFonteAtual = 0;
        aplicarTamanhoFonte();
      });

      function aplicarTamanhoFonte() {
        const tamanho = tamanhosFonte[indiceFonteAtual];
        document.body.style.fontSize = `${tamanho}%`;
        localStorage.setItem('tamanhoFonte', indiceFonteAtual);
        zoomInBtn.disabled = indiceFonteAtual === tamanhosFonte.length - 1;
        zoomOutBtn.disabled = indiceFonteAtual === 0;
      }

      aplicarTamanhoFonte();
    }

    // Formatação do telefone
    function formatarTelefone(input) {
      let value = input.value.replace(/\D/g, '');
      if (value.length > 11) value = value.substring(0, 11);
      if (value.length > 10) {
        value = value.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
      } else if (value.length > 6) {
        value = value.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
      }
      input.value = value;
    }

    // Configuração da data
    function configurarDataMinima() {
      const dataInput = document.getElementById('data');
      const hoje = new Date().toISOString().split('T')[0];
      dataInput.min = hoje;
      dataInput.addEventListener('change', carregarHorarios);
    }

    // Carregar horários
    async function carregarHorarios() {
      const data = document.getElementById("data").value;
      if (!data) return;

      const select = document.getElementById("hora");
      select.disabled = true;
      select.innerHTML = '<option value="">Carregando...</option>';

      try {
        const res = await fetch("/horarios?data=" + data);
        const horarios = await res.json();

        select.innerHTML = "";
        if (horarios.length === 0) {
          select.innerHTML = '<option value="">Nenhum horário disponível</option>';
        } else {
          horarios.forEach(h => {
            const opt = document.createElement("option");
            opt.value = h;
            opt.textContent = h;
            select.appendChild(opt);
          });
          select.disabled = false;
        }
      } catch (err) {
        select.innerHTML = '<option value="">Erro ao carregar</option>';
      }
    }

    // Copiar mensagem
    function copiarMensagem(texto) {
      navigator.clipboard.writeText(texto).then(() => {
        alert('Mensagem copiada! Cole no WhatsApp.');
      });
    }

    // Abrir WhatsApp
    function abrirWhatsApp(link) {
      window.open(link, '_blank');
    }

    // Validação do formulário
    function validarFormulario() {
      let valido = true;
      const campos = ['nome', 'telefone', 'servico', 'data', 'hora'];

      campos.forEach(campo => {
        const element = document.getElementById(campo);
        const errorElement = document.getElementById(campo + '-error');

        if (!element.value) {
          errorElement.textContent = 'Campo obrigatório';
          valido = false;
        } else {
          errorElement.textContent = '';
        }
      });

      return valido;
    }

    // Event listeners
    document.addEventListener("DOMContentLoaded", () => {
      inicializarControlesAcessibilidade();

      const form = document.getElementById("bookingForm");
      const telefoneInput = document.getElementById("telefone");

      telefoneInput.addEventListener("input", function() {
        formatarTelefone(this);
      });

      configurarDataMinima();

      form.addEventListener("submit", async (e) => {
        e.preventDefault();

        if (!validarFormulario()) {
          document.getElementById("msg").className = "msg erro";
          document.getElementById("msg").textContent = "Preencha todos os campos.";
          document.getElementById("msg").style.display = "block";
          return;
        }

        const submitBtn = document.getElementById("submit-btn");
        submitBtn.disabled = true;
        submitBtn.textContent = "Processando...";

        try {
          const formData = {
            nome: document.getElementById('nome').value,
            telefone: document.getElementById('telefone').value,
            servico: document.getElementById('servico').value,
            data: document.getElementById('data').value,
            horario: document.getElementById('hora').value
          };

          const res = await fetch("/agendar", {
            method: "POST",
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
          });

          const result = await res.json();

          if (result.success) {
            const msgDiv = document.getElementById("msg");
            msgDiv.innerHTML = `
              <div style="text-align: center;">
                <h3>✅ Agendamento Confirmado!</h3>
                <p><strong>Código:</strong> ${result.numero_confirmacao}</p>
                <button class="whatsapp-btn" onclick="abrirWhatsApp('${result.whatsapp_links.mobile_profissional}')">
                  📱 Abrir WhatsApp
                </button>
                <button class="copy-btn" onclick="copiarMensagem('${result.mensagem_direct}')">
                  📋 Copiar Mensagem
                </button>
                <p><small>Se o WhatsApp não abrir, use a opção "Copiar Mensagem"</small></p>
              </div>
            `;
            msgDiv.className = "msg sucesso";
            msgDiv.style.display = "block";

            // Tentar abrir WhatsApp automaticamente
            setTimeout(() => {
              abrirWhatsApp(result.whatsapp_links.mobile_profissional);
            }, 1000);

            form.reset();
            document.getElementById("hora").innerHTML = '<option value="">Selecione a data primeiro</option>';

          } else {
            document.getElementById("msg").className = "msg erro";
            document.getElementById("msg").textContent = result.message;
            document.getElementById("msg").style.display = "block";
          }
        } catch (error) {
          document.getElementById("msg").className = "msg erro";
          document.getElementById("msg").textContent = "Erro de conexão";
          document.getElementById("msg").style.display = "block";
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = "Confirmar Agendamento";
        }
      });
    });
  </script>
</body>
</html>'''

    # Salvar o HTML
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

    print("Servidor iniciando...")
    print("Acesse: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)