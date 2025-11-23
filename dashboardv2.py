import os
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
import re

try:
    import PyPDF2
except:
    PyPDF2 = None

# cria pasta assets se não existir (para servir a página HTML)
if not os.path.exists("assets"):
    os.makedirs("assets")

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

# Variáveis globais
resultados_parciais = []
log_msgs = []
progresso = {"total": 0, "processados": 0}
thread_active = False
url_global = None
stop_thread = False  # controle para parar a verificação

# --- Funções ---
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
        with io.Bytes.BytesIO(resp.content) as f:
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

def processar_site(url):
    """
    Processamento incremental (thread). Atualiza resultados_parciais e log_msgs.
    """
    global resultados_parciais, log_msgs, progresso, thread_active, stop_thread
    log_msgs = []
    resultados_parciais = []

    links = [url] + coletar_links_internos(url)
    progresso["total"] = len(links)
    progresso["processados"] = 0
    log_msgs.append(f"Total de links: {len(links)}")

    for link in links:
        if stop_thread:
            log_msgs.append("Processamento interrompido pelo usuário.")
            break

        log_msgs.append(f"Processando: {link}")
        texto_total = ""
        try:
            resp = requests.get(link, timeout=5)
            soup = BeautifulSoup(resp.text, "html.parser")
            texto_total += soup.get_text() or ""

            for a in soup.find_all("a", href=True):
                href = a["href"]
                file_url = urljoin(link, href)
                if href.lower().endswith(".pdf") and PyPDF2:
                    log_msgs.append(f"  -> PDF: {file_url}")
                    texto_total += extrair_texto_pdf(file_url)
                elif href.lower().endswith((".csv",".xls",".xlsx")):
                    log_msgs.append(f"  -> Planilha: {file_url}")
                    texto_total += extrair_texto_planilha(file_url)
        except Exception as e:
            log_msgs.append(f"Erro ao processar {link}: {e}")

        for aba, palavras in ABAS_LAI.items():
            encontrados = verificar_texto(texto_total, palavras)
            resultados_parciais.append({
                "aba": aba,
                "conteudo": ", ".join(palavras),
                "link": link if encontrados else None,
                "status": "OK" if encontrados else "Não encontrado"
            })

        progresso["processados"] += 1
        time.sleep(0.2)

    thread_active = False
    stop_thread = False

# gera HTML com links do log
def gerar_html_log_links():
    arquivo_saida = os.path.join("assets", "log_links.html")
    urls = set(re.findall(r'https?://[^\s\)]+', "\n".join(log_msgs)))
    html_content = "<html><head><meta charset='utf-8'><title>Links Verificados</title></head><body>"
    html_content += "<h2 style='text-align:center'>Links verificados</h2><ul style='font-family:Arial,sans-serif;'>"
    for url in sorted(urls):
        html_content += f"<li><a href='{url}' target='_blank'>{url}</a></li>"
    html_content += "</ul></body></html>"

    with open(arquivo_saida, "w", encoding="utf-8") as f:
        f.write(html_content)

    return "/assets/log_links.html"

