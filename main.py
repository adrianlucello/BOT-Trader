import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import time
from datetime import datetime, timedelta, date
import json
import os
from ta.momentum import RSIIndicator, WilliamsRIndicator
import sys

try:
    from capital_api import CapitalAPI
except ImportError:
    CapitalAPI = None

BANCA_FILE = 'banca.json'
PARES = ['EURUSD', 'GBPUSD', 'EURGBP', 'USDJPY']
TIMEFRAMES = [Interval.in_5_minute, Interval.in_15_minute, Interval.in_1_hour]

MODO_REAL = True  # Altere para True para operar de verdade

# Funções de gerenciamento de banca

def ler_banca():
    if not os.path.exists(BANCA_FILE):
        return {
            "banca": 200.0,
            "risco_percentual": 1.0,
            "stop_win_diario": 5.0,
            "stop_loss_diario": -5.0,
            "historico": [],
            "ultimo_dia": None
        }
    with open(BANCA_FILE, 'r') as f:
        return json.load(f)

def salvar_banca(dados):
    with open(BANCA_FILE, 'w') as f:
        json.dump(dados, f, indent=2)

# Função para buscar candles de qualquer par e timeframe
def buscar_candles(par, timeframe=Interval.in_5_minute, n_bars=100):
    tv = TvDatafeed()
    df = tv.get_hist(symbol=par, exchange='FX', interval=timeframe, n_bars=n_bars)
    return df

# Estratégia base: cruzamento de médias móveis + suporte/resistência
def detectar_price_action(df):
    # Engolfo de alta
    if (
        df['close'].iloc[-2] < df['open'].iloc[-2] and  # candle anterior de baixa
        df['close'].iloc[-1] > df['open'].iloc[-1] and  # candle atual de alta
        df['open'].iloc[-1] < df['close'].iloc[-2] and  # abertura do atual abaixo do fechamento anterior
        df['close'].iloc[-1] > df['open'].iloc[-2]      # fechamento do atual acima da abertura anterior
    ):
        return 'Engolfo de Alta'
    # Engolfo de baixa
    if (
        df['close'].iloc[-2] > df['open'].iloc[-2] and  # candle anterior de alta
        df['close'].iloc[-1] < df['open'].iloc[-1] and  # candle atual de baixa
        df['open'].iloc[-1] > df['close'].iloc[-2] and  # abertura do atual acima do fechamento anterior
        df['close'].iloc[-1] < df['open'].iloc[-2]      # fechamento do atual abaixo da abertura anterior
    ):
        return 'Engolfo de Baixa'
    # Martelo
    corpo = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
    sombra_inf = df['open'].iloc[-1] - df['low'].iloc[-1] if df['open'].iloc[-1] > df['close'].iloc[-1] else df['close'].iloc[-1] - df['low'].iloc[-1]
    sombra_sup = df['high'].iloc[-1] - df['close'].iloc[-1] if df['close'].iloc[-1] > df['open'].iloc[-1] else df['high'].iloc[-1] - df['open'].iloc[-1]
    if corpo < sombra_inf and sombra_inf > 2 * corpo and sombra_sup < corpo:
        return 'Martelo'
    # Pin bar (sombra superior longa)
    if corpo < sombra_sup and sombra_sup > 2 * corpo and sombra_inf < corpo:
        return 'Pin Bar'
    return None

def detectar_rompimento(df, suporte, resistencia):
    # Rompimento de resistência: fechamento atual acima da resistência anterior
    if df['close'].iloc[-1] > resistencia and df['close'].iloc[-2] <= resistencia:
        return 'Rompimento de Resistência'
    # Rompimento de suporte: fechamento atual abaixo do suporte anterior
    if df['close'].iloc[-1] < suporte and df['close'].iloc[-2] >= suporte:
        return 'Rompimento de Suporte'
    return None

