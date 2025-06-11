import time
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
from Fibonacci import calcular_fibonacci, encontrar_zona_fibonacci
from chapeleiro import analisar_pressao
from thedesigner import mostrar_vela_em_tempo_real
import threading
from setup import executar_entrada, capital_setup
from paciencia import Paciencia

# Mapeamento símbolo -> epic real Capital.com (apenas para envio de ordem)
SYMBOL_TO_EPIC = {
    'EURUSD': 'EURUSD',
    'GBPUSD': 'GBPUSD',
    'USDJPY': 'USDJPY',
    'EURJPY': 'EURJPY',
    'GBPJPY': 'GBPJPY',
    'BTCUSD': 'BTCUSD',
    'ETHUSD': 'ETHUSD',
    # Adicione outros conforme necessário
}

# Pares padrão para análise (usados para TradingView e análise)
PARES_PADRAO = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'EURJPY', 'GBPJPY', 'BTCUSD', 'ETHUSD'
]

# Controle de par atual e entrada executada
par_atual_idx = 0
par_atual = PARES_PADRAO[par_atual_idx]
entrada_executada = threading.Event()
par_lock = threading.Lock()

RR_FIXO = 2.0  # Risk:Reward fixo
ATR_MULT_STOP = 2.0  # Stop = ATR * 2

def get_par_atual():
    with par_lock:
        return PARES_PADRAO[par_atual_idx]

def get_proximo_par():
    with par_lock:
        return PARES_PADRAO[(par_atual_idx + 1) % len(PARES_PADRAO)]

def trocar_par():
    global par_atual_idx
    with par_lock:
        par_atual_idx = (par_atual_idx + 1) % len(PARES_PADRAO)
        print(f'[LUCHELO] Trocando para o próximo par: {PARES_PADRAO[par_atual_idx]}')
    entrada_executada.clear()

def get_entrada_executada():
    return entrada_executada.is_set()

def analisar_tendencia(df: pd.DataFrame) -> str:
    """
    Analisa a tendência do mercado com base em médias móveis e volatilidade.
    """
    close = df['close']
    ema50 = close.ewm(span=50, min_periods=50).mean()
    ema200 = close.ewm(span=200, min_periods=200).mean()
    if close.iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]:
        return 'alta'
    elif close.iloc[-1] < ema50.iloc[-1] < ema200.iloc[-1]:
        return 'baixa'
    else:
        return 'lateralizado'

def encontrar_suporte_resistencia(df: pd.DataFrame, n=100):
    """
    Encontra suportes e resistências simples nos últimos n candles.
    """
    ultimos = df.tail(n)
    suporte = ultimos['low'].min()
    resistencia = ultimos['high'].max()
    return suporte, resistencia

def analisar_ponto_entrada(df: pd.DataFrame, tendencia: str, suporte: float, resistencia: float):
    """
    Analisa possíveis pontos de entrada com base na tendência e nos níveis.
    """
    close = df['close'].iloc[-1]
    mensagem = f"Tendência: {tendencia}\n"
    if tendencia == 'lateralizado':
        mensagem += f"Mercado lateralizado. Suporte em {suporte:.5f}, resistência em {resistencia:.5f}.\n"
        if abs(close - suporte) < (resistencia - suporte) * 0.1:

            mensagem += "[SUPORTE] Preço próximo ao suporte. Avalie pressão compradora para possível compra.\n"
        elif abs(close - resistencia) < (resistencia - suporte) * 0.1:
            mensagem += "[RESISTÊNCIA] Preço próximo à resistência. Avalie pressão vendedora para possível venda.\n"
    elif tendencia == 'alta':
        mensagem += f"Mercado em alta. Suporte relevante em {suporte:.5f}.\n"
        if abs(close - suporte) < (resistencia - suporte) * 0.1:
            mensagem += "[SUPORTE] Preço recuando para suporte. Avalie força compradora para possível compra.\n"
    elif tendencia == 'baixa':
        mensagem += f"Mercado em baixa. Resistência relevante em {resistencia:.5f}.\n"
        if abs(close - resistencia) < (resistencia - suporte) * 0.1:
            mensagem += "[RESISTÊNCIA] Preço subindo para resistência. Avalie força vendedora para possível venda.\n"
    return mensagem

