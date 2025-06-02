import pandas as pd
import os
import streamlit as st
import random
import unicodedata
import calendar
import random
from datetime import datetime, date
from calendar import monthrange
from io import BytesIO
from openpyxl.drawing.image import Image

import locale
locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')  # Exibe os meses em português

from openpyxl.drawing.image import Image
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

CAMINHO_CSV_DEFAULT = r"C:\\Users\\alelo\\OneDrive\\Documentos\\USP\\TCC\\Projeto\\funcionarios_upa.csv"

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

MESES_PT_ABREV = {
    "jan": "Janeiro", "fev": "Fevereiro", "mar": "Março", "abr": "Abril",
    "mai": "Maio", "jun": "Junho", "jul": "Julho", "ago": "Agosto",
    "set": "Setembro", "out": "Outubro", "nov": "Novembro", "dez": "Dezembro"
}

REGRAS_SETOR = {
    "Sala de emergência": {"min_total": 6, "min_enfermeiros": 1},
    "Sala de sutura e CME": {"min_total": 2, "min_enfermeiros": 0},
    "Sala de medicação": {"min_total": 6, "min_enfermeiros": 1},
    "Classificação de risco": {"min_total": 2, "min_enfermeiros": 2},
    "Repouso/observação": {"min_total": 6, "min_enfermeiros": 1}
}

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


