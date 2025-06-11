import time
from tvDatafeed import TvDatafeed, Interval
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.style import Style
import pandas as pd

console = Console()

# Função para desenhar uma vela estilizada no terminal
def desenhar_vela(open_, high, low, close, largura=7, altura=20):
    # Normalizar valores para o grid
    maximo = high
    minimo = low
    corpo_topo = max(open_, close)
    corpo_base = min(open_, close)
    # Proporção
    escala = (maximo - minimo) / (altura - 1) if (maximo - minimo) != 0 else 1
    grid = [' ' * largura for _ in range(altura)]
    # Pavio superior
    for i in range(altura):
        preco = maximo - i * escala
        if preco <= high and preco >= corpo_topo:
            grid[i] = ' ' * (largura // 2) + '│' + ' ' * (largura - largura // 2 - 1)
    # Corpo
    cor = 'red' if close < open_ else 'green'
    for i in range(altura):
        preco = maximo - i * escala
        if preco <= corpo_topo and preco >= corpo_base:
            grid[i] = ' ' * (largura // 2 - 1) + '█' * 3 + ' ' * (largura - (largura // 2 + 2))
    # Pavio inferior
    for i in range(altura):
        preco = maximo - i * escala
        if preco < corpo_base and preco >= low:
            grid[i] = ' ' * (largura // 2) + '│' + ' ' * (largura - largura // 2 - 1)
    # Montar texto
    linhas = []
    for i, linha in enumerate(grid):
        if corpo_topo >= maximo - i * escala >= corpo_base:
            linhas.append(Text(linha, style=cor))
        else:
            linhas.append(Text(linha, style='white'))
    return linhas

def mostrar_vela_em_tempo_real(par: str, timeframe: Interval = Interval.in_1_minute, delay: int = 1):
    tv = TvDatafeed()
    with Live(refresh_per_second=4, console=console) as live:
        while True:
            try:
                df = tv.get_hist(symbol=par, exchange='FX', interval=timeframe, n_bars=2)
                if df is None or len(df) < 2:
                    live.update(Panel("Aguardando dados...", title="TheDesigner"))
                    time.sleep(delay)
                    continue
                open_ = df['open'].iloc[-1]
                high = df['high'].iloc[-1]
                low = df['low'].iloc[-1]
                close = df['close'].iloc[-1]
                linhas = desenhar_vela(open_, high, low, close)
                texto = Text.assemble(*linhas)
                painel = Panel(texto, title=f"{par} - Vela Atual", subtitle=f"O: {open_:.5f} H: {high:.5f} L: {low:.5f} C: {close:.5f}")
                live.update(painel)
            except Exception as e:
                live.update(Panel(f"Erro: {e}", title="TheDesigner"))
            time.sleep(delay) 