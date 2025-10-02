const express = require("express");
const router = express.Router();
const Agendamento = require("../models/Agendamento");
const rateLimit = require("express-rate-limit");
const mongoose = require("mongoose");

// Rate limiting para prevenir spam
const agendamentoLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutos
  max: 5, // máximo 5 agendamentos por IP a cada 15 minutos
  message: {
    error: "Muitas tentativas de agendamento. Tente novamente em 15 minutos."
  },
  standardHeaders: true,
  legacyHeaders: false,
});

// Aplicar rate limiting
router.use(agendamentoLimiter);

// Sanitizar dados para prevenir NoSQL injection
function sanitizeInput(input) {
  if (typeof input === 'string') {
    return input.trim().replace(/[$\{\}]/g, '');
  }
  return input;
}

// Validar formato do telefone
function validarTelefone(telefone) {
  const regex = /^\(\d{2}\)\s\d{4,5}-\d{4}$/;
  return regex.test(telefone);
}

// Validar formato da data
function validarData(data) {
  const regex = /^\d{4}-\d{2}-\d{2}$/;
  if (!regex.test(data)) return false;

  const dataObj = new Date(data + "T00:00:00");
  if (isNaN(dataObj.getTime())) return false;

  // Não permitir datas passadas
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  return dataObj >= hoje;
}

// Validar horário
function validarHorario(horario) {
  const regex = /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/;
  if (!regex.test(horario)) return false;

  const [hora, minuto] = horario.split(':').map(Number);
  return hora >= 0 && hora <= 23 && minuto >= 0 && minuto <= 59;
}

// Validar serviço
function validarServico(servico) {
  const servicosValidos = ['corte', 'kids', 'combo', 'degrade'];
  return servicosValidos.includes(servico);
}

// Mapear códigos de serviço para nomes
function obterNomeServico(codigo) {
  const servicos = {
    'corte': 'Corte Social',
    'kids': 'Corte Kids',
    'combo': 'Cabelo e Barba',
    'degrade': 'Degradê Giletado'
  };
  return servicos[codigo] || 'Serviço não especificado';
}

// Gerar número de confirmação
function gerarNumeroConfirmacao() {
  return 'BS' + Date.now().toString().slice(-8) + Math.random().toString(36).substr(2, 3).toUpperCase();
}

