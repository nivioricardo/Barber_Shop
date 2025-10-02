from database import db
from datetime import datetime, timedelta


def test_database():
    print("🧪 TESTANDO BANCO DE DADOS")

    # Testar configurações
    print("\n📊 CONFIGURAÇÕES:")
    configs = [
        'dias_funcionamento',
        'horario_abertura',
        'horario_fechamento',
        'intervalo_almoco_inicio',
        'intervalo_almoco_fim',
        'duracao_padrao',
        'feriados'
    ]

    for config in configs:
        valor = db.obter_configuracao(config)
        print(f"  {config}: {valor}")

    # Testar serviços
    print("\n✂️  SERVIÇOS:")
    servicos = db.obter_servicos()
    for servico in servicos:
        print(f"  {servico['codigo']}: {servico['nome']} - R$ {servico['valor']}")

    # Testar agendamentos
    print("\n📅 AGENDAMENTOS EXISTENTES:")
    amanha = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    agendamentos = db.buscar_agendamentos_por_data(amanha)
    print(f"  Agendamentos para {amanha}: {len(agendamentos)}")
    for ag in agendamentos:
        print(f"    {ag['horario']} - {ag['nome']}")

    # Testar disponibilidade
    print(f"\n🔍 DISPONIBILIDADE PARA {amanha}:")
    for hora in ['09:00', '10:00', '11:00', '14:00', '15:00']:
        disponivel = db.verificar_disponibilidade(amanha, hora)
        status = "✅ Disponível" if disponivel else "❌ Ocupado"
        print(f"  {hora}: {status}")


if __name__ == '__main__':
    test_database()