class Funcionario:
    def __init__(self, nome, coren, profissao, horario, setor, turno_id, setores_preferidos=None):
        self.nome = nome
        self.coren = coren
        self.profissao = profissao
        self.horario = horario
        self.setor = setor if setor != "Setor de observação/repouso" else "Repouso/observação"
        self.turno_id = turno_id
        self.setores_preferidos = setores_preferidos or []

        # Detecta tipo especial de função
        self.is_supervisor = (self.profissao == "Supervisor Técnico")
        self.is_responsavel = (self.profissao == "Responsável Técnico")

    def turno(self):
        # Supervisor é sempre Diurno, o restante segue horário
        if self.is_supervisor:
            return "Diurno"
        return "Diurno" if "07x" in self.horario or "07:30" in self.horario else "Noturno"

    def dias(self, mes_atual, ano_atual):
        _, ultimo_dia_mes = monthrange(ano_atual, mes_atual)

        if self.is_supervisor:
            return list(range(1, ultimo_dia_mes + 1))

        if mes_atual == 1:
            mes_anterior = 12
            ano_anterior = ano_atual - 1
        else:
            mes_anterior = mes_atual - 1
            ano_anterior = ano_atual

        ultimo_anterior = monthrange(ano_anterior, mes_anterior)[1]

        if ultimo_anterior % 2 == 1:
            dias = list(range(2, ultimo_dia_mes + 1, 2)) if self.turno_id == "A" else list(range(1, ultimo_dia_mes + 1, 2))
        else:
            dias = list(range(1, ultimo_dia_mes + 1, 2)) if self.turno_id == "A" else list(range(2, ultimo_dia_mes + 1, 2))

        return dias

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
        dia = int(data.split("-")[2])  # formato YYYY-MM-DD
    except Exception as e:
        return {"suprido": False, "mensagem": f"Erro ao interpretar a data: {e}"}

    # Filtra por setor e remove faltante
    df_setor = df_funcionarios[df_funcionarios["Setor"] == setor_afetado]
    df_setor = df_setor[df_setor["Nome"] != nome_faltante]

    # REMOVE supervisores e responsáveis das contagens
    df_contaveis = df_setor[~df_setor["Função"].isin(["Responsável Técnico", "Supervisor Técnico"])]

    total_restante = len(df_contaveis)
    enfermeiros_restantes = len(df_contaveis[df_contaveis["Função"] == "Enfermeiro"])

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
    # Só aloca para os setores definidos nas regras
    setores_alocados = {s: [] for s in REGRAS_SETOR.keys()}

    # Ignora supervisores: eles serão tratados separadamente em alocar_escala
    funcionarios_turno = [
        f for f in funcionarios
        if f.turno() == turno and f.turno_id == turno_id and f.profissao != "Supervisor Técnico"
    ]
    random.shuffle(funcionarios_turno)

    utilizados = set()

    # Aloca diretamente os Responsáveis Técnicos no setor clínico correto
    for f in funcionarios_turno:
        if getattr(f, "is_responsavel", False):
            if f.setor in setores_alocados:
                setores_alocados[f.setor].append(f)
                utilizados.add(f)

    # Etapa 1: alocar o mínimo necessário por setor
    for setor, regras in REGRAS_SETOR.items():
        candidatos = [
            f for f in funcionarios_turno
            if f not in utilizados and (not f.setores_preferidos or setor in f.setores_preferidos)
        ]

        enfermeiros = [f for f in candidatos if f.profissao == "Enfermeiro"]
        outros = [f for f in candidatos if f.profissao not in ["Enfermeiro", "Responsável Técnico", "Supervisor Técnico"]]

        alocados = []

        while len(alocados) < regras["min_total"]:
            if len(alocados) < regras["min_enfermeiros"]:
                if enfermeiros:
                    f = enfermeiros.pop()
                else:
                    break
            else:
                if outros:
                    f = outros.pop()
                elif enfermeiros:
                    f = enfermeiros.pop()
                else:
                    break
            alocados.append(f)
            utilizados.add(f)

        setores_alocados[setor].extend(alocados)

    # Etapa 2: distribuir funcionários restantes entre setores
    nao_alocados = [
        f for f in funcionarios_turno
        if f not in utilizados and not getattr(f, "is_responsavel", False)
    ]
    setores = list(REGRAS_SETOR.keys())
    i = 0

    while nao_alocados:
        f = nao_alocados.pop()
        setor_destino = None
        for pref in f.setores_preferidos:
            if pref in setores:
                setor_destino = pref
                break
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

        ultimo_dia_mes = monthrange(ano, mes)[1]  # <-- dias reais do mês

        for turno in ["Diurno", "Noturno"]:
            for turno_id in ["A", "B"]:
                setores = distribuir_com_regras(funcionarios, turno, turno_id)

                rts_validos = [
                    f for f in funcionarios
                    if getattr(f, "is_responsavel", False)
                    and f.turno() == turno
                    and f.turno_id == turno_id
                ]
                supervisores_validos = [
                    f for f in funcionarios
                    if getattr(f, "is_supervisor", False)
                ]

                # Corrigido: calcula os dias reais de acordo com o plantão
                dias_validos = list(range(1, ultimo_dia_mes + 1, 2)) if turno_id == "A" else list(range(2, ultimo_dia_mes + 1, 2))

                os.makedirs("escalas", exist_ok=True)
                for setor, lista in setores.items():
                    if setor not in REGRAS_SETOR:
                        continue

                    dados = []

                    for f in lista:
                        if aplicar_rotatividade and not getattr(f, "is_supervisor", False) and not getattr(f, "is_responsavel", False):
                            setor_compat = [s for s in f.setores_preferidos if s != f.setor and s in REGRAS_SETOR]
                            if setor_compat:
                                f.setor = random.choice(setor_compat)

                        f.setor = setor
                        linha = f.to_dict()
                        linha["Mês"] = f"{nome_mes} de {ano}"
                        marca = "D" if f.turno() == "Diurno" else "N"
                        for dia in f.dias(mes, ano):
                            if dia in dias_validos:
                                linha[f"Dia {dia}"] = marca
                        dados.append(linha)

                    # Evita duplicatas
                    nomes_na_escala = set([linha["Nome"] for linha in dados])

                    for sup in supervisores_validos:
                        if sup.nome in nomes_na_escala:
                            continue
                        sup.setor = setor
                        linha = sup.to_dict()
                        linha["Mês"] = f"{nome_mes} de {ano}"
                        marca = "D" if sup.turno() == "Diurno" else "N"
                        for dia in sup.dias(mes, ano):
                            if dia in dias_validos:
                                linha[f"Dia {dia}"] = marca
                        dados.append(linha)
                        nomes_na_escala.add(sup.nome)

                    for rt in rts_validos:
                        if rt.nome in nomes_na_escala:
                            continue
                        rt.setor = setor
                        linha = rt.to_dict()
                        linha["Mês"] = f"{nome_mes} de {ano}"
                        marca = "D" if rt.turno() == "Diurno" else "N"
                        for dia in rt.dias(mes, ano):
                            if dia in dias_validos:
                                linha[f"Dia {dia}"] = marca
                        dados.append(linha)
                        nomes_na_escala.add(rt.nome)

                    if dados:
                        df = pd.DataFrame(dados)

                        # Ordena: Supervisor Técnico → Responsável Técnico → Demais
                        def prioridade(row):
                            if row["Função"] == "Supervisor Técnico":
                                return 0
                            elif row["Função"] == "Responsável Técnico":
                                return 1
                            else:
                                return 2

                        df["__ordem"] = df.apply(prioridade, axis=1)
                        df = df.sort_values(by="__ordem").drop(columns="__ordem")

                        nome_arquivo = f"{setor.replace(' ', '_').replace('/', '-')}_({turno} {turno_id})_{nome_mes}_{ano}.csv"
                        caminho_completo = os.path.join("escalas", nome_arquivo)
                        df.to_csv(caminho_completo, index=False)
                        resultados.append((f"{setor} ({turno} {turno_id}) - {nome_mes} de {ano}", caminho_completo, df))

    return resultados