def exibir_fibonacci_info(fibo_ctx):
    print("\n--- [FIBONACCI] ---")
    print(f"Swing High: {fibo_ctx['swing_high']:.5f} | Swing Low: {fibo_ctx['swing_low']:.5f}")
    print(f"Tendência detectada: {fibo_ctx['tendencia']} | Direção: {fibo_ctx['direcao']}")
    print(f"ATR (vol): {fibo_ctx['atr']:.5f}")
    print(f"Preço atual: {fibo_ctx['close']:.5f}")
    print("Níveis de retração:")
    for nivel, valor in fibo_ctx['retracements'].items():
        print(f"  {nivel}: {valor:.5f} | Distância: {fibo_ctx['distancias'][nivel]:.5f}")
    if fibo_ctx['extensoes']:
        print("Níveis de extensão:")
        for nivel, valor in fibo_ctx['extensoes'].items():
            print(f"  {nivel}: {valor:.5f} | Distância: {fibo_ctx['distancias'][nivel]:.5f}")

def monitorar_pnl_apos_ordem(deal_id):
    print(f'[LUCHELO] Monitorando P&L da operação {deal_id}...')
    while True:
        pos = capital_setup.api.consultar_posicao_aberta(deal_id=deal_id)
        if not pos or pos.get('status') != 'OPEN':
            print('[LUCHELO] Operação encerrada.')
            break
        pnl = pos.get('profit')
        if pnl is not None:
            print(f'[LUCHELO] Lucro/Prejuízo tempo real: {pnl}')
        else:
            print(f'[LUCHELO] Lucro/Prejuízo tempo real: --')
        time.sleep(10)

# Função para decidir se é entrada forte (exemplo simplificado)
def detectar_entrada_forte(mensagem, fibo_ctx, tendencia, suporte, resistencia, close):
    # Exemplo: tendência definida + preço muito próximo do suporte/resistência + confluência Fibonacci
    if tendencia == 'alta' and abs(close - suporte) < (resistencia - suporte) * 0.1:
        if fibo_ctx['direcao'] == 'alta' and abs(close - fibo_ctx['retracements']['38.2%']) < fibo_ctx['atr']:
            return 'BUY'
    if tendencia == 'baixa' and abs(close - resistencia) < (resistencia - suporte) * 0.1:
        if fibo_ctx['direcao'] == 'baixa' and abs(close - fibo_ctx['retracements']['61.8%']) < fibo_ctx['atr']:
            return 'SELL'
    return None

