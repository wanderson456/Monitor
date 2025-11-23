import dash
from dash import html, dcc, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import requests
from bs4 import BeautifulSoup
import plotly.graph_objs as go

# Inicializa Dash
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# Abas e conteúdos sugeridos + palavras-chave flexíveis
ABAS_LAI = {
    "Institucional / Prefeitura": [
        ["organograma", "estrutura organizacional"],
        ["competências", "funções de cada secretaria"],
        ["contato", "telefone", "gestor"],
        ["endereço", "mapa do município"],
        ["horários de atendimento"]
    ],
    "Gestão e Planejamento": [
        ["ppa", "plano plurianual"],
        ["ldo", "lei de diretrizes orçamentárias"],
        ["loa", "lei orçamentária anual"],
        ["metas", "indicadores municipais"],
        ["relatório de execução"]
    ],
    "Orçamento e Finanças": [
        ["receita", "despesa", "gastos"],
        ["demonstrativo contábil", "relatório financeiro"],
        ["repasses federais", "repasses estaduais"],
        ["prestação de contas"]
    ],
    "Licitações e Contratos": [
        ["licitação", "edital", "resultado"],
        ["contrato", "aditivo", "convênio"],
        ["valores", "prazos", "relatório de acompanhamento"]
    ],
    "Servidores e Remuneração": [
        ["servidor ativo", "cargos", "funções"],
        ["remuneração", "benefício", "gratificação"],
        ["concurso público", "processo seletivo"]
    ],
    "Atos Oficiais": [
        ["lei municipal", "decreto", "portaria", "resolução"],
        ["ata", "sessão da câmara"],
        ["diário oficial", "publicação oficial"]
    ],
    "Transparência em Tempo Real / Dados Abertos": [
        ["csv", "json", "dados abertos"],
        ["gráfico interativo", "relatório automatizado"]
    ],
    "Serviços ao Cidadão": [
        ["programa social", "curso", "evento"],
        ["vaga de emprego público"],
        ["canal de denúncia", "ouvidoria", "formulário"]
    ],
    "Auditoria e Controle": [
        ["auditoria interna", "auditoria externa"],
        ["parecer tribunal de contas"],
        ["controle de metas", "indicadores de gestão"]
    ],
    "Ouvidoria / Fale Conosco": [
        ["atendimento eletrônico", "formulário"],
        ["prazo de resposta", "acompanhamento de protocolo"]
    ]
}

# Função para verificar abas + palavras-chave flexíveis
def verificar_abas_flex(url_base):
    resultados = []
    try:
        resp = requests.get(url_base, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        texto_pagina = soup.get_text().lower()

        # Links da página
        links = [a["href"] for a in soup.find_all("a", href=True)]

        for aba, itens in ABAS_LAI.items():
            for palavra_chave_lista in itens:
                # Verifica se qualquer sinônimo aparece no texto ou links
                encontrado = any(any(p.lower() in texto_pagina for p in palavra_chave_lista) or 
                                 any(p.lower() in l.lower() for l in links) for p in palavra_chave_lista)
                # Escolhe link correspondente (o primeiro que contém algum termo)
                link_encontrado = None
                for l in links:
                    if any(p.lower() in l.lower() for p in palavra_chave_lista):
                        link_encontrado = l
                        break
                resultados.append({
                    "aba": aba,
                    "conteudo": ", ".join(palavra_chave_lista),
                    "status": "OK" if encontrado else "Falta",
                    "link": link_encontrado
                })
        return resultados
    except Exception as e:
        return [{"aba": "Erro", "conteudo": str(e), "status": "Erro", "link": None}]

# Layout do dashboard
app.layout = dbc.Container([
    html.H1("Monitor de Cumprimento da LAI (flexível)", className="text-center mb-4"),
    dbc.Row([
        dbc.Col([
            dbc.Input(id="url-input", type="text", placeholder="Digite o link do site", 
                      value="https://iprema.com.br/institucional/")
        ], width=8),
        dbc.Col([
            dbc.Button("Rodar Crawler", id="run-button", color="primary")
        ], width=4)
    ], className="mb-4"),
    dbc.Row([
        dbc.Col([
            dcc.Graph(id="lai-graph")
        ])
    ]),
    dbc.Row([
        dbc.Col([
            html.H4("Tabela detalhada de abas e conteúdos"),
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
                    {'if': {'filter_query': '{status} contains "Falta"'}, 'color': 'red', 'fontWeight': 'bold'},
                ],
                markdown_options={"html": True},
                page_size=20
            )
        ])
    ])
], fluid=True)

# Callback para atualizar gráfico e tabela
@app.callback(
    Output("lai-graph", "figure"),
    Output("lai-table", "data"),
    Input("run-button", "n_clicks"),
    State("url-input", "value")
)
def atualizar_dashboard(n_clicks, url):
    if not n_clicks:
        return {}, []

    dados = verificar_abas_flex(url)
    
    # Agrupa por aba para gráfico
    abas = list(ABAS_LAI.keys())
    valores = []
    for aba in abas:
        itens = [d for d in dados if d["aba"] == aba]
        if itens:
            ok_count = sum(1 for i in itens if i["status"] == "OK")
            valores.append(ok_count / len(itens))
        else:
            valores.append(0)

    # Gráfico de barras
    fig = go.Figure([go.Bar(x=abas, y=valores, text=[f"{v*100:.0f}%" for v in valores], textposition="auto")])
    fig.update_layout(title="Percentual de Cumprimento da LAI por Aba", 
                      yaxis=dict(range=[0,1], tickvals=[0,0.25,0.5,0.75,1], 
                                 ticktext=["0%","25%","50%","75%","100%"]))

    # Prepara links para Markdown na tabela
    for d in dados:
        if d["link"]:
            d["link"] = f"[Link]({d['link']})"
        else:
            d["link"] = "-"

    return fig, dados

# Rodar app
if __name__ == "__main__":
    app.run(debug=True, port=8050)