def adicionar_funcionario_interface():
    st.subheader("Adicionar novo funcionário")

    setores_possiveis = [
        "Classificação de risco", "Sala de emergência", "Sala de medicação",
        "Sala de sutura e CME", "Repouso/observação"
    ]

    with st.form("form_funcionario"):
        nome = st.text_input("Nome completo")
        coren = st.text_input("Número do COREN-SP")
        profissao = st.selectbox("Profissão", [
            "Enfermeiro", "Técnico de enfermagem", "Auxiliar de enfermagem",
            "Supervisor Técnico", "Responsável Técnico"
        ])
        horario = st.selectbox("Horário de trabalho", ["07x19", "19x07", "07:30x16:30"])
        turno_id = st.selectbox("Plantão (A para dias ímpares, B para dias pares)", ["A", "B"])

        setores_preferidos = st.multiselect(
            "Setores preferidos (mínimo 1)",
            options=setores_possiveis,
            help="Selecione ao menos um setor em que esse funcionário possa trabalhar"
        )

        submitted = st.form_submit_button("Adicionar")
        if submitted:
            if not setores_preferidos:
                st.warning("❗ Você deve selecionar pelo menos um setor preferido.")
                return

            # sorteia aleatoriamente o setor principal a partir dos preferidos
            setor_principal = random.choice(setores_preferidos)

            novo = {
                "Nome": nome,
                "COREN-SP": coren,
                "Função": profissao,
                "Horário": horario,
                "Setor": setor_principal,
                "Plantão": turno_id,
                "Setores Preferidos": ", ".join(setores_preferidos)
            }

            try:
                df = pd.read_csv(CAMINHO_CSV_DEFAULT)
                df = pd.concat([df, pd.DataFrame([novo])], ignore_index=True)
                df.to_csv(CAMINHO_CSV_DEFAULT, index=False)
                st.success(f"Funcionário adicionado com sucesso! Setor atribuído: {setor_principal}")
            except Exception as e:
                st.error(f"Erro ao adicionar funcionário: {e}")


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

    funcionario = next((f for f in funcionarios if f.nome == nome_faltante), None)
    if not funcionario:
        return {"erro": "Funcionário não encontrado."}

    setor = funcionario.setor
    turno = funcionario.turno()
    turno_id = funcionario.turno_id

    em_servico = [
        f for f in funcionarios
        if f.setor == setor
        and f.turno() == turno
        and f.turno_id == turno_id
        and dia in f.dias(mes, ano)
        and f.nome != nome_faltante
    ]

    # REMOVE supervisores e responsáveis
    em_servico_validos = [
        f for f in em_servico if f.profissao not in ["Supervisor Técnico", "Responsável Técnico"]
    ]

    total_em_servico = len(em_servico_validos)
    total_enfermeiros = sum(1 for f in em_servico_validos if f.profissao == "Enfermeiro")

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

    sobrando = [
        f for f in funcionarios
        if f.setor != setor
        and f.turno() == turno
        and f.turno_id == turno_id
        and dia in f.dias(mes, ano)
        and f.profissao not in ["Supervisor Técnico", "Responsável Técnico"]
    ]

    return {
        "suprido": suprido,
        "em_servico": em_servico,
        "sobrando": sobrando,
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

def exportar_ocorrencias_excel(df):
    df_ordenado = df.sort_values(by="Data")
    dias_unicos = sorted(df_ordenado["Data"].dt.day.unique())
    mes_ano = df_ordenado["Data"].dt.strftime("%B %Y").iloc[0].capitalize()

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_ordenado.to_excel(writer, sheet_name='Ocorrências', startrow=3, index=False)

        workbook = writer.book
        worksheet = writer.sheets['Ocorrências']

        titulo = f"Ocorrências Diárias - {mes_ano} ({' - '.join(map(str, dias_unicos))})"
        worksheet.merge_range('A1:C1', titulo, workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_size': 14
        }))

        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1})
        for col_num, value in enumerate(df_ordenado.columns):
            worksheet.write(3, col_num, value, header_format)

        for i, col in enumerate(df_ordenado.columns):
            max_len = df_ordenado[col].astype(str).map(len).max()
            worksheet.set_column(i, i, max(max_len + 2, len(col) + 2))

    output.seek(0)
    return output