# --- Layout ---
app.layout = dbc.Container([
    dcc.Location(id="redirect-html", refresh=True),

    html.H1("Monitor Incremental LAI", className="text-center mb-4"),
    dbc.Row([
        dbc.Col([dbc.Input(id="url-input", type="text", placeholder="Digite o site (ex: https://araripe.ce.gov.br/transparencia/)")], width=6),
        dbc.Col([dbc.Button("Verificar", id="run-button", color="primary")], width=3),
        dbc.Col([dbc.Button("Parar Verificação", id="stop-button", color="danger")], width=3)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dbc.Progress(id="progress-bar", value=0, striped=True, animated=True, color="info", style={"height":"30px"}),
            html.Div(id="progress-text", className="text-center mt-1", style={"fontWeight":"600"})
        ], width=12)
    ], className="mb-3"),

    dbc.Row([dbc.Col([dcc.Graph(id="lai-graph")])]),

    dbc.Row([dbc.Col([
        html.H4("Tabela de palavras-chave LAI", className="text-center"),
        dash_table.DataTable(
            id='lai-table',
            columns=[
                {"name": "Aba", "id": "aba"},
                {"name": "Conteúdo", "id": "conteudo"},
                {"name": "Link", "id": "link", "presentation": "markdown"},
                {"name": "Status", "id": "status"}
            ],
            style_table={
                'margin': '0 auto',
                'width': '92%',
                'overflowX': 'auto',
                'border': '1px solid #e0e0e0',
                'borderRadius': '10px',
                'boxShadow': '0 2px 8px rgba(0,0,0,0.08)'
            },
            style_cell={
                'textAlign': 'left',
                'padding': '10px',
                'whiteSpace': 'normal',
                'wordWrap': 'break-word',
                'fontFamily': 'Arial, sans-serif',
                'fontSize': '14px',
                'height': 'auto'
            },
            style_cell_conditional=[
                {'if': {'column_id': 'conteudo'}, 'maxWidth': '220px'},
                {'if': {'column_id': 'link'}, 'maxWidth': '160px'},
                {'if': {'column_id': 'aba'}, 'maxWidth': '180px'}
            ],
            style_header={
                'backgroundColor': '#007BFF',
                'color': 'white',
                'fontWeight': 'bold',
                'textAlign': 'center'
            },
            style_data_conditional=[
                {'if': {'filter_query': '{status} contains "OK"'}, 'color': 'green', 'fontWeight': 'bold'},
                {'if': {'filter_query': '{status} contains "Não encontrado"'}, 'color': 'red', 'fontWeight': 'bold'},
                {'if': {'row_index': 'odd'}, 'backgroundColor': '#fbfbfb'}
            ],
            markdown_options={"html": True},
            page_size=20
        )
    ])]),

    dbc.Row([
        dbc.Col([
            dbc.Button("Gerar página HTML dos links do log", id="gerar-html-btn", color="secondary", className="mb-2"),
            html.Div(id="link-html-area")
        ], width=12)
    ]),

    dbc.Row([dbc.Col([
        html.H4("Log de Processamento", className="text-center"),
        html.Div(id="log-area", style={"whiteSpace": "pre-line","height":"280px","overflowY":"scroll","backgroundColor":"#f9f9f9","padding":"10px","border":"1px solid #ddd"})
    ])]),

    dcc.Interval(id="interval-component", interval=700, n_intervals=0)
], fluid=True)

# --- Callbacks ---
@app.callback(
    Output("lai-graph", "figure"),
    Output("lai-table", "data"),
    Output("progress-bar", "value"),
    Output("progress-bar", "children"),
    Output("progress-text", "children"),
    Output("log-area", "children"),
    Input("interval-component", "n_intervals")
)
def atualizar_dashboard_interval(n):
    if not resultados_parciais:
        return {}, [], 0, "", "0%", ""

    df = pd.DataFrame(resultados_parciais)
    counts = df.groupby("status").size()
    fig = go.Figure([go.Bar(x=counts.index, y=counts.values, text=counts.values, textposition="auto")])
    fig.update_layout(title="Status das palavras-chave detectadas", yaxis_title="Quantidade", margin=dict(t=40))

    for d in resultados_parciais:
        if d.get("link") and isinstance(d["link"], str) and not d["link"].startswith("[Link]("):
            d["link"] = f"[Link]({d['link']})"
        elif not d.get("link"):
            d["link"] = "-"

    progresso_percent = int((progresso["processados"]/max(progresso["total"],1))*100)
    log_text = "\n".join(log_msgs[-200:])

    return fig, resultados_parciais, progresso_percent, "", f"{progresso_percent}%", log_text


@app.callback(
    Output("run-button", "disabled"),
    Input("run-button", "n_clicks"),
    State("url-input", "value")
)
def iniciar_processamento(n_clicks, url):
    global thread_active, url_global, stop_thread, progresso
    if n_clicks and url and not thread_active:
        url_global = url
        stop_thread = False
        thread_active = True
        progresso = {"total": 0, "processados": 0}
        threading.Thread(target=processar_site, args=(url,), daemon=True).start()
        return True
    return False


@app.callback(
    Output("stop-button", "disabled"),
    Input("stop-button", "n_clicks")
)
def parar_verificacao(n_clicks):
    global stop_thread, thread_active
    if n_clicks and thread_active:
        stop_thread = True
        return True
    return False


@app.callback(
    Output("link-html-area", "children"),
    Output("redirect-html", "href"),
    Input("gerar-html-btn", "n_clicks"),
    prevent_initial_call=True
)
def gerar_html(n_clicks):
    if not n_clicks:
        return "", dash.no_update

    caminho_relativo = gerar_html_log_links()
    link_comp = html.A("Abrir página com links verificados", href=caminho_relativo, target="_blank", style={"fontWeight":"600"})

    return link_comp, caminho_relativo


if __name__ == "__main__":
    app.run(debug=True, port=8051)
