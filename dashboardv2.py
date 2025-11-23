import dash
from dash import html, dcc, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import requests
from bs4 import BeautifulSoup
import plotly.graph_objs as go
import pandas as pd
from urllib.parse import urljoin, urlparse
import io
import threading
import time

try:
    import PyPDF2
except:
    PyPDF2 = None

# Inicializa app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# Palavras-chave LAI
ABAS_LAI = {
    "Institucional / Prefeitura": ["organograma","estrutura organizacional","gestor","endereço","mapa","telefone","secretaria","secretarias","gestão municipal"],
    "Gestão e Planejamento": ["ppa","loa","ldo","metas","indicadores","plano","relatório de execução","prestação de contas","balanço","relatório financeiro"],
    "Orçamento e Finanças": ["receita","despesa","gasto","demonstrativo","prestação de contas","repasses","balanço","relatório financeiro"],
    "Licitações e Contratos": ["licitação","edital","resultado","contrato","aditivo","convênio","termo de colaboração"],
    "Servidores e Remuneração": ["servidor","cargo","função","remuneração","benefício","gratificação","concurso","processo seletivo"],
    "Atos Oficiais": ["lei municipal","decreto","portaria","resolução","ata","diário oficial","publicação"],
    "Transparência em tempo real / Dados Abertos": ["csv","json","dados abertos","gráfico interativo","relatório automatizado"],
    "Serviços ao Cidadão": ["programa social","curso","evento","vaga de emprego","formulário","ouvidoria","denúncia"],
    "Auditoria e Controle": ["auditoria interna","auditoria externa","tribunal de contas","parecer","indicador de gestão"],
    "Ouvidoria / Fale Conosco": ["ouvidoria","e-sic","protocolo","formulário de atendimento","prazo de resposta"]
}

# Variáveis globais para thread e dashboard
resultados_parciais = []
log_msgs = []
progresso = {"total": 0, "processados": 0}
url_global = None
thread_active = False

# --- Funções de extração ---
def coletar_links_internos(base_url):
    links = set()
    try:
        resp = requests.get(base_url, timeout=5)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            url = urljoin(base_url, a["href"])
            if urlparse(url).netloc == urlparse(base_url).netloc:
                links.add(url)
    except:
        pass
    return list(links)

def extrair_texto_pdf(url):
    if PyPDF2 is None:
        return ""
    try:
        resp = requests.get(url, timeout=10)
        with io.BytesIO(resp.content) as f:
            reader = PyPDF2.PdfReader(f)
            texto = ""
            for page in reader.pages:
                texto += page.extract_text() or ""
        return texto
    except:
        return ""

def extrair_texto_planilha(url):
    try:
        resp = requests.get(url, timeout=10)
        if url.lower().endswith(".csv"):
            df = pd.read_csv(io.StringIO(resp.text))
        else:
            df = pd.read_excel(io.BytesIO(resp.content))
        texto = " ".join(df.astype(str).apply(lambda x: " ".join(x), axis=1).tolist())
        return texto
    except:
        return ""

def verificar_texto(texto, palavras):
    encontrados = []
    for p in palavras:
        if p.lower() in texto.lower():
            encontrados.append(p)
    return encontrados

# --- Função de processamento incremental ---
def processar_site(url):
    global resultados_parciais, log_msgs, progresso, thread_active
    log_msgs = []
    resultados_parciais = []

    links = [url] + coletar_links_internos(url)
    progresso["total"] = len(links)
    progresso["processados"] = 0
    log_msgs.append(f"Total de links: {len(links)}")

    for link in links:
        log_msgs.append(f"Processando: {link}")
        texto_total = ""
        try:
            resp = requests.get(link, timeout=5)
            soup = BeautifulSoup(resp.text, "html.parser")
            texto_total += soup.get_text()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                file_url = urljoin(link, href)
                if href.lower().endswith(".pdf") and PyPDF2:
                    log_msgs.append(f"  -> PDF: {file_url}")
                    texto_total += extrair_texto_pdf(file_url)
                elif href.lower().endswith((".csv",".xls",".xlsx")):
                    log_msgs.append(f"  -> Planilha: {file_url}")
                    texto_total += extrair_texto_planilha(file_url)
        except:
            log_msgs.append(f"Erro ao processar {link}")

        # Atualiza status parcial
        for aba, palavras in ABAS_LAI.items():
            encontrados = verificar_texto(texto_total, palavras)
            for p in palavras:
                status = "OK" if p in encontrados else "Não encontrado"
                # Atualiza resultados existentes ou adiciona novo
                achou = next((r for r in resultados_parciais if r["aba"]==aba and r["conteudo"]==p), None)
                if achou:
                    if status == "OK":
                        achou["status"] = "OK"
                        achou["link"] = url
                else:
                    resultados_parciais.append({"aba": aba, "conteudo": p, "link": url if status=="OK" else None, "status": status})
        
        progresso["processados"] += 1
        time.sleep(0.2)  # evita sobrecarga

    thread_active = False

