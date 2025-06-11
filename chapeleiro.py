import time
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
from typing import Optional

# Função para exibir com cor no terminal
def colorir(texto, cor):
    cores = {
        'vermelho': '\033[91m',
        'verde': '\033[92m',
        'amarelo': '\033[93m',
        'reset': '\033[0m'
    }
    return f"{cores.get(cor, '')}{texto}{cores['reset']}"

def analisar_pressao(par: str, timeframe: Interval = Interval.in_1_minute, n_bars: int = 30, delay: int = 5):
    """
    Monitora o preço em tempo real, mostra variação, soma dos movimentos e pressão compradora/vendedora.
    """
    tv = TvDatafeed()
    ultimo_preco: Optional[float] = None
    soma_movimentos = 0.0
    print(f"Chapeleiro monitorando {par} em tempo real! (aperte Ctrl+C para parar)")
    while True:
        try:
            df = tv.get_hist(symbol=par, exchange='FX', interval=timeframe, n_bars=n_bars)
            if df is None or len(df) < 2:
                print("Sem dados suficientes, tentando novamente...")
                time.sleep(delay)
                continue
            preco_atual = df['close'].iloc[-1]
            preco_anterior = df['close'].iloc[-2]
            variacao = preco_atual - preco_anterior
            soma_movimentos += variacao
            cor = 'amarelo'
            if variacao > 0:
                cor = 'verde'
            elif variacao < 0:
                cor = 'vermelho'
            direcao = '⬆️' if variacao > 0 else ('⬇️' if variacao < 0 else '➡️')
            texto = f"{preco_atual:,.5f} USD {direcao} ({variacao:+.5f}) | Soma: {soma_movimentos:+.2f}"
            print(colorir(texto, cor))
            # Exibir horário do candle
            hora = df.index[-1].strftime('%H:%M UTC-3')
            print(f"Mercado {'aberto' if df.index[-1] else 'fechado'} horário {hora}")
        except Exception as e:
            print(f"Erro no Chapeleiro: {e}")
        time.sleep(delay) 