def detectar_pullback(df, suporte, resistencia):
    # Pullback de resistência: após rompimento, preço retorna para testar resistência e respeita (não fecha abaixo)
    if (
        df['close'].iloc[-3] <= resistencia and  # antes do rompimento
        df['close'].iloc[-2] > resistencia and   # candle de rompimento
        df['low'].iloc[-1] <= resistencia and df['close'].iloc[-1] > resistencia  # candle atual testa resistência mas fecha acima
    ):
        return 'Pullback de Resistência'
    # Pullback de suporte: após rompimento, preço retorna para testar suporte e respeita (não fecha acima)
    if (
        df['close'].iloc[-3] >= suporte and  # antes do rompimento
        df['close'].iloc[-2] < suporte and   # candle de rompimento
        df['high'].iloc[-1] >= suporte and df['close'].iloc[-1] < suporte  # candle atual testa suporte mas fecha abaixo
    ):
        return 'Pullback de Suporte'
    return None

def analisar_estrategia(df):
    if len(df) < 21:
        return None, "Poucos dados para análise.", None, None, None, None, None
    df = df.copy()
    df['ma_curta'] = df['close'].rolling(window=5).mean()
    df['ma_longa'] = df['close'].rolling(window=10).mean()
    # RSI
    rsi = RSIIndicator(df['close'], window=14).rsi()
    df['rsi'] = rsi
    rsi_atual = rsi.iloc[-1]
    # Williams %R
    willr = WilliamsRIndicator(df['high'], df['low'], df['close'], lbp=14).williams_r()
    df['willr'] = willr
    willr_atual = willr.iloc[-1]
    # Price Action
    padrao_pa = detectar_price_action(df)
    prev_diff = df['ma_curta'].iloc[-2] - df['ma_longa'].iloc[-2]
    curr_diff = df['ma_curta'].iloc[-1] - df['ma_longa'].iloc[-1]
    suporte = df['low'].iloc[-21:-1].min()
    resistencia = df['high'].iloc[-21:-1].max()
    preco_atual = df['close'].iloc[-1]
    distancia_suporte = abs(preco_atual - suporte)
    distancia_resistencia = abs(preco_atual - resistencia)
    limiar = 0.0007
    # Rompimento
    rompimento = detectar_rompimento(df, suporte, resistencia)
    # Pullback
    pullback = detectar_pullback(df, suporte, resistencia)
    tendencia = ""
    if df['ma_curta'].iloc[-1] > df['ma_curta'].iloc[-2]:
        tendencia += "Média curta subindo. "
    else:
        tendencia += "Média curta descendo. "
    if df['ma_longa'].iloc[-1] > df['ma_longa'].iloc[-2]:
        tendencia += "Média longa subindo."
    else:
        tendencia += "Média longa descendo."
    possivel = ""
    if abs(curr_diff) < abs(prev_diff) and abs(curr_diff) < 0.0005:
        possivel = "Médias se aproximando, possível sinal na próxima vela. "
    sinal = None
    instrucao = None
    assertividade = "BAIXA"
    motivo_rsi = ""
    motivo_pa = ""
    motivo_romp = ""
    motivo_pull = ""
    motivo_willr = ""
    # Estratégia de cruzamento + filtros
    if prev_diff < 0 and curr_diff > 0:
        if distancia_suporte < limiar:
            if rsi_atual < 30 and willr_atual < -80:
                if padrao_pa in ['Engolfo de Alta', 'Martelo']:
                    sinal = "CALL (COMPRA)"
                    assertividade = "ALTA"
                    instrucao = f"Entre comprado (CALL) para expiração de 5 minutos, padrão PA: {padrao_pa}. Se a vela abriu às {{hora}}, compre para expirar às {{prox_hora}}."
                else:
                    motivo_pa = f"Sem confirmação de price action de compra (PA detectado: {padrao_pa}). NÃO ENTRAR!"
                    instrucao = motivo_pa
            else:
                if rsi_atual >= 30:
                    motivo_rsi = f"RSI={rsi_atual:.2f} não está em sobrevenda (<30). "
                if willr_atual >= -80:
                    motivo_willr = f"Williams %R={willr_atual:.2f} não está em sobrevenda (<-80). "
                instrucao = motivo_rsi + motivo_willr + "NÃO ENTRAR!"
        else:
            instrucao = "Cruzamento de compra detectado, mas preço longe do suporte. NÃO ENTRAR!"
    elif prev_diff > 0 and curr_diff < 0:
        if distancia_resistencia < limiar:
            if rsi_atual > 70 and willr_atual > -20:
                if padrao_pa in ['Engolfo de Baixa', 'Pin Bar']:
                    sinal = "PUT (VENDA)"
                    assertividade = "ALTA"
                    instrucao = f"Entre vendido (PUT) para expiração de 5 minutos, padrão PA: {padrao_pa}. Se a vela abriu às {{hora}}, compre para expirar às {{prox_hora}}."
                else:
                    motivo_pa = f"Sem confirmação de price action de venda (PA detectado: {padrao_pa}). NÃO ENTRAR!"
                    instrucao = motivo_pa
            else:
                if rsi_atual <= 70:
                    motivo_rsi = f"RSI={rsi_atual:.2f} não está em sobrecompra (>70). "
                if willr_atual <= -20:
                    motivo_willr = f"Williams %R={willr_atual:.2f} não está em sobrecompra (>-20). "
                instrucao = motivo_rsi + motivo_willr + "NÃO ENTRAR!"
        else:
            instrucao = "Cruzamento de venda detectado, mas preço longe da resistência. NÃO ENTRAR!"
    # Estratégia de rompimento
    elif rompimento == 'Rompimento de Resistência' and rsi_atual < 70 and willr_atual < -20:
        sinal = "CALL (COMPRA)"
        assertividade = "ALTA"
        motivo_romp = "Rompimento de resistência detectado."
        instrucao = f"Entre comprado (CALL) após rompimento de resistência. Se a vela abriu às {{hora}}, compre para expirar às {{prox_hora}}."
    elif rompimento == 'Rompimento de Suporte' and rsi_atual > 30 and willr_atual > -80:
        sinal = "PUT (VENDA)"
        assertividade = "ALTA"
        motivo_romp = "Rompimento de suporte detectado."
        instrucao = f"Entre vendido (PUT) após rompimento de suporte. Se a vela abriu às {{hora}}, compre para expirar às {{prox_hora}}."
    # Estratégia de pullback
    elif pullback == 'Pullback de Resistência' and rsi_atual < 70 and willr_atual < -20:
        sinal = "CALL (COMPRA)"
        assertividade = "ALTA"
        motivo_pull = "Pullback de resistência confirmado."
        instrucao = f"Entre comprado (CALL) após pullback de resistência. Se a vela abriu às {{hora}}, compre para expirar às {{prox_hora}}."
    elif pullback == 'Pullback de Suporte' and rsi_atual > 30 and willr_atual > -80:
        sinal = "PUT (VENDA)"
        assertividade = "ALTA"
        motivo_pull = "Pullback de suporte confirmado."
        instrucao = f"Entre vendido (PUT) após pullback de suporte. Se a vela abriu às {{hora}}, compre para expirar às {{prox_hora}}."
    else:
        instrucao = "Aguardando confirmação de cruzamento, price action, rompimento ou pullback."
    detalhes = f"{tendencia}{possivel}Suporte: {suporte:.5f} | Resistência: {resistencia:.5f}. RSI: {rsi_atual:.2f} | Williams %R: {willr_atual:.2f} "
    if padrao_pa:
        detalhes += f"| Price Action: {padrao_pa} "
    if rompimento:
        detalhes += f"| {rompimento} "
    if pullback:
        detalhes += f"| {pullback} "
    if motivo_rsi:
        detalhes += motivo_rsi
    if motivo_pa:
        detalhes += motivo_pa
    if motivo_romp:
        detalhes += motivo_romp
    if motivo_pull:
        detalhes += motivo_pull
    if motivo_willr:
        detalhes += motivo_willr
    return sinal, detalhes, suporte, resistencia, distancia_suporte, distancia_resistencia, (instrucao, assertividade)

