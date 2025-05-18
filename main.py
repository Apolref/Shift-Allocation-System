import pandas as pd
import os
import streamlit as st
import random
import signal
from datetime import datetime, date
from calendar import monthrange

CAMINHO_CSV_DEFAULT = r"C:\\Users\\alelo\\OneDrive\\Documentos\\USP\\TCC\\Projeto\\funcionarios_upa.csv"

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

REGRAS_SETOR = {
    "Sala de emergência": {"min_total": 6, "min_enfermeiros": 1},
    "Sala de sutura e CME": {"min_total": 2, "min_enfermeiros": 0},
    "Sala de medicação": {"min_total": 6, "min_enfermeiros": 1},
    "Classificação de risco": {"min_total": 2, "min_enfermeiros": 2},
    "Repouso/observação": {"min_total": 6, "min_enfermeiros": 1}
}

class Funcionario:
    def __init__(self, nome, coren, profissao, horario, setor, turno_id, setores_preferidos=None):
        self.nome = nome
        self.coren = coren
        self.profissao = profissao
        self.horario = horario
        self.setor = setor if setor != "Setor de observação/repouso" else "Repouso/observação"
        self.turno_id = turno_id
        self.setores_preferidos = setores_preferidos if setores_preferidos else []

    def turno(self):
        return "Diurno" if "07x" in self.horario else "Noturno"

    def dias(self, mes_atual, ano_atual):
        if mes_atual == 1:
            mes_anterior = 12
            ano_anterior = ano_atual - 1
        else:
            mes_anterior = mes_atual - 1
            ano_anterior = ano_atual
        ultimo_dia_anterior = monthrange(ano_anterior, mes_anterior)[1]
        if ultimo_dia_anterior % 2 == 1:
            return list(range(2, 32, 2)) if self.turno_id == "A" else list(range(1, 31, 2))
        else:
            return list(range(1, 31, 2)) if self.turno_id == "A" else list(range(2, 32, 2))

    def to_dict(self):
        entrada, saida = self.horario.split("x")
        return {
            "Nome": self.nome,
            "Função": self.profissao,
            "COREN-SP": self.coren,
            "Turno": self.turno(),
            "Horário": f"{entrada}x{saida}",
            "Plantão": self.turno_id,
            "Setor": self.setor,
            "Setores Preferidos": ", ".join(self.setores_preferidos)
        }

def verificar_necessidade_setor(df_funcionarios, setor_afetado, data, nome_faltante):
    try:
        dia = int(data.split("-")[2])  # Garante que o formato seja YYYY-MM-DD
    except Exception as e:
        return {"suprido": False, "mensagem": f"Erro ao interpretar a data: {e}"}

    # Filtra funcionários alocados no setor
    df_setor = df_funcionarios[df_funcionarios["Setor"] == setor_afetado]

    # Remove o funcionário faltante da análise
    df_setor = df_setor[df_setor["Nome"] != nome_faltante]

    total_restante = len(df_setor)
    enfermeiros_restantes = len(df_setor[df_setor["Função"] == "Enfermeiro"])

    requisitos = REGRAS_SETOR.get(setor_afetado, {"min_total": 0, "min_enfermeiros": 0})
    min_total = requisitos["min_total"]
    min_enf = requisitos["min_enfermeiros"]

    if total_restante >= min_total and enfermeiros_restantes >= min_enf:
        return {
            "suprido": True,
            "mensagem": f"As necessidades mínimas do setor **{setor_afetado}** estão sendo mantidas após a falta."
        }
    else:
        return {
            "suprido": False,
            "mensagem": f"Atenção: o setor **{setor_afetado}** está com pessoal insuficiente após a falta."
        }