def main():
    global par_atual_idx
    print("=== Lucelo: Analista Profissional de Forex ===")
    print("Pares disponíveis para análise:")
    for i, par in enumerate(PARES_PADRAO):
        print(f"{i+1}. {par}")
    escolha = input("Digite o par que deseja analisar (ex: EURUSD): ").strip().upper()
    if escolha in PARES_PADRAO:
        par_atual_idx = PARES_PADRAO.index(escolha)
    else:
        print("Par não reconhecido, usando EURUSD por padrão.")
        par_atual_idx = 0
    # Iniciar Chapeleiro, TheDesigner e Paciencia automaticamente
    thread_chapeleiro = threading.Thread(target=analisar_pressao, args=(get_par_atual(),), daemon=True)
    thread_chapeleiro.start()
    thread_thedesigner = threading.Thread(target=mostrar_vela_em_tempo_real, args=(get_par_atual(),), daemon=True)
    thread_thedesigner.start()
    paciencia = Paciencia(get_entrada_executada, trocar_par, get_par_atual, get_proximo_par, tempo_minutos=15)
    paciencia.start()
    tv = TvDatafeed()
    while True:
        try:
            par = get_par_atual()
            # Buscar candles em M15 para análise principal
            df_m15 = tv.get_hist(symbol=par, exchange='FX', interval=Interval.in_15_minute, n_bars=700)
            # Buscar H4 para contexto macro
            df_h4 = tv.get_hist(symbol=par, exchange='FX', interval=Interval.in_4_hour, n_bars=200)
            if df_m15 is None or len(df_m15) < 200:
                print("[LUCHELO] Erro ao buscar candles M15. Tentando novamente em 1 minuto...")
                time.sleep(60)
                continue
            # Tendência macro (opcional)
            if df_h4 is not None and len(df_h4) >= 50:
                tendencia_macro = analisar_tendencia(df_h4)
                print(f"[MACRO H4] Tendência macro: {tendencia_macro}")
            tendencia = analisar_tendencia(df_m15)
            suporte, resistencia = encontrar_suporte_resistencia(df_m15, n=100)
            mensagem = analisar_ponto_entrada(df_m15, tendencia, suporte, resistencia)
            print(f"\n[{par}] {pd.Timestamp.now()}\n{mensagem}")
            # --- Fibonacci ---
            fibo_ctx = calcular_fibonacci(df_m15, n=200, incluir_extensoes=True)
            exibir_fibonacci_info(fibo_ctx)
            # Checar confluência preço x níveis de Fibonacci (retracement + extensões)
            nivel_prox, valor_prox = encontrar_zona_fibonacci(
                fibo_ctx['close'],
                {**fibo_ctx['retracements'], **fibo_ctx['extensoes']},
                atr=fibo_ctx['atr']
            )
            if nivel_prox:
                print(f"[FIBO] Confluência: Preço muito próximo do nível de Fibonacci {nivel_prox} ({valor_prox:.5f})!")
            else:
                print("[FIBO] Nenhuma confluência forte de preço com níveis de Fibonacci no momento.")
            # --- Entrada automática ---
            close = df_m15['close'].iloc[-1]
            atr = fibo_ctx['atr']
            direcao = detectar_entrada_forte(mensagem, fibo_ctx, tendencia, suporte, resistencia, close)
            if direcao:
                # Cálculo do stop e take combinando ATR e suporte/resistência
                if direcao == 'BUY':
                    stop_atr = close - ATR_MULT_STOP * atr
                    # Stop não pode ser maior que o preço de entrada
                    stop = max(suporte, stop_atr)
                    # Take: alvo técnico (resistência) ou RR fixo, o que for mais próximo
                    take_rr = close + RR_FIXO * (close - stop)
                    take = min(resistencia, take_rr)
                else:
                    stop_atr = close + ATR_MULT_STOP * atr
                    # Stop não pode ser menor que o preço de entrada
                    stop = min(resistencia, stop_atr)
                    # Take: alvo técnico (suporte) ou RR fixo, o que for mais próximo
                    take_rr = close - RR_FIXO * (stop - close)
                    take = max(suporte, take_rr)
                epic = SYMBOL_TO_EPIC.get(par, par)
                print(f"[LUCHELO] ENTRADA FORTE DETECTADA! Enviando ordem automática: {direcao} para {par} (epic: {epic}) ao preço {close} | Stop: {stop:.5f} | Take: {take:.5f} ...")
                resposta = capital_setup.api.enviar_ordem(epic, direcao, 0.01, stop=stop, limit=take)
                print(f"[LUCHELO] Ordem enviada! Resposta: {resposta}")
                deal_id = resposta.get('dealId') or resposta.get('dealReference')
                if deal_id:
                    entrada_executada.set()
                    monitorar_pnl_apos_ordem(deal_id)
                else:
                    print('[LUCHELO] Não foi possível obter o dealId da ordem!')
        except Exception as e:
            print(f"[LUCHELO] Erro na análise: {e}")
        time.sleep(60)  # Analisa a cada minuto

if __name__ == "__main__":
    main() 