# Simulação de trade
def simular_trade(par, timeframe, df, sinal, banca, risco_percentual):
    preco_entrada = df['close'].iloc[-1]
    pip = 0.0001 if 'JPY' not in par else 0.01
    sl_pips = 15
    tp_pips = 30
    if sinal == 'CALL (COMPRA)':
        stop_loss = preco_entrada - sl_pips * pip
        take_profit = preco_entrada + tp_pips * pip
    else:
        stop_loss = preco_entrada + sl_pips * pip
        take_profit = preco_entrada - tp_pips * pip
    valor_risco = banca * (risco_percentual / 100)
    print(f"  - Simulando entrada em {par} | {sinal}")
    print(f"    Entrada: {preco_entrada:.5f} | SL: {stop_loss:.5f} | TP: {take_profit:.5f} | Risco: ${valor_risco:.2f}")
    resultado = None
    for i in range(len(df)-1, len(df)):
        for j in range(i+1, len(df)):
            preco_max = df['high'].iloc[j]
            preco_min = df['low'].iloc[j]
            if sinal == 'CALL (COMPRA)':
                if preco_min <= stop_loss:
                    resultado = 'STOP LOSS'
                    break
                if preco_max >= take_profit:
                    resultado = 'TAKE PROFIT'
                    break
            else:
                if preco_max >= stop_loss:
                    resultado = 'STOP LOSS'
                    break
                if preco_min <= take_profit:
                    resultado = 'TAKE PROFIT'
                    break
        if resultado:
            break
    if resultado == 'TAKE PROFIT':
        ganho = valor_risco * (tp_pips / sl_pips)
        print(f"    Resultado: GAIN! Lucro: ${ganho:.2f}")
        return ganho, 'WIN'
    elif resultado == 'STOP LOSS':
        print(f"    Resultado: LOSS! Prejuízo: -${valor_risco:.2f}")
        return -valor_risco, 'LOSS'
    else:
        print(f"    Resultado: Operação não finalizada (mercado lateral ou sem candles suficientes)")
        return 0, 'OPEN'