def carregar_funcionarios(csv_path):
    df = pd.read_csv(csv_path)
    funcionarios = []
    for _, row in df.iterrows():
        setores_preferidos = []
        if "Setores Preferidos" in row and pd.notna(row["Setores Preferidos"]):
            setores_preferidos = [s.strip() for s in str(row["Setores Preferidos"]).split(',')]
        funcionarios.append(Funcionario(
            nome=row["Nome"],
            coren=row["COREN-SP"],
            profissao=row["Função"],
            horario=row["Horário"],
            setor=row["Setor"],
            turno_id=row["Plantão"],
            setores_preferidos=setores_preferidos
        ))
    return funcionarios
def distribuir_com_regras(funcionarios, turno, turno_id):
    setores_alocados = {s: [] for s in REGRAS_SETOR.keys()}
    funcionarios_turno = [f for f in funcionarios if f.turno() == turno and f.turno_id == turno_id]
    random.shuffle(funcionarios_turno)

    utilizados = set()

    # ETAPA 1: GARANTIR MÍNIMO DE ENFERMEIROS POR SETOR
    for setor, regras in REGRAS_SETOR.items():
        min_enf = regras["min_enfermeiros"]
        enfermeiros_disp = [f for f in funcionarios_turno if f not in utilizados and f.profissao == "Enfermeiro"]

        alocados_enf = []
        for f in enfermeiros_disp:
            if len(alocados_enf) < min_enf:
                alocados_enf.append(f)
                utilizados.add(f)
            else:
                break

        setores_alocados[setor].extend(alocados_enf)

    # ETAPA 2: GARANTIR MÍNIMO TOTAL DE FUNCIONÁRIOS POR SETOR
    for setor, regras in REGRAS_SETOR.items():
        min_total = regras["min_total"]
        ja_alocados = setores_alocados[setor]
        faltam = max(0, min_total - len(ja_alocados))

        disponiveis = [f for f in funcionarios_turno if f not in utilizados]
        random.shuffle(disponiveis)

        for f in disponiveis:
            if faltam <= 0:
                break
            setores_alocados[setor].append(f)
            utilizados.add(f)
            faltam -= 1

    # ETAPA 3: REDISTRIBUIR QUEM SOBROU IGUALMENTE ENTRE OS SETORES
    nao_alocados = [f for f in funcionarios_turno if f not in utilizados]
    setores = list(REGRAS_SETOR.keys())
    i = 0

    while nao_alocados:
        f = nao_alocados.pop()
        setor_destino = None

        # Prioriza setor preferido entre os disponíveis
        for pref in f.setores_preferidos:
            if pref in setores:
                setor_destino = pref
                break

        # Se não tiver preferência válida, alocar circularmente
        if not setor_destino:
            setor_destino = setores[i % len(setores)]
            i += 1

        setores_alocados[setor_destino].append(f)
        utilizados.add(f)

    return setores_alocados