def exportar_escala_para_excel(setor, df, mes, ano, turno_id):

    wb = Workbook()
    ws = wb.active
    ws.title = setor[:31]

    # ——— 0) INSERIR IMAGENS —————————————————————————————————
    # Brasão na coluna A
    brasao = Image("imagens/itanhaem.jpg")
    brasao.width, brasao.height = 100, 100
    ws.add_image(brasao, "A1")

    # Logo UPA na coluna N (ou na última que você quiser)
    upa_logo = Image("imagens/upa.png")
    upa_logo.width, upa_logo.height = 150, 80
    ws.add_image(upa_logo, "N1")
    # ————————————————————————————————————————————————————

    thin        = Side(border_style="thin", color="000000")
    border      = Border(top=thin, bottom=thin, left=thin, right=thin)
    font_header = Font(name="Calibri", size=11, bold=True)
    font_title  = Font(name="Calibri", size=12, bold=True, italic=True)
    align_center= Alignment(horizontal="center", vertical="center")
    align_left  = Alignment(horizontal="left",   vertical="center")
    fill_gray   = PatternFill(fill_type="solid", fgColor="D8D8D8")

    # 1–4) Cabeçalho institucional: agora mesclamos de B até M, não de A até L
    for row, text in [
        (1, "PREFEITURA MUNICIPAL DA ESTÂNCIA BALNEÁRIA DE ITANHAÉM"),
        (2, "Secretaria Municipal de Saúde"),
        (3, "UPA – Antônio Maria Marques de Oliveira")
    ]:
        ws.merge_cells(f"B{row}:M{row}")
        c = ws[f"B{row}"]
        c.value     = text
        c.font      = font_header
        c.alignment = align_center

    # Linha 4: título do período
    data_inicio = 1 if turno_id=="A" else 2
    ultimo      = monthrange(ano, mes)[1]
    data_fim    = (
        ultimo
        if (data_inicio==1 and ultimo%2==1) or (data_inicio==2 and ultimo%2==0)
        else ultimo-1
    )
    titulo = f"ESCALA DE SERVIÇO … MÊS {data_inicio:02d}/{mes:02d}/{ano} A {data_fim:02d}/{mes:02d}/{ano}"
    ws.merge_cells("B4:M4")
    c = ws["B4"]
    c.value     = titulo
    c.font      = font_header
    c.alignment = align_center

    # Linha 6: subtítulo do setor
    ws.merge_cells("B6:F6")
    c = ws["B6"]
    c.value     = f"{setor} ({turno_id})"
    c.font      = font_title
    c.alignment = align_center
    for col in range(2, 7):
        cell = ws.cell(row=6, column=col)
        cell.fill   = fill_gray
        cell.border = border

    # Linhas 7–8: cabeçalho de colunas
    base_cols = ["Funcionário", "Função", "Coren sp", "Horário"]
    for idx, header in enumerate(base_cols, start=1):
        ws.merge_cells(start_row=7, start_column=idx, end_row=8, end_column=idx)
        cell = ws.cell(row=7, column=idx, value=header)
        cell.font      = font_header
        cell.alignment = align_center
        cell.border    = border

    # Dias
    dias = sorted(int(c.split()[1]) for c in df.columns if c.startswith("Dia "))
    for j, dia in enumerate(dias, start=len(base_cols) + 1):
        wd = calendar.day_abbr[date(ano, mes, dia).weekday()][0].upper()
        ncell = ws.cell(row=7, column=j, value=dia)
        wcell = ws.cell(row=8, column=j, value=wd)
        for cell in (ncell, wcell):
            cell.font      = font_header
            cell.alignment = align_center
            cell.border    = border

    # Preenche fundo cinza nas linhas 7 e 8
    total_cols = len(base_cols) + len(dias)
    for row in (7, 8):
        for col in range(1, total_cols + 1):
            ws.cell(row=row, column=col).fill = fill_gray

    # Dados a partir da linha 9
    for i, (_, row) in enumerate(df.iterrows(), start=9):
        ws.cell(row=i, column=1, value=row["Nome"]   ).alignment = align_left
        ws.cell(row=i, column=2, value=row["Função"] ).alignment = align_center
        ws.cell(row=i, column=3, value=row["COREN-SP"]).alignment = align_center
        ws.cell(row=i, column=4, value=row["Horário"]).alignment = align_center
        for c in range(1, len(base_cols) + 1):
            ws.cell(row=i, column=c).border = border
        for j, dia in enumerate(dias, start=len(base_cols) + 1):
            cell = ws.cell(row=i, column=j, value=row.get(f"Dia {dia}", ""))
            cell.alignment = align_center
            cell.border    = border

    # Legenda abaixo
    ultima = 9 + len(df)
    legenda = (
        "*FA:Falta Abonada *FM:Folga Mensal *FE:Folga Eleitoral *LP:Licença Prêmio "
        "*F:Férias *LM:Licença Maternidade *LS:Licença Saúde *D:Diurno *N:Noturno *A:Aniversário"
    )
    ws.merge_cells(start_row=ultima, start_column=1, end_row=ultima, end_column=total_cols)
    lcell = ws.cell(row=ultima, column=1, value=legenda)
    lcell.font      = Font(name="Calibri", size=9, italic=True)
    lcell.alignment = Alignment(horizontal="left", vertical="center")

    # Ajuste de colunas, com limite na coluna Função (B)
    for col in range(1, total_cols + 1):
        letter = get_column_letter(col)
        max_len = max(len(str(c.value or "")) for c in ws[letter])
        width = max_len + 2
        if col == 1:
            width = min(width, 25)     # mantém A no máximo 25
        if col == 2:
            width = min(width, 20)     # FUNÇÃO no máximo 20
        ws.column_dimensions[letter].width = width

    # Retorna em buffer
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def remover_acentos(txt):
    return ''.join(c for c in unicodedata.normalize('NFD', txt)
                   if unicodedata.category(c) != 'Mn')