# Mapeamento dos epics dos principais pares de moedas na Capital.com
EPICS = {
    'EURUSD': 'CS.D.EURUSD.MINI.IP',
    'GBPUSD': 'CS.D.GBPUSD.MINI.IP',
    'USDJPY': 'CS.D.USDJPY.MINI.IP',
    'EURGBP': 'CS.D.EURGBP.MINI.IP',
}


if __name__ == "__main__":
    if MODO_REAL:
        if not CapitalAPI:
            print("capital_api.py não encontrado! Não é possível operar em modo real.")
            sys.exit(1)
        api = CapitalAPI()
        api.autenticar()
        saldo_api = api.saldo()
        saldo_demo = saldo_api['accounts'][0]['balance']['balance']
        banca = ler_banca()
        banca['banca'] = saldo_demo
        print(f"[MODO REAL] Banca sincronizada com Capital.com: ${banca['banca']:.2f}")
    else:
        banca = ler_banca()
        print(f"[SIMULAÇÃO] Banca atual: ${banca['banca']:.2f} | Risco por operação: {banca['risco_percentual']}%\n")
    print(f"Pares monitorados: {', '.join(PARES)}")
    print("Robô Trader Multi-Pares - Análise e Simulação de Trades\n")
    while True:
        hoje = date.today().isoformat()
        if banca.get('ultimo_dia') != hoje:
            banca['ultimo_dia'] = hoje
            banca['lucro_dia'] = 0.0
            salvar_banca(banca)
        if banca['lucro_dia'] >= banca['stop_win_diario']:
            print(f"\n[STOP WIN] Meta diária de lucro atingida (+${banca['lucro_dia']:.2f}). Robô vai pausar até amanhã.\n")
            time.sleep(60*60*3)
            continue
        if banca['lucro_dia'] <= banca['stop_loss_diario']:
            print(f"\n[STOP LOSS] Limite diário de perda atingido (${banca['lucro_dia']:.2f}). Robô vai pausar até amanhã.\n")
            time.sleep(60*60*3)
            continue
        for par in PARES:
            for timeframe in TIMEFRAMES:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Analisando {par} | Timeframe: {timeframe.name}")
                try:
                    df = buscar_candles(par, timeframe)
                    if df is not None and not df.empty:
                        sinal, detalhes, suporte, resistencia, dist_sup, dist_res, extra = analisar_estrategia(df)
                        instrucao, assertividade = extra if extra else (None, None)
                        candle = df.iloc[-1]
                        cor = "verde" if candle['close'] > candle['open'] else "vermelha"
                        print(f"  - Vela atual: {cor} (abertura: {candle['open']:.5f}, fechamento: {candle['close']:.5f})")
                        ma_curta = df['ma_curta'].iloc[-1] if 'ma_curta' in df.columns and pd.notna(df['ma_curta'].iloc[-1]) else None
                        ma_longa = df['ma_longa'].iloc[-1] if 'ma_longa' in df.columns and pd.notna(df['ma_longa'].iloc[-1]) else None
                        if ma_curta is not None and ma_longa is not None:
                            print(f"  - Média curta: {ma_curta:.5f} | Média longa: {ma_longa:.5f}")
                        else:
                            print("  - Médias móveis ainda não disponíveis (aguardando mais candles)")
                        if suporte is not None and resistencia is not None:
                            print(f"  - Suporte: {suporte:.5f} | Resistência: {resistencia:.5f}")
                        if dist_sup is not None and dist_res is not None:
                            print(f"  - Distância até suporte: {dist_sup:.5f} | Distância até resistência: {dist_res:.5f}")
                        print(f"  - {detalhes}")
                        if sinal and assertividade == 'ALTA':
                            hora = pd.to_datetime(df.index[-1])
                            prox_hora = hora + timedelta(minutes=5)
                            if instrucao:
                                instrucao_final = instrucao.format(hora=hora.strftime('%H:%M'), prox_hora=prox_hora.strftime('%H:%M'))
                                print(f"  >>> SINAL: {sinal} | Assertividade: {assertividade}")
                                print(f"  >>> {instrucao_final}")
                            else:
                                print(f"  >>> SINAL: {sinal} | Assertividade: {assertividade}")
                            if MODO_REAL:
                                # Enviar ordem real
                                direcao = 'BUY' if 'CALL' in sinal else 'SELL'
                                lote = 1  # Ajuste conforme sua gestão
                                try:
                                    print(f"[MODO REAL] Enviando ordem para {par} ({direcao})...")
                                    # Aqui você pode mapear o epic correto do ativo
                                    epic = EPICS.get(par, par)
                                    api.enviar_ordem(epic, direcao, lote)
                                    print(f"[MODO REAL] Ordem enviada para {par} ({direcao})!")
                                    ganho = 0  # Não sabemos o resultado imediato
                                    resultado = 'ENVIADA'
                                except Exception as e:
                                    print(f"[MODO REAL] Erro ao enviar ordem: {e}")
                                    ganho = 0
                                    resultado = 'ERRO ENVIO'
                            else:
                                ganho, resultado = simular_trade(par, timeframe, df, sinal, banca['banca'], banca['risco_percentual'])
                            banca['banca'] += ganho
                            banca['lucro_dia'] += ganho
                            banca['historico'].append({
                                'par': par,
                                'timeframe': timeframe.name,
                                'sinal': sinal,
                                'resultado': resultado,
                                'lucro': ganho,
                                'banca': banca['banca'],
                                'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                            salvar_banca(banca)
                            print(f"  - Banca atualizada: ${banca['banca']:.2f} | Lucro do dia: ${banca['lucro_dia']:.2f}")
                        else:
                            if instrucao:
                                print(f"  - {instrucao}")
                            print(f"  - Assertividade: {assertividade}")
                        print("-")
                except Exception as e:
                    print(f"  Erro ao analisar {par} ({timeframe.name}): {e}")
        print("Aguardando próximo ciclo de análise...\n")
        time.sleep(60)
        # Atualizar banca com saldo real da conta demo a cada ciclo
        if MODO_REAL:
            saldo_api = api.saldo()
            saldo_demo = saldo_api['accounts'][0]['balance']['balance']
            banca['banca'] = saldo_demo
            print(f"[MODO REAL] Banca sincronizada com Capital.com: ${banca['banca']:.2f}")

            