def alocar_escala(funcionarios, rotatividade=False, frequencia_rotatividade=1, mes_atual=None, gerar_para_meses=1, ano_atual=None):
    if mes_atual is None:
        mes_atual = datetime.now().month
    if ano_atual is None:
        ano_atual = datetime.now().year

    resultados = []

    for i in range(gerar_para_meses):
        mes = ((mes_atual - 1 + i) % 12) + 1
        ano = ano_atual + ((mes_atual - 1 + i) // 12)
        nome_mes = MESES_PT[mes - 1]
        aplicar_rotatividade = rotatividade and (mes % frequencia_rotatividade == 0)

        for turno in ["Diurno", "Noturno"]:
            for turno_id in ["A", "B"]:
                setores = distribuir_com_regras(funcionarios, turno, turno_id)

                os.makedirs("escalas", exist_ok=True)

                for setor_alocado, lista in setores.items():
                    dados = []

                    for f in lista:
                        # Se houver rotatividade, sortear outro setor preferido
                        setor_final = setor_alocado
                        if aplicar_rotatividade:
                            compat = [s for s in f.setores_preferidos if s != f.setor and s in REGRAS_SETOR]
                            if compat:
                                setor_final = random.choice(compat)

                        # Criar linha baseada no funcionário original, mas com setor da alocação
                        linha = f.to_dict()
                        linha["Setor"] = setor_final
                        linha["Mês"] = f"{nome_mes} de {ano}"
                        marca = "D" if f.turno() == "Diurno" else "N"

                        for dia in f.dias(mes, ano):
                            linha[f"Dia {dia}"] = marca

                        dados.append(linha)

                    if dados:
                        df = pd.DataFrame(dados)
                        nome_arquivo = f"{setor_alocado.replace(' ', '_').replace('/', '-')}_({turno} {turno_id})_{nome_mes}_{ano}.csv"
                        caminho_completo = os.path.join("escalas", nome_arquivo)
                        df.to_csv(caminho_completo, index=False)
                        resultados.append((f"{setor_alocado} ({turno} {turno_id}) - {nome_mes} de {ano}", caminho_completo, df))

    return resultados


def adicionar_funcionario_interface():
    st.subheader("Adicionar novo funcionário")

    setores_possiveis = [
        "Classificação de risco", "Sala de emergência", "Sala de medicação",
        "Sala de sutura e CME", "Repouso/observação", "Setor de observação/repouso"
    ]

    with st.form("form_funcionario"):
        nome = st.text_input("Nome completo")
        coren = st.text_input("Número do COREN-SP")
        profissao = st.selectbox("Profissão", ["Enfermeiro", "Técnico de enfermagem", "Auxiliar de enfermagem"])
        horario = st.selectbox("Horário de trabalho", ["07x19", "19x07"])
        setor = st.selectbox("Setor", setores_possiveis)
        turno_id = st.selectbox("Plantão (A para dias ímpares, B para dias pares)", ["A", "B"])
        setores_preferidos = st.multiselect("Setores preferidos (opcional)", options=[s for s in setores_possiveis if s != setor])

        submitted = st.form_submit_button("Adicionar")

        if submitted:
            novo_funcionario = {
                "Nome": nome,
                "COREN-SP": coren,
                "Função": profissao,
                "Horário": horario,
                "Setor": setor,
                "Plantão": turno_id,
                "Setores Preferidos": ", ".join(setores_preferidos)
            }
            try:
                df = pd.read_csv(CAMINHO_CSV_DEFAULT)
                df = pd.concat([df, pd.DataFrame([novo_funcionario])], ignore_index=True)
                df.to_csv(CAMINHO_CSV_DEFAULT, index=False)
                st.success("Funcionário adicionado com sucesso!")
            except Exception as e:
                st.error(f"Erro ao adicionar funcionário: {e}")

import locale
locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')  # Exibe os meses em português

def registrar_ocorrencia(nome, data, motivo):
    mes_abrev = data.strftime("%b").lower()
    ano = data.year
    nome_arquivo = f"relatorio_ocorrencias_{mes_abrev}_{ano}.csv"
    caminho_arquivo = os.path.join("ocorrencias", nome_arquivo)

    nova_ocorrencia = pd.DataFrame([{
        "Nome": nome,
        "Data": data.strftime("%d/%b/%Y"),
        "Motivo da Ocorrência": motivo
    }])

    os.makedirs("ocorrencias", exist_ok=True)

    if os.path.exists(caminho_arquivo):
        df_existente = pd.read_csv(caminho_arquivo)
        df_total = pd.concat([df_existente, nova_ocorrencia], ignore_index=True)
    else:
        df_total = nova_ocorrencia

    df_total.to_csv(caminho_arquivo, index=False)

def obter_setor_real(nome_funcionario, data, turno, plantao):
    """
    Retorna o setor em que o funcionário está alocado na escala gerada para o mês e ano da data fornecida.
    """
    nome_funcionario = nome_funcionario.strip().lower()
    mes = MESES_PT[data.month - 1]
    ano = data.year

    escala_dir = "escalas"
    if not os.path.exists(escala_dir):
        return None

    for arquivo in os.listdir(escala_dir):
        if not arquivo.endswith(".csv"):
            continue
        if f"({turno} {plantao})" in arquivo and f"{mes}_{ano}" in arquivo:
            caminho = os.path.join(escala_dir, arquivo)
            try:
                df = pd.read_csv(caminho)
                for _, row in df.iterrows():
                    if row["Nome"].strip().lower() == nome_funcionario:
                        return row.get("Setor", None)
            except Exception:
                continue
    return None

def verificar_impacto_falta(nome_faltante, data, funcionarios):
    dia = data.day
    mes = data.month
    ano = data.year
    dia_coluna = f"Dia {dia}"

    funcionario = next((f for f in funcionarios if f.nome == nome_faltante), None)
    if not funcionario:
        return {"erro": "Funcionário não encontrado."}

    setor = funcionario.setor
    turno = funcionario.turno()
    turno_id = funcionario.turno_id

    nome_arquivo_esperado = f"{setor.replace(' ', '_').replace('/', '-')}_({turno} {turno_id})_{MESES_PT[mes - 1]}_{ano}.csv"
    caminho_escala = os.path.join("escalas", nome_arquivo_esperado)

    if not os.path.exists(caminho_escala):
        return {"erro": f"Arquivo de escala {nome_arquivo_esperado} não encontrado."}

    try:
        df_escala = pd.read_csv(caminho_escala)
    except Exception as e:
        return {"erro": f"Erro ao ler escala: {e}"}

    if dia_coluna not in df_escala.columns:
        return {"erro": f"A escala não contém a coluna {dia_coluna}."}

    # Funcionários efetivamente em serviço no dia (com marcação "D" ou "N")
    em_servico = df_escala[
        (df_escala[dia_coluna].isin(["D", "N"])) &
        (df_escala["Setor"] == setor) &
        (df_escala["Plantão"] == turno_id)
    ]

    total_em_servico = len(em_servico)
    total_enfermeiros = sum(em_servico["Função"] == "Enfermeiro")

    requisitos = REGRAS_SETOR.get(setor, {"min_total": 0, "min_enfermeiros": 0})
    min_total = requisitos["min_total"]
    min_enf = requisitos["min_enfermeiros"]

    mensagens = []
    suprido = True

    if total_em_servico < min_total:
        mensagens.append(f"⚠️ Setor **{setor}** com apenas {total_em_servico} funcionários (mínimo: {min_total}).")
        suprido = False

    if total_enfermeiros < min_enf:
        mensagens.append(f"⚠️ Setor **{setor}** com apenas {total_enfermeiros} enfermeiro(s) (mínimo: {min_enf}).")
        suprido = False

    # Verificar se há substitutos possíveis (sobras de outros setores no mesmo turno e plantão)
    sobras = []
    for f in funcionarios:
        if (
            f.setor != setor and
            f.turno() == turno and
            f.turno_id == turno_id and
            dia in f.dias(mes, ano)
        ):
            sobras.append(f)

    return {
        "suprido": suprido,
        "em_servico": em_servico,
        "sobrando": sobras,
        "faltante": funcionario,
        "mensagens": mensagens
    }
def registrar_falta_interface(funcionarios):
    st.subheader("Registrar falta(s) de funcionário(s)")

    nomes_faltantes = st.multiselect("Funcionários faltantes", [f.nome for f in funcionarios])
    data = st.date_input("Data da falta", value=date.today())
    motivo = st.text_area("Motivo da(s) ocorrência(s)")

    if st.button("Registrar falta(s)"):
        for nome in nomes_faltantes:
            registrar_ocorrencia(nome, data, motivo)

        resultados = [verificar_impacto_falta(nome, data, funcionarios) for nome in nomes_faltantes]

        for resultado in resultados:
            if resultado.get("erro"):
                st.error(resultado["erro"])
                continue

            faltante = resultado["faltante"]
            setor = faltante.setor
            turno = faltante.turno()
            turno_id = faltante.turno_id
            dia_str = data.strftime("%d/%b")

            st.markdown(f"### Ocorrência: {faltante.nome} - {setor} ({turno} {turno_id})")

            if resultado["suprido"]:
                st.success("Setor ainda está com o número mínimo de funcionários.")
            else:
                for msg in resultado["mensagens"]:
                    st.warning(msg)

                num_sobrando = len(resultado["sobrando"])
                if num_sobrando > 0:
                    st.info(f"Há {num_sobrando} funcionário(s) disponíveis no mesmo turno e plantão.")

                    with st.expander("Visualizar funcionários disponíveis"):
                        for f in resultado["sobrando"]:
                            setor_real = obter_setor_real(f.nome, data, f.turno(), f.turno_id)
                            setor_txt = f"alocado em: _{setor_real}_" if setor_real else "sem alocação encontrada"
                            pref_txt = f", preferências: {', '.join(f.setores_preferidos)}" if f.setores_preferidos else ""
                            st.markdown(f"- **{f.nome}** — {f.profissao}, {setor_txt}{pref_txt}")
                else:
                    st.error("Nenhum funcionário disponível no mesmo turno. Pode ser necessário hora extra.")

                mensagem = (
                    f"URGENTE: Setor {setor} ({turno} {turno_id}) está abaixo do mínimo.\n"
                    f"Necessário {faltante.profissao.lower()} extra para cobrir falta no dia {dia_str}.\n"
                    "Favor entrar em contato se puder ajudar."
                )

                mensagem_encoded = mensagem.replace(" ", "%20").replace("\n", "%0A")
                url_whatsapp = f"https://wa.me/?text={mensagem_encoded}"

                st.markdown(
                    f"""
                    <a href="{url_whatsapp}" target="_blank">
                        <button style="background-color:#25D366;color:white;padding:10px;border:none;border-radius:5px;cursor:pointer;">
                            Disparar solicitação de hora extra via WhatsApp
                        </button>
                    </a>
                    """,
                    unsafe_allow_html=True
                )


def visualizar_ocorrencias_interface():
    st.subheader("Visualizar ocorrências registradas")

    ano = st.number_input("Ano", min_value=2020, max_value=2100, value=datetime.today().year)
    mes = st.selectbox("Mês", MESES_PT, index=datetime.today().month - 1)
    mes_abrev = datetime(1900, MESES_PT.index(mes)+1, 1).strftime("%b").lower()
    nome_arquivo = f"relatorio_ocorrencias_{mes_abrev}_{ano}.csv"
    caminho_arquivo = os.path.join("ocorrencias", nome_arquivo)

    if os.path.exists(caminho_arquivo):
        df = pd.read_csv(caminho_arquivo)
        st.dataframe(df)
    else:
        st.info(f"Nenhum relatório encontrado para {mes} de {ano}.")

def registrar_falta_planejada_interface(funcionarios):
    st.subheader("Registrar falta planejada")

    nome = st.selectbox("Funcionário", [f.nome for f in funcionarios])
    data = st.date_input("Data da falta planejada", value=date.today())
    tipo = st.selectbox("Tipo de falta", [
        "FA", "FM", "FE", "LP", "F", "LM", "LS", "A"
    ], format_func=lambda x: f"{x} - {TIPOS_FALTA_DESCRICAO.get(x, '')}")

    if st.button("Registrar falta planejada"):
        funcionario = next((f for f in funcionarios if f.nome == nome), None)

        if not funcionario:
            st.error("Funcionário não encontrado.")
            return

        # 1. REGISTRA NO CSV DE FALTAS
        nova_falta = pd.DataFrame([{
            "Nome": nome,
            "Data": data.strftime("%Y-%m-%d"),
            "Tipo": tipo
        }])

        os.makedirs("faltas", exist_ok=True)
        caminho_csv = os.path.join("faltas", "faltas_planejadas.csv")
        if os.path.exists(caminho_csv):
            faltas_existentes = pd.read_csv(caminho_csv)
            df_total = pd.concat([faltas_existentes, nova_falta], ignore_index=True)
        else:
            df_total = nova_falta
        df_total.to_csv(caminho_csv, index=False)

        # 2. REGISTRA NO RELATÓRIO DE OCORRÊNCIAS
        registrar_ocorrencia(nome, data, f"Falta planejada: {tipo}")

        # 3. APLICA A FALTA NA ESCALA (caso possível)
        aplicar_falta_planejada_na_escala(nome, data, tipo)

        # 4. VERIFICA IMPACTO SOMENTE SE SETOR ESTÁ ATIVO NAQUELE DIA
        mes_nome = MESES_PT[data.month - 1]
        ano = data.year
        dia_coluna = f"Dia {data.day}"

        resultado = None
        if os.path.exists("escalas"):
            for nome_arquivo in os.listdir("escalas"):
                if not nome_arquivo.endswith(".csv"):
                    continue
                if mes_nome not in nome_arquivo or str(ano) not in nome_arquivo:
                    continue

                caminho_escala = os.path.join("escalas", nome_arquivo)
                try:
                    df = pd.read_csv(caminho_escala)
                except:
                    continue

                if nome in df["Nome"].values and dia_coluna in df.columns:
                    resultado = verificar_impacto_falta(nome, data, funcionarios)
                    break  # só avalia uma vez

        if resultado:
            if resultado.get("erro"):
                st.error(resultado["erro"])
                return

            setor = resultado["faltante"].setor
            turno = resultado["faltante"].turno()
            turno_id = resultado["faltante"].turno_id
            dia_str = data.strftime("%d/%b")

            st.markdown(f"### Avaliação de impacto da falta - {setor} ({turno} {turno_id})")

            if resultado["suprido"]:
                st.success("Setor ainda está com o número mínimo de funcionários.")
            else:
                for msg in resultado["mensagens"]:
                    st.warning(msg)

                if resultado["sobrando"]:
                    st.info(f"Há {len(resultado['sobrando'])} funcionário(s) disponíveis no mesmo turno e plantão.")

                    with st.expander("Visualizar funcionários disponíveis"):
                        for f in resultado["sobrando"]:
                            setor_real = obter_setor_real(f.nome, data, f.turno(), f.turno_id)
                            setor_txt = f"alocado em: _{setor_real}_" if setor_real else "sem alocação encontrada"
                            pref_txt = f", preferências: {', '.join(f.setores_preferidos)}" if f.setores_preferidos else ""
                            st.markdown(f"- **{f.nome}** — {f.profissao}, {setor_txt}{pref_txt}")

                else:
                    st.error("Nenhum funcionário disponível. Pode ser necessário hora extra.")

                mensagem = (
                    f"URGENTE: Setor {setor} ({turno} {turno_id}) está abaixo do mínimo.\n"
                    f"Necessário {resultado['faltante'].profissao.lower()} extra para cobrir falta no dia {dia_str}.\n"
                    "Favor entrar em contato se puder ajudar."
                )
                mensagem_encoded = mensagem.replace(" ", "%20").replace("\n", "%0A")
                url_whatsapp = f"https://wa.me/?text={mensagem_encoded}"

                st.markdown(
                    f"""
                    <a href="{url_whatsapp}" target="_blank">
                        <button style="background-color:#25D366;color:white;padding:10px;border:none;border-radius:5px;cursor:pointer;">
                            Disparar solicitação de hora extra via WhatsApp
                        </button>
                    </a>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("Falta registrada com sucesso. Nenhuma verificação de impacto foi feita porque o setor não está ativo nesse dia.")


def aplicar_falta_planejada_na_escala(nome, data, tipo):
    mes_nome = MESES_PT[data.month - 1]
    ano = data.year
    dia_coluna = f"Dia {data.day}"

    if not os.path.exists("escalas"):
        return

    for nome_arquivo in os.listdir("escalas"):
        if not nome_arquivo.endswith(".csv"):
            continue
        if mes_nome not in nome_arquivo or str(ano) not in nome_arquivo:
            continue

        caminho_escala = os.path.join("escalas", nome_arquivo)
        try:
            df = pd.read_csv(caminho_escala)
        except:
            continue

        if nome not in df["Nome"].values:
            continue

        if dia_coluna not in df.columns:
            continue

        df[dia_coluna] = df[dia_coluna].astype(str)
        df.loc[df["Nome"] == nome, dia_coluna] = tipo
        df.to_csv(caminho_escala, index=False)
        print(f"Falta planejada aplicada em {nome_arquivo}, dia {data.day}")
        break  # aplicar apenas uma vez


# Dicionário para exibir descrição dos tipos de falta na interface
TIPOS_FALTA_DESCRICAO = {
    "FA": "Falta Abonada",
    "FM": "Folga Mensal",
    "FE": "Folga Eleitoral",
    "LP": "Licença Prêmio",
    "F":  "Férias",
    "LM": "Licença Maternidade",
    "LS": "Licença Saúde",
    "A":  "Aniversário"
}



# Interface Streamlit
st.title("Sistema de Alocação de Funcionários - UPA")

# arquivo = st.file_uploader("Envie o CSV com os funcionários ou use o padrão:", type="csv")

# if arquivo is not None:
#     df_func = pd.read_csv(arquivo)
#     temp_path = "funcionarios_temp.csv"
#     df_func.to_csv(temp_path, index=False)
#     funcionarios = carregar_funcionarios(temp_path)
# else:
#     funcionarios = carregar_funcionarios(CAMINHO_CSV_DEFAULT)

funcionarios = carregar_funcionarios(CAMINHO_CSV_DEFAULT)

st.sidebar.header("Ações")
acao = st.sidebar.radio("Escolha uma ação", [
    "Alocar novas escalas",
    "Visualizar escalas",
    "Adicionar novo funcionário",
    "Visualizar e editar funcionários",
    "Registrar falta ou ocorrência",
    "Registrar faltas planejadas",
    "Visualizar ocorrências"
])


if acao == "Alocar novas escalas":
    rotatividade = st.checkbox("Ativar rotatividade de setores", value=False)
    if rotatividade:
        frequencia = st.number_input("Rotacionar a cada quantos meses?", min_value=1, step=1, value=1)
    else:
        frequencia = 1

    mes = st.number_input("Mês inicial (1-12)", min_value=1, max_value=12, value=datetime.now().month)
    ano = st.number_input("Ano", min_value=2024, step=1, value=datetime.now().year)
    meses_gerar = st.number_input("Gerar escala para quantos meses?", min_value=1, max_value=12, step=1, value=1)

    if st.button("Gerar Escala"):
        arquivos_gerados = alocar_escala(
            funcionarios,
            rotatividade=rotatividade,
            frequencia_rotatividade=frequencia,
            mes_atual=mes,
            gerar_para_meses=meses_gerar,
            ano_atual=ano
        )
        st.session_state["escalas"] = arquivos_gerados
        st.success("Escalas geradas com sucesso!")

elif acao == "Visualizar escalas":
    escalas_path = "escalas"
    arquivos_gerados = []

    if os.path.exists(escalas_path):
        for nome_arquivo in sorted(os.listdir(escalas_path)):
            if nome_arquivo.endswith(".csv"):
                caminho = os.path.join(escalas_path, nome_arquivo)
                try:
                    df = pd.read_csv(caminho)
                    nome = nome_arquivo.replace("_", " ").replace(".csv", "").replace("-", "/")
                    arquivos_gerados.append((nome, caminho, df))
                except Exception as e:
                    st.warning(f"Erro ao carregar {nome_arquivo}: {e}")

    if arquivos_gerados:
        setores_disponiveis = sorted(set(nome.split(" (" )[0] for nome, _, _ in arquivos_gerados))
        turnos_disponiveis = sorted(set(nome.split("(")[1].split(")")[0] for nome, _, _ in arquivos_gerados))

        setor_filtro = st.selectbox("Filtrar por setor", ["Todos"] + setores_disponiveis)
        turno_filtro = st.selectbox("Filtrar por turno", ["Todos"] + turnos_disponiveis)

        for nome, caminho, df in arquivos_gerados:
            setor_nome = nome.split(" (" )[0]
            turno_nome = nome.split("(")[1].split(")")[0]

            if (setor_filtro == "Todos" or setor_filtro == setor_nome) and (turno_filtro == "Todos" or turno_filtro == turno_nome):
                with st.expander(nome):
                    st.dataframe(df)
    else:
        st.info("Nenhuma escala encontrada na pasta 'escalas'.")


elif acao == "Adicionar novo funcionário":
    adicionar_funcionario_interface()

elif acao == "Visualizar e editar funcionários":
    st.subheader("Visualizar e editar funcionários")
    try:
        df = pd.read_csv(CAMINHO_CSV_DEFAULT)
        termo_busca = st.text_input("Buscar por nome ou COREN-SP")
        df_filtrado = df[df["Nome"].str.contains(termo_busca, case=False) | df["COREN-SP"].astype(str).str.contains(termo_busca)] if termo_busca else df

        setores_possiveis = [
            "Classificação de risco", "Sala de emergência", "Sala de medicação",
            "Sala de sutura e CME", "Repouso/observação", "Setor de observação/repouso"
        ]

        for i in range(len(df_filtrado)):
            idx_original = df_filtrado.index[i]
            with st.expander(f"{df_filtrado.iloc[i]['Nome']} - {df_filtrado.iloc[i]['Função']}"):
                st.markdown(f"**Nome:** {df_filtrado.iloc[i]['Nome']}")
                st.markdown(f"**COREN-SP:** {df_filtrado.iloc[i]['COREN-SP']}")
                st.markdown(f"**Função:** {df_filtrado.iloc[i]['Função']}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    novo_horario = st.selectbox("Horário", ["07x19", "19x07"], index=["07x19", "19x07"].index(df_filtrado.iloc[i]['Horário']), key=f"horario_{i}")
                with col2:
                    novo_setor = st.selectbox("Setor", setores_possiveis, index=setores_possiveis.index(df_filtrado.iloc[i]['Setor']), key=f"setor_{i}")
                with col3:
                    novo_plantao = st.selectbox("Plantão", ["A", "B"], index=["A", "B"].index(df_filtrado.iloc[i]['Plantão']), key=f"plantao_{i}")

                setores_pref_atuais = [s.strip() for s in str(df_filtrado.iloc[i].get("Setores Preferidos", "")).split(",") if s.strip() in setores_possiveis and s.strip() != novo_setor]
                novos_preferidos = st.multiselect("Setores preferidos (opcional)", options=[s for s in setores_possiveis if s != novo_setor], default=setores_pref_atuais, key=f"preferidos_{i}")

                if st.button("Salvar Alterações", key=f"salvar_{i}"):
                    df.at[idx_original, "Horário"] = novo_horario
                    df.at[idx_original, "Setor"] = novo_setor
                    df.at[idx_original, "Plantão"] = novo_plantao
                    df.at[idx_original, "Setores Preferidos"] = ", ".join(novos_preferidos)
                    df.to_csv(CAMINHO_CSV_DEFAULT, index=False)
                    st.success("Alterações salvas com sucesso.")

                if st.button("Excluir Funcionário", key=f"excluir_{i}"):
                    df = df.drop(index=idx_original).reset_index(drop=True)
                    df.to_csv(CAMINHO_CSV_DEFAULT, index=False)
                    st.success("Funcionário excluído com sucesso.")
                    st.experimental_rerun()
    except Exception as e:
        st.error(f"Erro ao carregar funcionários: {e}")

elif acao == "Registrar falta ou ocorrência":
    registrar_falta_interface(funcionarios)

elif acao == "Registrar faltas planejadas":
    registrar_falta_planejada_interface(funcionarios)

elif acao == "Visualizar ocorrências":
    visualizar_ocorrencias_interface()
