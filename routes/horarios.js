const express = require("express");
const router = express.Router();
const Agendamento = require("../models/Agendamento");
const mongoose = require("mongoose");

// Configuração de horários de funcionamento
const CONFIG_HORARIOS = {
  diasFuncionamento: [1, 2, 3, 4, 5, 6], // 0 = Domingo, 1 = Segunda, ..., 6 = Sábado
  horarioAbertura: "09:00",
  horarioFechamento: "19:00",
  intervaloAlmoco: {
    inicio: "12:00",
    fim: "13:00"
  },
  duracaoPadrao: 30, // minutos
  feriados: [
    "2024-01-01", "2024-04-21", "2024-05-01", "2024-09-07",
    "2024-10-12", "2024-11-02", "2024-11-15", "2024-12-25"
  ] // Adicionar mais feriados conforme necessário
};

// Validação de data
function validarData(data) {
  if (!data) {
    throw new Error("Data não fornecida");
  }

  const regexData = /^\d{4}-\d{2}-\d{2}$/;
  if (!regexData.test(data)) {
    throw new Error("Formato de data inválido. Use YYYY-MM-DD");
  }

  const dataObj = new Date(data + "T00:00:00");
  if (isNaN(dataObj.getTime())) {
    throw new Error("Data inválida");
  }

  return dataObj;
}

// Verificar se é dia de funcionamento
function isDiaFuncionamento(data) {
  const diaSemana = data.getDay();

  // Verificar se é dia de funcionamento
  if (!CONFIG_HORARIOS.diasFuncionamento.includes(diaSemana)) {
    return false;
  }

  // Verificar se é feriado
  const dataStr = data.toISOString().split('T')[0];
  if (CONFIG_HORARIOS.feriados.includes(dataStr)) {
    return false;
  }

  return true;
}

// Gerar todos os horários possíveis do dia
function gerarHorariosDisponiveis(data) {
  if (!isDiaFuncionamento(data)) {
    return [];
  }

  const horarios = [];
  const [horaAbertura, minutoAbertura] = CONFIG_HORARIOS.horarioAbertura.split(":").map(Number);
  const [horaFechamento, minutoFechamento] = CONFIG_HORARIOS.horarioFechamento.split(":").map(Number);
  const [inicioIntervalo, fimIntervalo] = [
    CONFIG_HORARIOS.intervaloAlmoco.inicio.split(":").map(Number),
    CONFIG_HORARIOS.intervaloAlmoco.fim.split(":").map(Number)
  ];

  let horaAtual = horaAbertura;
  let minutoAtual = minutoAbertura;

  while (horaAtual < horaFechamento || (horaAtual === horaFechamento && minutoAtual < minutoFechamento)) {
    const horario = `${horaAtual.toString().padStart(2, '0')}:${minutoAtual.toString().padStart(2, '0')}`;

    // Verificar se está fora do intervalo de almoço
    const isIntervaloAlmoco =
      (horaAtual > inicioIntervalo[0] || (horaAtual === inicioIntervalo[0] && minutoAtual >= inicioIntervalo[1])) &&
      (horaAtual < fimIntervalo[0] || (horaAtual === fimIntervalo[0] && minutoAtual < fimIntervalo[1]));

    if (!isIntervaloAlmoco) {
      horarios.push(horario);
    }

    // Avançar no tempo
    minutoAtual += CONFIG_HORARIOS.duracaoPadrao;
    if (minutoAtual >= 60) {
      horaAtual += Math.floor(minutoAtual / 60);
      minutoAtual = minutoAtual % 60;
    }
  }

  return horarios;
}

// Rota principal
router.get("/", async (req, res) => {
  try {
    const { data } = req.query;

    // Validações
    if (!data) {
      return res.status(400).json({
        erro: "Parâmetro 'data' é obrigatório",
        exemplo: "/horarios?data=2024-01-15"
      });
    }

    const dataObj = validarData(data);

    // Verificar se não é uma data passada
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    if (dataObj < hoje) {
      return res.status(400).json({
        erro: "Não é possível agendar para datas passadas"
      });
    }

    // Buscar agendamentos para a data específica
    const agendamentos = await Agendamento.find({
      data: dataObj
    }, "horario").lean();

    const horariosOcupados = agendamentos.map(a => a.horario);
    const todosHorarios = gerarHorariosDisponiveis(dataObj);

    const horariosDisponiveis = todosHorarios.filter(
      h => !horariosOcupados.includes(h)
    );

    res.json(horariosDisponiveis);

  } catch (error) {
    console.error("Erro ao carregar horários:", error);

    if (error.message.includes("Data") || error.message.includes("formato")) {
      return res.status(400).json({
        erro: error.message
      });
    }

    res.status(500).json({
      erro: "Erro interno do servidor ao carregar horários"
    });
  }
});

// Rota para obter configurações (útil para o frontend)
router.get("/config", (req, res) => {
  res.json({
    diasFuncionamento: CONFIG_HORARIOS.diasFuncionamento,
    horarioAbertura: CONFIG_HORARIOS.horarioAbertura,
    horarioFechamento: CONFIG_HORARIOS.horarioFechamento,
    intervaloAlmoco: CONFIG_HORARIOS.intervaloAlmoco,
    duracaoPadrao: CONFIG_HORARIOS.duracaoPadrao
  });
});

module.exports = router;