router.post("/", async (req, res) => {
  try {
    // Sanitizar todos os campos
    const camposSanitizados = {};
    Object.keys(req.body).forEach(key => {
      camposSanitizados[key] = sanitizeInput(req.body[key]);
    });

    const { nome, telefone, servico, data, horario, csrf_token } = camposSanitizados;

    // Validar CSRF token (simplificado - em produção usar biblioteca dedicada)
    if (!csrf_token || csrf_token !== 'token_seguranca_gerado_pelo_servidor') {
      return res.status(403).json({
        success: false,
        message: "Token de segurança inválido."
      });
    }

    // Validar campos obrigatórios
    const camposObrigatorios = { nome, telefone, servico, data, horario };
    const camposFaltantes = Object.keys(camposObrigatorios).filter(key => !camposObrigatorios[key]);

    if (camposFaltantes.length > 0) {
      return res.status(400).json({
        success: false,
        message: `Campos obrigatórios faltando: ${camposFaltantes.join(', ')}`
      });
    }

    // Validações específicas
    if (nome.length < 2 || nome.length > 50) {
      return res.status(400).json({
        success: false,
        message: "Nome deve ter entre 2 e 50 caracteres."
      });
    }

    if (!validarTelefone(telefone)) {
      return res.status(400).json({
        success: false,
        message: "Telefone inválido. Use o formato (XX) XXXXX-XXXX."
      });
    }

    if (!validarServico(servico)) {
      return res.status(400).json({
        success: false,
        message: "Serviço inválido."
      });
    }

    if (!validarData(data)) {
      return res.status(400).json({
        success: false,
        message: "Data inválida. Use o formato YYYY-MM-DD e selecione uma data futura."
      });
    }

    if (!validarHorario(horario)) {
      return res.status(400).json({
        success: false,
        message: "Horário inválido."
      });
    }

    // Verificar se já existe agendamento nessa data e horário
    const agendamentoExistente = await Agendamento.findOne({
      data: new Date(data + "T00:00:00"),
      horario
    });

    if (agendamentoExistente) {
      return res.status(409).json({
        success: false,
        message: "Horário já agendado. Por favor, selecione outro horário."
      });
    }

    // Verificar limite de agendamentos por telefone (prevenir spam)
    const agendamentosRecentes = await Agendamento.countDocuments({
      telefone,
      data: {
        $gte: new Date(new Date().setDate(new Date().getDate() - 7)) // últimos 7 dias
      }
    });

    if (agendamentosRecentes >= 3) {
      return res.status(429).json({
        success: false,
        message: "Limite de agendamentos excedido. Máximo 3 agendamentos por semana."
      });
    }

    // Criar novo agendamento
    const numeroConfirmacao = gerarNumeroConfirmacao();
    const nomeServico = obterNomeServico(servico);

    const novoAgendamento = new Agendamento({
      nome,
      telefone,
      servico: nomeServico,
      codigoServico: servico,
      data: new Date(data + "T00:00:00"),
      horario,
      numeroConfirmacao,
      dataCriacao: new Date(),
      ip: req.ip
    });

    await novoAgendamento.save();

    // Em produção, aqui enviaria SMS/WhatsApp de confirmação
    console.log(`📱 Confirmação agendamento ${numeroConfirmacao}: ${nome} - ${data} às ${horario}`);

    res.status(201).json({
      success: true,
      message: "Agendamento confirmado com sucesso!",
      numeroConfirmacao,
      agendamento: {
        nome,
        servico: nomeServico,
        data,
        horario,
        telefone
      }
    });

  } catch (error) {
    console.error("Erro no agendamento:", error);

    // Erros do MongoDB
    if (error instanceof mongoose.Error.ValidationError) {
      const errors = Object.values(error.errors).map(err => err.message);
      return res.status(400).json({
        success: false,
        message: "Dados inválidos: " + errors.join(', ')
      });
    }

    if (error.code === 11000) {
      return res.status(409).json({
        success: false,
        message: "Conflito de agendamento. Este horário já está reservado."
      });
    }

    res.status(500).json({
      success: false,
      message: "Erro interno do servidor. Tente novamente em alguns minutos."
    });
  }
});

// Rota para cancelar agendamento
router.delete("/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const { telefone } = req.body;

    if (!telefone) {
      return res.status(400).json({
        success: false,
        message: "Telefone é obrigatório para cancelamento."
      });
    }

    const agendamento = await Agendamento.findOne({
      _id: id,
      telefone
    });

    if (!agendamento) {
      return res.status(404).json({
        success: false,
        message: "Agendamento não encontrado ou telefone não corresponde."
      });
    }

    // Verificar se não é muito próximo do horário agendado
    const agora = new Date();
    const dataAgendamento = new Date(agendamento.data);
    dataAgendamento.setHours(...agendamento.horario.split(':').map(Number));

    const diferencaHoras = (dataAgendamento - agora) / (1000 * 60 * 60);

    if (diferencaHoras < 2) {
      return res.status(400).json({
        success: false,
        message: "Cancelamento não permitido com menos de 2 horas de antecedência."
      });
    }

    await Agendamento.findByIdAndDelete(id);

    res.json({
      success: true,
      message: "Agendamento cancelado com sucesso."
    });

  } catch (error) {
    console.error("Erro ao cancelar agendamento:", error);
    res.status(500).json({
      success: false,
      message: "Erro interno ao cancelar agendamento."
    });
  }
});

// Rota para consultar agendamentos por telefone
router.get("/consulta/:telefone", async (req, res) => {
  try {
    const { telefone } = req.params;

    if (!validarTelefone(telefone)) {
      return res.status(400).json({
        success: false,
        message: "Telefone inválido."
      });
    }

    const agendamentos = await Agendamento.find({
      telefone,
      data: { $gte: new Date() }
    }).sort({ data: 1, horario: 1 });

    res.json({
      success: true,
      agendamentos: agendamentos.map(ag => ({
        id: ag._id,
        nome: ag.nome,
        servico: ag.servico,
        data: ag.data.toISOString().split('T')[0],
        horario: ag.horario,
        numeroConfirmacao: ag.numeroConfirmacao
      }))
    });

  } catch (error) {
    console.error("Erro ao consultar agendamentos:", error);
    res.status(500).json({
      success: false,
      message: "Erro interno ao consultar agendamentos."
    });
  }
});

module.exports = router;