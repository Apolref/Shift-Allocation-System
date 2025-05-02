import pandas as pd
import os
import streamlit as st
import random
import signal
from datetime import datetime
from calendar import monthrange

# Caminho padrão para o CSV com os dados dos funcionários
CAMINHO_CSV_DEFAULT = r"C:\\Users\\alelo\\OneDrive\\Documentos\\USP\\TCC\\Projeto\\funcionarios_upa.csv"

# Lista de meses em português
MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

class Funcionario:
    def __init__(self, nome, coren, profissao, horario, setor, turno_id, setores_preferidos=None):
        self.nome = nome
        self.coren = coren
        self.profissao = profissao
        self.horario = horario
        self.setor = setor
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


def alocar_escala(funcionarios, rotatividade=False, frequencia_rotatividade=1, mes_atual=None, gerar_para_meses=1, ano_atual=None):
    setores_possiveis = [
        "Classificação de risco", "Sala de emergência", "Sala de medicação",
        "Sala de sutura e CME", "Repouso/observação", "Setor de observação/repouso"
    ]

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

        setores = {}
        for f in funcionarios:
            setor_atual = f.setor
            if aplicar_rotatividade:
                if f.setores_preferidos:
                    setores_compatíveis = [s for s in f.setores_preferidos if s != setor_atual and s in setores_possiveis]
                    if not setores_compatíveis:
                        setores_compatíveis = [s for s in setores_possiveis if s != setor_atual]
                else:
                    setores_compatíveis = [s for s in setores_possiveis if s != setor_atual]
                if setores_compatíveis:
                    f.setor = random.choice(setores_compatíveis)


            chave = f"{f.setor} ({f.turno()} {f.turno_id})"
            if chave not in setores:
                setores[chave] = []
            linha = f.to_dict()
            linha["Mês"] = f"{nome_mes} de {ano}"
            marca = "D" if f.turno() == "Diurno" else "N"
            for dia in f.dias(mes, ano):
                linha[f"Dia {dia}"] = marca
            setores[chave].append(linha)

        os.makedirs("escalas", exist_ok=True)
        for setor_turno, lista in setores.items():
            df = pd.DataFrame(lista)
            nome_arquivo = f"{setor_turno.replace(' ', '_').replace('/', '-')}_{nome_mes}_{ano}.csv"
            caminho_completo = os.path.join("escalas", nome_arquivo)
            df.to_csv(caminho_completo, index=False, mode ='w')
            resultados.append((f"{setor_turno} - {nome_mes} de {ano}", caminho_completo, df))

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


# Interface Streamlit
st.title("Sistema de Alocação de Funcionários - UPA")

arquivo = st.file_uploader("Envie o CSV com os funcionários ou use o padrão:", type="csv")

if arquivo is not None:
    df_func = pd.read_csv(arquivo)
    temp_path = "funcionarios_temp.csv"
    df_func.to_csv(temp_path, index=False)
    funcionarios = carregar_funcionarios(temp_path)
else:
    funcionarios = carregar_funcionarios(CAMINHO_CSV_DEFAULT)

st.sidebar.header("Ações")
if st.sidebar.button("Encerrar servidor Streamlit", help="Fecha este app imediatamente"):
    st.write("Encerrando servidor...")
    os.kill(os.getpid(), signal.SIGTERM)
acao = st.sidebar.radio("Escolha uma ação", [
    "Alocar novas escalas",
    "Visualizar escalas",
    "Adicionar novo funcionário",
    "Visualizar e editar funcionários"
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
