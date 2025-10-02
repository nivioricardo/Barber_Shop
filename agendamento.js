const mongoose = require("mongoose");

const AgendamentoSchema = new mongoose.Schema({
  // Informações do cliente
  nome: {
    type: String,
    required: [true, "Nome é obrigatório"],
    trim: true,
    minlength: [2, "Nome deve ter pelo menos 2 caracteres"],
    maxlength: [100, "Nome deve ter no máximo 100 caracteres"],
    match: [/^[a-zA-ZÀ-ÿ\s']+$/, "Nome deve conter apenas letras e espaços"]
  },

  telefone: {
    type: String,
    required: [true, "Telefone é obrigatório"],
    trim: true,
    match: [/^\(\d{2}\)\s\d{4,5}-\d{4}$/, "Telefone deve estar no formato (XX) XXXXX-XXXX"],
    index: true
  },

  // Informações do serviço
  servico: {
    type: String,
    required: [true, "Serviço é obrigatório"],
    enum: {
      values: ["Corte Social", "Corte Kids", "Cabelo e Barba", "Degradê Giletado"],
      message: "Serviço {VALUE} não é válido"
    }
  },

  codigoServico: {
    type: String,
    required: [true, "Código do serviço é obrigatório"],
    enum: ["corte", "kids", "combo", "degrade"],
    index: true
  },

  // Data e horário
  data: {
    type: Date,
    required: [true, "Data é obrigatória"],
    index: true,
    validate: {
      validator: function(value) {
        return value >= new Date().setHours(0, 0, 0, 0);
      },
      message: "Data não pode ser no passado"
    }
  },

  horario: {
    type: String,
    required: [true, "Horário é obrigatório"],
    match: [/^([01]?[0-9]|2[0-3]):[0-5][0-9]$/, "Horário deve estar no formato HH:MM"],
    index: true
  },

  // Metadados e controle
  numeroConfirmacao: {
    type: String,
    required: true,
    unique: true,
    index: true,
    match: [/^BS\d{8}[A-Z0-9]{3}$/, "Formato do número de confirmação inválido"]
  },

  status: {
    type: String,
    enum: {
      values: ["confirmado", "cancelado", "concluído", "ausente"],
      message: "Status {VALUE} não é válido"
    },
    default: "confirmado",
    index: true
  },

  duracaoEstimada: {
    type: Number, // em minutos
    required: true,
    min: [15, "Duração mínima deve ser 15 minutos"],
    max: [180, "Duração máxima deve ser 180 minutos"]
  },

  valor: {
    type: Number,
    required: true,
    min: [0, "Valor não pode ser negativo"]
  },

  observacoes: {
    type: String,
    maxlength: [500, "Observações não podem exceder 500 caracteres"],
    trim: true
  },

  // Auditoria e segurança
  ipCliente: {
    type: String,
    match: [/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/, "IP inválido"]
  },

  userAgent: {
    type: String,
    maxlength: 500
  },

  // Controle de cancelamento
  canceladoEm: {
    type: Date
  },

  motivoCancelamento: {
    type: String,
    maxlength: [200, "Motivo do cancelamento não pode exceder 200 caracteres"]
  }

}, {
  timestamps: true, // Cria createdAt e updatedAt automaticamente
  toJSON: {
    virtuals: true,
    transform: function(doc, ret) {
      ret.id = ret._id;
      delete ret._id;
      delete ret.__v;
      return ret;
    }
  },
  toObject: { virtuals: true }
});

// Índices compostos para otimizar consultas comuns
AgendamentoSchema.index({ data: 1, horario: 1 });
AgendamentoSchema.index({ telefone: 1, data: 1 });
AgendamentoSchema.index({ status: 1, data: 1 });
AgendamentoSchema.index({ "createdAt": 1 });

// Virtual para verificar se é um agendamento futuro
AgendamentoSchema.virtual('isFuturo').get(function() {
  const agora = new Date();
  const dataAgendamento = new Date(this.data);
  dataAgendamento.setHours(...this.horario.split(':').map(Number));
  return dataAgendamento > agora;
});

// Virtual para tempo restante até o agendamento
AgendamentoSchema.virtual('tempoRestante').get(function() {
  const agora = new Date();
  const dataAgendamento = new Date(this.data);
  dataAgendamento.setHours(...this.horario.split(':').map(Number));
  return dataAgendamento - agora;
});

// Virtual para data/hora completa
AgendamentoSchema.virtual('dataHoraCompleta').get(function() {
  const data = new Date(this.data);
  const [hora, minuto] = this.horario.split(':').map(Number);
  data.setHours(hora, minuto, 0, 0);
  return data;
});

// Método de instância para cancelar agendamento
AgendamentoSchema.methods.cancelar = function(motivo = "Cancelado pelo cliente") {
  this.status = "cancelado";
  this.canceladoEm = new Date();
  this.motivoCancelamento = motivo;
  return this.save();
};

// Método de instância para verificar se pode ser cancelado
AgendamentoSchema.methods.podeSerCancelado = function() {
  if (this.status !== "confirmado") return false;

  const agora = new Date();
  const dataAgendamento = new Date(this.data);
  dataAgendamento.setHours(...this.horario.split(':').map(Number));

  const diferencaHoras = (dataAgendamento - agora) / (1000 * 60 * 60);
  return diferencaHoras >= 2; // Pode cancelar com pelo menos 2h de antecedência
};

// Método estático para buscar agendamentos futuros por telefone
AgendamentoSchema.statics.buscarFuturosPorTelefone = function(telefone) {
  return this.find({
    telefone,
    data: { $gte: new Date().setHours(0, 0, 0, 0) },
    status: "confirmado"
  }).sort({ data: 1, horario: 1 });
};

// Método estático para verificar disponibilidade
AgendamentoSchema.statics.verificarDisponibilidade = function(data, horario) {
  return this.findOne({
    data: new Date(data),
    horario,
    status: "confirmado"
  });
};

// Método estático para estatísticas
AgendamentoSchema.statics.obterEstatisticas = async function(dataInicio, dataFim) {
  const matchStage = {
    createdAt: {
      $gte: new Date(dataInicio),
      $lte: new Date(dataFim)
    }
  };

  return this.aggregate([
    { $match: matchStage },
    {
      $group: {
        _id: null,
        totalAgendamentos: { $sum: 1 },
        totalConfirmados: {
          $sum: { $cond: [{ $eq: ["$status", "confirmado"] }, 1, 0] }
        },
        totalCancelados: {
          $sum: { $cond: [{ $eq: ["$status", "cancelado"] }, 1, 0] }
        },
        totalConcluidos: {
          $sum: { $cond: [{ $eq: ["$status", "concluído"] }, 1, 0] }
        },
        faturamentoTotal: { $sum: "$valor" },
        servicoMaisPopular: { $push: "$servico" }
      }
    },
    {
      $project: {
        _id: 0,
        totalAgendamentos: 1,
        totalConfirmados: 1,
        totalCancelados: 1,
        totalConcluidos: 1,
        faturamentoTotal: 1,
        taxaCancelamento: {
          $round: [
            { $multiply: [{ $divide: ["$totalCancelados", "$totalAgendamentos"] }, 100] },
            2
          ]
        }
      }
    }
  ]);
};

// Middleware pré-save para calcular duração e valor baseado no serviço
AgendamentoSchema.pre('save', function(next) {
  // Mapeamento de serviços para duração e valor
  const configServicos = {
    'corte': { duracao: 30, valor: 45.00 },
    'kids': { duracao: 25, valor: 35.00 },
    'combo': { duracao: 50, valor: 70.00 },
    'degrade': { duracao: 40, valor: 60.00 }
  };

  const servicoConfig = configServicos[this.codigoServico];
  if (servicoConfig) {
    this.duracaoEstimada = servicoConfig.duracao;
    this.valor = servicoConfig.valor;
  }

  // Gerar número de confirmação se não existir
  if (!this.numeroConfirmacao) {
    this.numeroConfirmacao = 'BS' +
      Date.now().toString().slice(-8) +
      Math.random().toString(36).substr(2, 3).toUpperCase();
  }

  next();
});

// Middleware para validar conflitos de horário
AgendamentoSchema.pre('save', async function(next) {
  if (this.isModified('data') || this.isModified('horario') || this.isNew) {
    const conflito = await this.constructor.verificarDisponibilidade(this.data, this.horario);

    if (conflito && !conflito._id.equals(this._id)) {
      const err = new Error('Horário já está agendado');
      err.name = 'ConflitoHorario';
      return next(err);
    }
  }
  next();
});

module.exports = mongoose.model("Agendamento", AgendamentoSchema);