def visualizar_ocorrencias_interface():
    st.subheader("Visualizar ocorrências registradas")

    ano = st.number_input("Ano", min_value=2020, max_value=2100,
                         value=datetime.today().year)
    mes = st.selectbox("Mês", MESES_PT, index=datetime.today().month - 1)

    # Abreviação para nome de arquivo
    mes_abrev = datetime(1900, MESES_PT.index(mes) + 1, 1)\
                   .strftime("%b").lower()
    nome_arquivo = f"relatorio_ocorrencias_{mes_abrev}_{ano}.csv"
    caminho_arquivo = os.path.join("ocorrencias", nome_arquivo)

    if not os.path.exists(caminho_arquivo):
        st.warning(f"Nenhum relatório encontrado para {mes} de {ano}.")
        return

    try:
        df = pd.read_csv(caminho_arquivo)
        st.dataframe(df)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return

    if st.button("Exportar para Excel (modelo de relatório)"):
        try:
            # extrai dias únicos para o título e agrupamento
            datas = df["Data"].astype(str)
            dias = sorted({int(d.split("/")[0]) for d in datas})
            primeiro, ultimo = dias[0], dias[-1]
            titulo = f"Ocorrências Diárias - {mes} {ano} ({primeiro} ~ {ultimo})"

            # cria workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Ocorrências"

            # estilos
            thin = Side(border_style="thin", color="000000")
            borda = Border(left=thin, right=thin, top=thin, bottom=thin)
            font_normal = Font(name="Times New Roman", size=11)
            font_bold   = Font(name="Times New Roman", size=11, bold=True)
            font_titulo = Font(name="Times New Roman", size=14, bold=True)
            alin_center = Alignment(horizontal="center", vertical="center")
            alin_left   = Alignment(horizontal="left",   vertical="center")

            # título mesclado B1:D1
            ws.merge_cells("B1:D1")
            c = ws["B1"]
            c.value = titulo
            c.font = font_titulo
            c.alignment = alin_center

            # cabeçalhos na linha 2
            headers = ["Nome", "Data", "Motivo da Ocorrência"]
            for col_idx, h in enumerate(headers, start=2):
                cell = ws.cell(row=2, column=col_idx, value=h)
                cell.font = font_bold
                cell.alignment = alin_center
                cell.border = borda

            # dados a partir da linha 3
            row_out = 3
            for dia in dias:
                grupo = df[datas.str.startswith(f"{dia}/")]
                for _, r in grupo.iterrows():
                    # Nome (à esquerda)
                    nome_cell = ws.cell(row=row_out, column=2, value=r["Nome"])
                    nome_cell.font      = font_normal
                    nome_cell.alignment = alin_left
                    nome_cell.border    = borda

                    # Data (só dia/mes)
                    data_fmt = r["Data"].rsplit("/", 1)[0]  # retira "/YYYY"
                    d_cell = ws.cell(row=row_out, column=3, value=data_fmt)
                    d_cell.font      = font_normal
                    d_cell.alignment = alin_center
                    d_cell.border    = borda

                    # Motivo (centralizado)
                    m_cell = ws.cell(row=row_out, column=4,
                                     value=r["Motivo da Ocorrência"])
                    m_cell.font      = font_normal
                    m_cell.alignment = alin_center
                    m_cell.border    = borda

                    row_out += 1

                # linha em branco com bordas
                for col_idx in (2, 3, 4):
                    blank = ws.cell(row=row_out, column=col_idx, value="")
                    blank.font      = font_normal
                    blank.alignment = alin_center
                    blank.border    = borda
                row_out += 1

            # auto‐fit de colunas
            for col_idx in (2, 3, 4):
                col_letter = get_column_letter(col_idx)
                max_len = max(
                    len(str(cell.value)) for cell in ws[col_letter]
                    if cell.value is not None
                )
                ws.column_dimensions[col_letter].width = max_len + 2

            # grava em buffer e disponibiliza download
            buf = BytesIO()
            wb.save(buf)
            buf.seek(0)
            nome_saida = (f"Ocorrencias_Diarias_"
                          f"{remover_acentos(mes)}_{ano}.xlsx")

            st.download_button(
                label="📥 Baixar relatório em Excel",
                data=buf,
                file_name=nome_saida,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:
            st.error(f"Erro ao gerar Excel formatado: {e}")

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
        descricao = TIPOS_FALTA_DESCRICAO.get(tipo, tipo)
        motivo = f"{descricao}: {tipo}"
        registrar_ocorrencia(nome, data, motivo)


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

def cadastrar_rpa_interface():
    st.subheader("Cadastrar funcionário RPA (temporário)")

    nome = st.text_input("Nome completo do RPA")
    coren = st.text_input("Número do COREN-SP (opcional)")
    funcao = st.selectbox("Função", ["Enfermeiro", "Técnico de enfermagem", "Auxiliar de enfermagem"])
    setor = st.selectbox("Setor de atuação", list(REGRAS_SETOR.keys()))
    turno = st.selectbox("Turno", ["Diurno", "Noturno"])
    plantao = st.selectbox("Plantão", ["A", "B"])

    dias = []
    mes_atual = datetime.today().month
    ano_atual = datetime.today().year
    nome_mes = MESES_PT[mes_atual - 1]
    ultimo_dia = monthrange(ano_atual, mes_atual)[1]

    if plantao:
        dias_validos = list(range(1, ultimo_dia + 1, 2)) if plantao == "A" else list(range(2, ultimo_dia + 1, 2))
        dias = st.multiselect("Dias que irá atuar (mês atual)", dias_validos)

    if st.button("Registrar RPA"):
        if not nome or not dias:
            st.warning("Preencha todos os campos obrigatórios.")
            return

        os.makedirs("rpa", exist_ok=True)
        caminho = os.path.join("rpa", "rpa_allocations.csv")
        nova_linha = pd.DataFrame([{
            "Nome": nome,
            "COREN-SP": coren if coren else "RPA",
            "Função": funcao,
            "Setor": setor,
            "Turno": turno,
            "Plantão": plantao,
            "Dias": ",".join(str(d) for d in dias),
            "Mês": mes_atual,
            "Ano": ano_atual
        }])

        if os.path.exists(caminho):
            df = pd.read_csv(caminho)
            df = pd.concat([df, nova_linha], ignore_index=True)
        else:
            df = nova_linha

        df.to_csv(caminho, index=False)

        # Adiciona o RPA diretamente na escala
        os.makedirs("escalas", exist_ok=True)
        nome_arquivo = f"{setor.replace(' ', '_').replace('/', '-')}_({turno} {plantao})_{nome_mes}_{ano_atual}.csv"
        caminho_escala = os.path.join("escalas", nome_arquivo)

        if os.path.exists(caminho_escala):
            escala_df = pd.read_csv(caminho_escala)
        else:
            escala_df = pd.DataFrame()

        nova_entrada = {
            "Nome": nome,
            "Função": funcao,
            "COREN-SP": coren if coren else "RPA",
            "Horário": "07x19" if turno == "Diurno" else "19x07",
            "Turno": turno,
            "Plantão": plantao,
            "Setor": setor,
            "Setores Preferidos": "",
            "Mês": f"{nome_mes} de {ano_atual}"
        }

        for d in dias:
            nova_entrada[f"Dia {d}"] = "D" if turno == "Diurno" else "N"

        escala_df = pd.concat([escala_df, pd.DataFrame([nova_entrada])], ignore_index=True)
        escala_df.to_csv(caminho_escala, index=False)

        st.success(f"RPA {nome} cadastrado com sucesso e adicionado à escala de {setor} ({turno} {plantao}) para os dias: {', '.join(map(str, dias))}")

def registrar_troca_plantao_interface(funcionarios):
    st.subheader("Registrar troca de plantão entre funcionários")

    nomes_disponiveis = [f.nome for f in funcionarios]
    nome1 = st.selectbox("Funcionário A", nomes_disponiveis)
    nome2 = st.selectbox("Funcionário B", [n for n in nomes_disponiveis if n != nome1])

    ano = st.number_input("Ano", min_value=2020, max_value=2100, value=datetime.today().year)
    mes_nome = st.selectbox("Mês", MESES_PT, index=datetime.today().month - 1)
    mes = MESES_PT.index(mes_nome) + 1
    ultimo_dia = monthrange(ano, mes)[1]

    col1, col2 = st.columns(2)
    with col1:
        dia_a = st.selectbox(f"Dia original de {nome1}", list(range(1, ultimo_dia + 1)), key="dia1")
    with col2:
        dia_b = st.selectbox(f"Dia original de {nome2}", list(range(1, ultimo_dia + 1)), key="dia2")

    if st.button("Registrar troca"):
        try:
            data_a = date(ano, mes, dia_a)
            data_b = date(ano, mes, dia_b)

            motivo1 = f"Troca de plantão com {nome2} (ficará com dia {dia_b})"
            motivo2 = f"Troca de plantão com {nome1} (ficará com dia {dia_a})"

            registrar_ocorrencia(nome1, data_a, motivo1)
            registrar_ocorrencia(nome2, data_b, motivo2)

            st.success(f"Troca registrada entre {nome1} (dia {dia_a}) e {nome2} (dia {dia_b}).")
        except Exception as e:
            st.error(f"Erro ao registrar troca: {e}")

def visualizar_e_editar_funcionarios():
    st.subheader("Visualizar e editar funcionários")
    try:
        df = pd.read_csv(CAMINHO_CSV_DEFAULT)
        termo_busca = st.text_input("Buscar por nome ou COREN-SP")
        df_filtrado = df[df["Nome"].str.contains(termo_busca, case=False) | df["COREN-SP"].astype(str).str.contains(termo_busca)] if termo_busca else df

        setores_possiveis = [
            "Classificação de risco", "Sala de emergência", "Sala de medicação",
            "Sala de sutura e CME", "Repouso/observação", "Supervisão Técnica"
        ]

        horarios_validos = ["07x19", "19x07", "07:30x16:30"]
        plantoes_validos = ["A", "B"]
        profissoes_validas = [
            "Enfermeiro", "Técnico de enfermagem", "Auxiliar de enfermagem",
            "Supervisor Técnico", "Responsável Técnico"
        ]

        for i in range(len(df_filtrado)):
            idx_original = df_filtrado.index[i]
            with st.expander(f"{df_filtrado.iloc[i]['Nome']} - {df_filtrado.iloc[i]['Função']}"):
                st.markdown(f"**Nome:** {df_filtrado.iloc[i]['Nome']}")
                st.markdown(f"**COREN-SP:** {df_filtrado.iloc[i]['COREN-SP']}")
                st.markdown(f"**Função:** {df_filtrado.iloc[i]['Função']}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    horario_atual = df_filtrado.iloc[i]["Horário"]
                    opcoes_horario = horarios_validos if horario_atual in horarios_validos else [horario_atual] + horarios_validos
                    novo_horario = st.selectbox("Horário", opcoes_horario, index=0, key=f"horario_{i}")
                with col2:
                    setor_atual = df_filtrado.iloc[i]["Setor"]
                    opcoes_setor = setores_possiveis if setor_atual in setores_possiveis else [setor_atual] + setores_possiveis
                    novo_setor = st.selectbox("Setor", opcoes_setor, index=0, key=f"setor_{i}")
                with col3:
                    plantao_atual = df_filtrado.iloc[i]["Plantão"]
                    opcoes_plantao = plantoes_validos if plantao_atual in plantoes_validos else [plantao_atual] + plantoes_validos
                    novo_plantao = st.selectbox("Plantão", opcoes_plantao, index=0, key=f"plantao_{i}")

                setores_pref_atuais = [
                    s.strip() for s in str(df_filtrado.iloc[i].get("Setores Preferidos", "")).split(",")
                    if s.strip() in setores_possiveis and s.strip() != novo_setor
                ]
                novos_preferidos = st.multiselect(
                    "Setores preferidos (opcional)",
                    options=[s for s in setores_possiveis if s != novo_setor],
                    default=setores_pref_atuais,
                    key=f"preferidos_{i}"
                )

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


st.title("Sistema de Alocação de Funcionários - UPA")
st.image("imagens/logo.png", use_container_width=True)
funcionarios = carregar_funcionarios(CAMINHO_CSV_DEFAULT)

# inicializa ação como None
acao = None

with st.sidebar:
    st.header("Menu")

    with st.expander("Escalas"):
        if st.button("Alocar novas escalas"):
            acao = "Alocar novas escalas"
        if st.button("Visualizar escalas"):
            acao = "Visualizar escalas"

    with st.expander("Funcionários"):
        if st.button("Adicionar novo funcionário"):
            acao = "Adicionar novo funcionário"
        if st.button("Cadastrar RPA"):
            acao = "Cadastrar RPA"
        if st.button("Visualizar e editar funcionários"):
            acao = "Visualizar e editar funcionários"

    with st.expander("Faltas e Ocorrências"):
        if st.button("Registrar falta ou ocorrência"):
            acao = "Registrar falta ou ocorrência"
        if st.button("Registrar faltas planejadas"):
            acao = "Registrar faltas planejadas"
        if st.button("Registrar troca de plantão"):
            acao = "Registrar troca de plantão"
        if st.button("Visualizar ocorrências"):
            acao = "Visualizar ocorrências"


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
            if not nome_arquivo.endswith(".csv"):
                continue
            caminho = os.path.join(escalas_path, nome_arquivo)
            try:
                df = pd.read_csv(caminho)
                # transforma "Sala_de_emergência_(Diurno_A)_Maio_2025.csv"
                # em "Sala de emergência (Diurno A) Maio 2025"
                nome = nome_arquivo.replace("_", " ").replace(".csv", "").replace("-", "/")
                arquivos_gerados.append((nome, caminho, df))
            except Exception as e:
                st.warning(f"Erro ao carregar {nome_arquivo}: {e}")

    if arquivos_gerados:
        setores_disponiveis = sorted({nome.split(" (")[0] for nome, _, _ in arquivos_gerados})
        turnos_disponiveis = sorted({nome.split("(")[1].split(")")[0] for nome, _, _ in arquivos_gerados})

        setor_filtro = st.selectbox("Filtrar por setor", ["Todos"] + setores_disponiveis)
        turno_filtro = st.selectbox("Filtrar por turno", ["Todos"] + turnos_disponiveis)

        for nome, caminho, df in arquivos_gerados:
            setor_nome = nome.split(" (")[0]
            turno_nome = nome.split("(")[1].split(")")[0]

            if (setor_filtro in ("Todos", setor_nome)) and (turno_filtro in ("Todos", turno_nome)):
                with st.expander(nome):
                    # omite colunas redundantes
                    colunas_omitir = {"Setores Preferidos", "Mês", "Setor", "Turno", "Plantão"}
                    df_exibir = df[[c for c in df.columns if c not in colunas_omitir]]
                    st.dataframe(df_exibir)

                    # ---- botão de exportação para Excel ----
                    if st.button("📥 Exportar Excel desta escala", key=f"exp_{nome}"):
                        # extrai ano, mês e plantão diretamente do nome do arquivo
                        arquivo = os.path.basename(caminho)          # ex: "Sala_de_emergência_(Diurno_A)_Maio_2025.csv"
                        partes = arquivo[:-4].split("_")
                        ano   = int(partes[-1])
                        mes_nome = partes[-2].capitalize()           # "Maio"
                        mes = MESES_PT.index(mes_nome) + 1
                        turno_id = partes[-3].strip("()")            # "A" ou "B"

                        # chama a função que cria o Excel formatado
                        buf = exportar_escala_para_excel(
                            setor=setor_nome,
                            df=df_exibir,
                            mes=mes,
                            ano=ano,
                            turno_id=turno_id
                        )
                        st.download_button(
                            label="Baixar Excel formatado",
                            data=buf,
                            file_name=f"Escala_{setor_nome}_{mes_nome}_{ano}_{turno_id}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    # -----------------------------------------

    else:
        st.info("Nenhuma escala encontrada na pasta 'escalas'.")

elif acao == "Adicionar novo funcionário":
    adicionar_funcionario_interface()

elif acao == "Cadastrar RPA":
    cadastrar_rpa_interface()

elif acao == "Visualizar e editar funcionários":
    visualizar_e_editar_funcionarios()

elif acao == "Registrar falta ou ocorrência":
    registrar_falta_interface(funcionarios)

elif acao == "Registrar faltas planejadas":
    registrar_falta_planejada_interface(funcionarios)

elif acao == "Visualizar ocorrências":
    visualizar_ocorrencias_interface()

elif acao == "Registrar troca de plantão":
    registrar_troca_plantao_interface(funcionarios)