# --- Layout ---
app.layout = dbc.Container([
    html.H1("Monitor Incremental LAI", className="text-center mb-4"),
    dbc.Row([
        dbc.Col([dbc.Input(id="url-input", type="text", placeholder="Digite o site")], width=8),
        dbc.Col([dbc.Button("Verificar", id="run-button", color="primary")], width=4)
    ], className="mb-4"),

    dbc.Row([dbc.Col([dbc.Progress(id="progress-bar", value=0, striped=True, animated=True, color="info")])]),

    dbc.Row([dbc.Col([dcc.Graph(id="lai-graph")])]),

    dbc.Row([dbc.Col([
        html.H4("Tabela de palavras-chave LAI"),
        dash_table.DataTable(
            id='lai-table',
            columns=[
                {"name": "Aba", "id": "aba"},
                {"name": "Conteúdo", "id": "conteudo"},
                {"name": "Link", "id": "link", "presentation": "markdown"},
                {"name": "Status", "id": "status"}
            ],
            style_cell={'textAlign': 'left', 'padding': '5px'},
            style_header={'backgroundColor': '#f2f2f2', 'fontWeight': 'bold'},
            style_data_conditional=[
                {'if': {'filter_query': '{status} contains "OK"'}, 'color': 'green', 'fontWeight': 'bold'},
                {'if': {'filter_query': '{status} contains "Não encontrado"'}, 'color': 'red', 'fontWeight': 'bold'},
            ],
            markdown_options={"html": True},
            page_size=20
        )
    ])]),

    dbc.Row([dbc.Col([
        html.H4("Log de Processamento"),
        html.Div(id="log-area", style={"whiteSpace": "pre-line", "height":"300px", "overflowY":"scroll","backgroundColor":"#f9f9f9","padding":"10px","border":"1px solid #ddd"})
    ])]),

    # Interval para atualizar incrementalmente
    dcc.Interval(id="interval-component", interval=1500, n_intervals=0)
], fluid=True)

# --- Callbacks ---
@app.callback(
    Output("lai-graph", "figure"),
    Output("lai-table", "data"),
    Output("progress-bar", "value"),
    Output("log-area", "children"),
    Input("interval-component", "n_intervals")
)
def atualizar_dashboard_interval(n):
    if not resultados_parciais:
        return {}, [], 0, ""
    df = pd.DataFrame(resultados_parciais)
    counts = df.groupby("status").size()
    fig = go.Figure([go.Bar(x=counts.index, y=counts.values, text=counts.values, textposition="auto")])
    fig.update_layout(title="Status das palavras-chave detectadas", yaxis_title="Quantidade")

    for d in resultados_parciais:
        if d["link"]:
            d["link"] = f"[Link]({d['link']})"
        else:
            d["link"] = "-"

    progresso_percent = int((progresso["processados"]/max(progresso["total"],1))*100)
    log_text = "\n".join(log_msgs[-50:])
    return fig, resultados_parciais, progresso_percent, log_text

# Botão de iniciar processamento
@app.callback(
    Output("run-button", "disabled"),
    Input("run-button", "n_clicks"),
    State("url-input", "value")
)
def iniciar_processamento(n_clicks, url):
    global thread_active, url_global
    if n_clicks and url and not thread_active:
        url_global = url
        thread_active = True
        threading.Thread(target=processar_site, args=(url,), daemon=True).start()
        return True
    return False

if __name__ == "__main__":
    app.run(debug=True, port=8051)
