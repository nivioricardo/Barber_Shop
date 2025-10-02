// Configuração inicial
document.addEventListener("DOMContentLoaded", () => {
  // Definir data mínima como hoje
  const dataInput = document.getElementById("data");
  const hoje = new Date().toISOString().split("T")[0];
  dataInput.min = hoje;

  // Configurar máscara de telefone
  const telefoneInput = document.getElementById("telefone");
  telefoneInput.addEventListener("input", formatarTelefone);

  // Configurar validação em tempo real
  configurarValidacaoEmTempoReal();

  // Configurar envio do formulário
  const form = document.getElementById("bookingForm");
  form.addEventListener("submit", processarAgendamento);
});

// Formatar telefone
function formatarTelefone(e) {
  let value = e.target.value.replace(/\D/g, '');

  if (value.length > 11) {
    value = value.substring(0, 11);
  }

  if (value.length > 10) {
    value = value.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
  } else if (value.length > 6) {
    value = value.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
  } else if (value.length > 2) {
    value = value.replace(/(\d{2})(\d{0,5})/, '($1) $2');
  } else if (value.length > 0) {
    value = value.replace(/(\d{0,2})/, '($1');
  }

  e.target.value = value;
}

// Configurar validação em tempo real
function configurarValidacaoEmTempoReal() {
  const campos = document.querySelectorAll('input[required], select[required]');

  campos.forEach(campo => {
    campo.addEventListener('blur', validarCampo);
    campo.addEventListener('input', limparErroCampo);
  });
}

// Validar campo individual
function validarCampo(e) {
  const campo = e.target;
  const valor = campo.value.trim();
  const campoId = campo.id;
  const erroElemento = document.getElementById(`${campoId}-error`);

  // Limpar erro anterior
  limparErroCampo(e);

  // Validar campo vazio
  if (!valor) {
    mostrarErroCampo(campo, erroElemento, 'Este campo é obrigatório');
    return false;
  }

  // Validações específicas por campo
  switch(campoId) {
    case 'telefone':
      if (!validarTelefone(valor)) {
        mostrarErroCampo(campo, erroElemento, 'Telefone inválido. Use o formato (XX) XXXXX-XXXX');
        return false;
      }
      break;

    case 'data':
      if (!validarData(valor)) {
        mostrarErroCampo(campo, erroElemento, 'Data inválida. Selecione uma data futura');
        return false;
      }
      break;
  }

  return true;
}

// Validar telefone
function validarTelefone(telefone) {
  const regex = /^\(\d{2}\)\s\d{4,5}-\d{4}$/;
  return regex.test(telefone);
}

// Validar data
function validarData(data) {
  const dataSelecionada = new Date(data);
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);

  return dataSelecionada >= hoje;
}

// Mostrar erro no campo
function mostrarErroCampo(campo, erroElemento, mensagem) {
  campo.style.borderColor = '#e74c3c';
  erroElemento.textContent = mensagem;
}

// Limpar erro do campo
function limparErroCampo(e) {
  const campo = e.target;
  const campoId = campo.id;
  const erroElemento = document.getElementById(`${campoId}-error`);

  campo.style.borderColor = '#ccc';
  erroElemento.textContent = '';
}

// Carregar horários disponíveis
async function carregarHorarios() {
  const data = document.getElementById("data").value;
  if (!data) return;

  // Validar data
  if (!validarData(data)) {
    mostrarMensagem("Por favor, selecione uma data futura.", false);
    return;
  }

  const select = document.getElementById("hora");
  const submitBtn = document.getElementById("submit-btn");

  try {
    // Mostrar indicador de carregamento
    select.disabled = true;
    select.innerHTML = '<option value="">Carregando horários...</option>';

    // Simular atraso de rede para demonstração
    await new Promise(resolve => setTimeout(resolve, 800));

    const res = await fetch("horarios.php?data=" + encodeURIComponent(data), {
      headers: {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
      }
    });

    if (!res.ok) {
      throw new Error(`Erro ${res.status}: ${res.statusText}`);
    }

    const horarios = await res.json();

    select.innerHTML = "";

    if (!horarios || horarios.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Nenhum horário disponível para esta data";
      select.appendChild(opt);
      select.disabled = true;
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
    console.error("Erro ao carregar horários:", err);
    mostrarMensagem("Erro ao carregar horários disponíveis. Tente novamente.", false);

    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Erro ao carregar horários";
    select.innerHTML = "";
    select.appendChild(opt);
    select.disabled = true;
  }
}

// Processar agendamento
async function processarAgendamento(e) {
  e.preventDefault();

  // Validar todos os campos
  const camposValidos = validarFormularioCompleto();
  if (!camposValidos) {
    mostrarMensagem("Por favor, corrija os erros no formulário antes de enviar.", false);
    return;
  }

  // Confirmar envio
  if (!confirm("Confirma o agendamento?")) {
    return;
  }

  const form = e.target;
  const formData = new FormData(form);
  const submitBtn = document.getElementById("submit-btn");
  const btnText = submitBtn.querySelector('.btn-text');
  const loadingSpinner = submitBtn.querySelector('.loading-spinner');

  try {
    // Mostrar estado de carregamento
    submitBtn.disabled = true;
    btnText.style.display = 'none';
    loadingSpinner.style.display = 'inline-block';

    // Simular atraso de rede para demonstração
    await new Promise(resolve => setTimeout(resolve, 1500));

    const res = await fetch("agendar.php", {
      method: "POST",
      headers: {
        'X-CSRF-Token': document.getElementById('csrf_token').value
      },
      body: formData
    });

    const result = await res.json();

    if (result.sucesso) {
      mostrarMensagem("✅ Agendamento confirmado! Enviaremos uma confirmação por WhatsApp.", true);
      form.reset();
      document.getElementById("hora").innerHTML = '<option value="">Selecione a data primeiro</option>';
    } else {
      mostrarMensagem("❌ Erro: " + (result.mensagem || "Não foi possível agendar."), false);
    }
  } catch (error) {
    console.error("Erro ao enviar agendamento:", error);
    mostrarMensagem("Erro de conexão. Verifique sua internet e tente novamente.", false);
  } finally {
    // Restaurar estado normal do botão
    submitBtn.disabled = false;
    btnText.style.display = 'inline-block';
    loadingSpinner.style.display = 'none';
  }
}

// Validar formulário completo
function validarFormularioCompleto() {
  const campos = document.querySelectorAll('input[required], select[required]');
  let formularioValido = true;

  campos.forEach(campo => {
    // Disparar evento blur para validar cada campo
    const event = new Event('blur', { bubbles: true });
    campo.dispatchEvent(event);

    // Verificar se há erro
    const campoId = campo.id;
    const erroElemento = document.getElementById(`${campoId}-error`);

    if (erroElemento.textContent) {
      formularioValido = false;
    }
  });

  return formularioValido;
}

// Mostrar mensagem
function mostrarMensagem(texto, sucesso = true) {
  const msgDiv = document.getElementById("msg");
  msgDiv.textContent = texto;
  msgDiv.className = "msg " + (sucesso ? "sucesso" : "erro");
  msgDiv.style.display = "block";

  // Rolagem suave para a mensagem
  msgDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  // Auto-esconder mensagens de sucesso após 5 segundos
  if (sucesso) {
    setTimeout(() => {
      msgDiv.style.display = "none";
    }, 5000);
  }
}