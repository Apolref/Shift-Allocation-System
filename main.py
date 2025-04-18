# Importação das bibliotecas necessárias
import pandas as pd  # manipulação de dados
import os  # manipulação de diretórios e arquivos
import streamlit as st  # interface web
import random  # sorteio aleatório de setores (rotatividade)
from datetime import datetime  # data e hora atuais

# Caminho padrão do CSV com os dados dos funcionários
CAMINHO_CSV_DEFAULT = r"C:\\Users\\alelo\\OneDrive\\Documentos\\USP\\TCC\\Projeto\\funcionarios_upa.csv"

# Classe que representa um funcionário da UPA
class Funcionario:
    def __init__(self, nome, coren, profissao, horario, setor, turno_id):
        self.nome = nome
        self.coren = coren
        self.profissao = profissao
        self.horario = horario
        self.setor = setor
        self.turno_id = turno_id

    # Determina o tipo de turno com base no horário
    def turno(self):
        return "Diurno" if "07x" in self.horario else "Noturno"

    # Retorna a lista de dias do mês com base no tipo de plantão
    def dias(self):
        return list(range(1, 31, 2)) if self.turno_id == "A" else list(range(2, 32, 2))

    # Converte o objeto Funcionario em dicionário (linha de tabela)
    def to_dict(self):
        entrada, saida = self.horario.split("x")
        return {
            "Nome": self.nome,
            "Função": self.profissao,
            "COREN-SP": self.coren,
            "Turno": self.turno(),
            "Horário": f"{entrada}x{saida}",
            "Plantão": self.turno_id,
            "Setor": self.setor
        }

# Lê os dados do CSV e retorna a lista de funcionários como objetos
def carregar_funcionarios(csv_path):
    df = pd.read_csv(csv_path)
    funcionarios = []
    for _, row in df.iterrows():
        funcionarios.append(Funcionario(
            nome=row["Nome"],
            coren=row["COREN-SP"],
            profissao=row["Função"],
            horario=row["Horário"],
            setor=row["Setor"],
            turno_id=row["Plantão"]
        ))
    return funcionarios

# Função para gerar as escalas dos funcionários
def alocar_escala(funcionarios, rotatividade=False, frequencia_rotatividade=1, mes_atual=None, gerar_para_meses=1):
    # Setores possíveis onde os funcionários podem ser alocados
    setores_possiveis = [
        "Classificação de risco", "Sala de emergência", "Sala de medicação",
        "Sala de sutura e CME", "Repouso/observação", "Setor de observação/repouso"
    ]

    if mes_atual is None:
        mes_atual = datetime.now().month

    resultados = []

    # Loop sobre os meses desejados
    for m in range(mes_atual, mes_atual + gerar_para_meses):
        mes = ((m - 1) % 12) + 1
        aplicar_rotatividade = rotatividade and (mes % frequencia_rotatividade == 0)

        setores = {}
        for f in funcionarios:
            setor_atual = f.setor
            # Rotatividade de setor
            if aplicar_rotatividade:
                setores_compatíveis = [s for s in setores_possiveis if s != setor_atual]
                if setores_compatíveis:
                    f.setor = random.choice(setores_compatíveis)

            # Chave por setor e turno
            chave = f"{f.setor} ({f.turno()} {f.turno_id})"
            if chave not in setores:
                setores[chave] = []

            linha = f.to_dict()
            linha["Mês"] = mes  # para identificar o mês na planilha
            marca = "D" if f.turno() == "Diurno" else "N"
            for dia in f.dias():
                linha[f"Dia {dia}"] = marca

            setores[chave].append(linha)

        # Geração das planilhas em CSV
        os.makedirs("escalas", exist_ok=True)
        for setor_turno, lista in setores.items():
            df = pd.DataFrame(lista)
            nome_arquivo = f"{setor_turno.replace(' ', '_').replace('/', '-')}_Mes_{mes}.csv"
            caminho_completo = os.path.join("escalas", nome_arquivo)
            df.to_csv(caminho_completo, index=False)
            resultados.append((f"{setor_turno} - Mês {mes}", caminho_completo, df))

    return resultados

# Interface do Streamlit para adicionar funcionário manualmente
def adicionar_funcionario_interface():
    st.subheader("Adicionar novo funcionário")
    with st.form("form_funcionario"):
        # Campos do formulário
        nome = st.text_input("Nome completo")
        coren = st.text_input("Número do COREN-SP")
        profissao = st.selectbox("Profissão", ["Enfermeiro", "Técnico de enfermagem", "Auxiliar de enfermagem"])
        horario = st.selectbox("Horário de trabalho", ["07x19", "19x07"])
        setor = st.selectbox("Setor", [
            "Classificação de risco", "Sala de emergência", "Sala de medicação",
            "Sala de sutura e CME", "Repouso/observação", "Setor de observação/repouso"
        ])
        turno_id = st.selectbox("Plantão (A para dias ímpares, B para dias pares)", ["A", "B"])
        submitted = st.form_submit_button("Adicionar")

        # Adição no CSV ao enviar o formulário
        if submitted:
            novo_funcionario = {
                "Nome": nome,
                "COREN-SP": coren,
                "Função": profissao,
                "Horário": horario,
                "Setor": setor,
                "Plantão": turno_id
            }
            try:
                df = pd.read_csv(CAMINHO_CSV_DEFAULT)
                df = pd.concat([df, pd.DataFrame([novo_funcionario])], ignore_index=True)
                df.to_csv(CAMINHO_CSV_DEFAULT, index=False)
                st.success("Funcionário adicionado com sucesso!")
            except Exception as e:
                st.error(f"Erro ao adicionar funcionário: {e}")

# Início da interface com Streamlit
st.title("Sistema de Alocação de Funcionários - UPA")

# Upload opcional de um novo CSV
arquivo = st.file_uploader("Envie o CSV com os funcionários ou use o padrão:", type="csv")

# Carrega os funcionários com base no CSV
if arquivo is not None:
    df_func = pd.read_csv(arquivo)
    temp_path = "funcionarios_temp.csv"
    df_func.to_csv(temp_path, index=False)
    funcionarios = carregar_funcionarios(temp_path)
else:
    funcionarios = carregar_funcionarios(CAMINHO_CSV_DEFAULT)

# Menu lateral com opções
st.sidebar.header("Ações")
acao = st.sidebar.radio("Escolha uma ação", ["Visualizar Escalas", "Adicionar Funcionário"])

# Opção: Visualização/Geração de Escalas
if acao == "Visualizar Escalas":
    rotatividade = st.checkbox("Ativar rotatividade de setores", value=False)
    if rotatividade:
        frequencia = st.number_input("Rotacionar a cada quantos meses?", min_value=1, step=1, value=1)
    else:
        frequencia = 1

    mes = st.number_input("Mês inicial (1-12)", min_value=1, max_value=12, value=datetime.now().month)
    meses_gerar = st.number_input("Gerar escala para quantos meses?", min_value=1, max_value=12, step=1, value=1)

    if st.button("Gerar Escala"):
        arquivos_gerados = alocar_escala(
            funcionarios,
            rotatividade=rotatividade,
            frequencia_rotatividade=frequencia,
            mes_atual=mes,
            gerar_para_meses=meses_gerar
        )
        st.success("Escalas geradas com sucesso!")
        for nome, caminho, df in arquivos_gerados:
            st.subheader(nome)
            st.dataframe(df.head())

# Opção: Adição de Funcionário
elif acao == "Adicionar Funcionário":
    adicionar_funcionario_interface()
