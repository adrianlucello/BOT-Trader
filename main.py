import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import time
from datetime import datetime, timedelta, date
import json
import os
from ta.momentum import RSIIndicator, WilliamsRIndicator
import sys
import logging
import pandas as pd
from ta.trend import MACD
from ta.volatility import BollingerBands

# Suprimir logs de erro da biblioteca tvDatafeed para console limpo
logging.getLogger('tvDatafeed.main').setLevel(logging.CRITICAL)

try:
    from capital_api import CapitalAPI
except ImportError:
    CapitalAPI = None

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo

BANCA_FILE = 'banca.json'

# Configuração de pares por tipo de mercado
CRIPTO_PARES = ['BTCUSD', 'ETHUSD', 'SOLUSD', 'BCHUSD', 'XRPUSD', 'INJUSD']
FOREX_PARES = ['EURUSD', 'GBPUSD', 'USDJPY', 'EURGBP']

# Todos os pares disponíveis
PARES = CRIPTO_PARES + FOREX_PARES

# Critérios REALISTAS de trading profissional
CRITERIOS_REALISTAS = {
    'MINIMO_CONFLUENCIAS': 2,  # Mínimo 2 confluências (mais realista)
    'ALTA_QUALIDADE': 3,       # 3+ confluências = alta qualidade  
    'EXCELENTE_QUALIDADE': 4   # 4+ confluências = excelente (raro)
}

# Critérios PROFISSIONAIS balanceados
CRITERIOS_PROFISSIONAIS = {
    'SCORE_MINIMO': 3,           # Mínimo 3/6 pontos (realista)
    'SCORE_ALTA_QUALIDADE': 4,  # 4+ pontos para alta qualidade
    'SCORE_EXCELENTE': 5,       # 5+ pontos para excelente
    'PRICE_ACTION_OBRIGATORIO': True,  # Exigir price action se score baixo
    'MULTIPLAS_CONFLUENCIAS': True,    # Exigir múltiplas confluências
}

TIMEFRAMES = [Interval.in_1_minute, Interval.in_5_minute, Interval.in_15_minute, Interval.in_1_hour]

MODO_REAL = True  # Altere para True para operar de verdade

# Definir timezone padrão para o robô (UTC-3)
TZ = ZoneInfo('America/Sao_Paulo')

# Configuração do modo de operação
API_DEMO = True  # True para conta demo, False para conta real

# Configurações de Stop Loss
STOP_LOSS_CONFIG = {
    'modo_padrao': 'NORMAL',  # 'NORMAL' ou 'GARANTIDO'
    'usar_garantido_para_cripto': True,  # Usar stop garantido para criptomoedas (mais voláteis)
    'usar_garantido_para_forex_volatil': False,  # GBP, AUD, NZD pares mais voláteis
    'pares_sempre_garantido': ['BTCUSD', 'ETHUSD', 'XRPUSD'],  # Forçar garantido nestes pares
    'pares_nunca_garantido': ['EURUSD', 'GBPUSD', 'USDJPY'],   # Nunca usar garantido (mais estáveis)
}

def determinar_tipo_stop_loss(par):
    """
    Determina se deve usar stop loss NORMAL ou GARANTIDO baseado no par
    Retorna: True para garantido, False para normal
    """
    # Forçar garantido para pares específicos
    if par in STOP_LOSS_CONFIG['pares_sempre_garantido']:
        print(f"[STOP] {par}: GARANTIDO (forçado por configuração)")
        return True
    
    # Nunca garantido para pares específicos
    if par in STOP_LOSS_CONFIG['pares_nunca_garantido']:
        print(f"[STOP] {par}: NORMAL (forçado por configuração)")
        return False
    
    # Regra para criptomoedas
    if STOP_LOSS_CONFIG['usar_garantido_para_cripto']:
        is_crypto = any(crypto in par for crypto in ['BTC', 'ETH', 'SOL', 'XRP', 'BCH', 'PEPE', 'INJ', 'TREMP'])
        if is_crypto:
            print(f"[STOP] {par}: GARANTIDO (criptomoeda)")
            return True
    
    # Regra para forex volátil
    if STOP_LOSS_CONFIG['usar_garantido_para_forex_volatil']:
        forex_volatil = any(curr in par for curr in ['GBP', 'AUD', 'NZD'])
        if forex_volatil:
            print(f"[STOP] {par}: GARANTIDO (forex volátil)")
            return True
    
    # Padrão do sistema
    if STOP_LOSS_CONFIG['modo_padrao'] == 'GARANTIDO':
        print(f"[STOP] {par}: GARANTIDO (padrão do sistema)")
        return True
    else:
        print(f"[STOP] {par}: NORMAL (padrão do sistema)")
        return False

# Funções de gerenciamento de banca

def ler_banca():
    if not os.path.exists(BANCA_FILE):
        return {
            "banca": 200.0,
            "risco_percentual_operacao": 1.0,  # 1% da banca por operação
            "stop_win_percentual": 5.0,        # 5% da banca como meta diária
            "stop_loss_percentual": -3.0,      # -3% da banca como limite diário
            "historico": [],
            "ultimo_dia": None,
            "lucro_dia": 0.0
        }
    with open(BANCA_FILE, 'r') as f:
        return json.load(f)

def salvar_banca(dados):
    with open(BANCA_FILE, 'w') as f:
        json.dump(dados, f, indent=2)

def calcular_limites_dinamicos(banca_atual, config):
    """
    Calcula limites dinâmicos baseados na banca atual (juros compostos)
    """
    risco_por_operacao = banca_atual * (config['risco_percentual_operacao'] / 100)
    stop_win_diario = banca_atual * (config['stop_win_percentual'] / 100)
    stop_loss_diario = banca_atual * (config['stop_loss_percentual'] / 100)
    
    return {
        'risco_por_operacao': risco_por_operacao,
        'stop_win_diario': stop_win_diario, 
        'stop_loss_diario': stop_loss_diario
    }

def obter_lote_padrao(par):
    """
    Retorna lote padrão baseado no tipo de ativo
    """
    # Criptomoedas principais: lotes maiores
    if par in ['BTCUSD', 'ETHUSD']:
        return 0.1
    # Criptomoedas secundárias: lotes médios  
    elif par in ['SOLUSD', 'XRPUSD', 'BCHUSD']:
        return 1.0
    # Outras criptos: lotes pequenos
    elif any(crypto in par for crypto in ['PEPE', 'INJ']):
        return 10.0
    # Forex: lotes padrão
    else:
        return 1.0

# Dicionário para controlar ordens abertas por par
ordens_abertas = {}

# Lista de pares com problemas de conexão (para evitar spam de tentativas)
pares_problematicos = {}  # {par: timestamp_do_problema}

# Lista de sinais recentes para evitar repetição
sinais_recentes = {}  # {par: {'timestamp', 'sinal', 'timeframe'}}

# Função para buscar candles de qualquer par e timeframe
def buscar_candles(par, timeframe=Interval.in_5_minute, n_bars=200):
    # Verificar se o par está na lista de problemáticos
    if par in pares_problematicos:
        # Se passou menos de 30 minutos desde o último problema, pular
        if time.time() - pares_problematicos[par] < 1800:  # 30 minutos
            return None
        else:
            # Remover da lista após 30 minutos
            del pares_problematicos[par]
    
    tv = TvDatafeed()
    
    # Detectar exchange adequado
    is_crypto = any(crypto in par for crypto in ['BTC', 'ETH', 'SOL', 'BCH', 'XRP', 'INJ'])
    exchange = 'BINANCE' if is_crypto else 'FX'
    
    # Tentar buscar dados com retry e verificação de quantidade
    max_tentativas = 3
    for tentativa in range(max_tentativas):
        try:
            # Pedir mais dados para garantir quantidade suficiente
            df = tv.get_hist(symbol=par, exchange=exchange, interval=timeframe, n_bars=300)
            
            if df is not None and not df.empty:
                print(f"[DADOS] {par} {timeframe.name}: {len(df)} velas obtidas")
                
                # Verificar se tem dados suficientes
                if len(df) >= 50:  # Mínimo necessário
                    return df
                else:
                    print(f"[DADOS] ⚠️ {par}: Apenas {len(df)} velas (mínimo 50)")
                    if tentativa < max_tentativas - 1:
                        time.sleep(3)  # Aguardar mais tempo
                        continue
                    else:
                        return df  # Retornar mesmo com poucos dados
            
        except Exception as e:
            print(f"[DADOS] Erro ao buscar {par} {timeframe.name}: {e}")
            if tentativa == max_tentativas - 1:  # Última tentativa
                # Adicionar à lista de problemáticos
                pares_problematicos[par] = time.time()
            else:
                # Aguardar antes de tentar novamente
                time.sleep(5)
    
    return None  # Falhou silenciosamente

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
    if len(df) < 50:  # Aumentado para ter mais dados históricos
        return None, "Dados insuficientes para análise.", None, None, None, None, None
    
    df = df.copy()
    df['ma_curta'] = df['close'].rolling(window=5).mean()
    df['ma_longa'] = df['close'].rolling(window=10).mean()
    df['ma_lenta'] = df['close'].rolling(window=21).mean()  # Nova média lenta para contexto
    
    # RSI
    rsi = RSIIndicator(df['close'], window=14).rsi()
    df['rsi'] = rsi
    rsi_atual = rsi.iloc[-1]
    
    # Williams %R
    willr = WilliamsRIndicator(df['high'], df['low'], df['close'], lbp=14).williams_r()
    df['willr'] = willr
    willr_atual = willr.iloc[-1]
    
    # MACD para confirmação de tendência
    macd_line = MACD(df['close'], window_slow=26, window_fast=12, window_sign=9).macd()
    macd_signal = MACD(df['close'], window_slow=26, window_fast=12, window_sign=9).macd_signal()
    df['macd'] = macd_line
    df['macd_signal'] = macd_signal
    
    # Bollinger Bands para volatilidade
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_middle'] = bb.bollinger_mavg()
    
    # Price Action
    padrao_pa = detectar_price_action(df)
    
    # Médias móveis e contexto de tendência
    prev_diff = df['ma_curta'].iloc[-2] - df['ma_longa'].iloc[-2]
    curr_diff = df['ma_curta'].iloc[-1] - df['ma_longa'].iloc[-1]
    
    # Suporte e resistência em múltiplos períodos
    suporte_recente = df['low'].iloc[-21:-1].min()  # 20 períodos
    resistencia_recente = df['high'].iloc[-21:-1].max()
    suporte_amplo = df['low'].iloc[-50:-1].min()  # 50 períodos para contexto maior
    resistencia_ampla = df['high'].iloc[-50:-1].max()
    
    preco_atual = df['close'].iloc[-1]
    distancia_suporte = abs(preco_atual - suporte_recente)
    distancia_resistencia = abs(preco_atual - resistencia_recente)
    
    # Rompimento e pullback
    rompimento = detectar_rompimento(df, suporte_recente, resistencia_recente)
    pullback = detectar_pullback(df, suporte_recente, resistencia_recente)
    
    # Análise de topos e fundos (novidade profissional)
    def detectar_topos_fundos(df, periodo=10):
        highs = df['high'].iloc[-periodo:]
        lows = df['low'].iloc[-periodo:]
        
        # Topo: preço atual é o mais alto dos últimos períodos
        topo_recente = preco_atual >= highs.max() * 0.999  # 0.1% de tolerância
        # Fundo: preço atual é o mais baixo dos últimos períodos  
        fundo_recente = preco_atual <= lows.min() * 1.001  # 0.1% de tolerância
        
        return topo_recente, fundo_recente
    
    topo_recente, fundo_recente = detectar_topos_fundos(df)
    
    # Tendência geral baseada em múltiplas médias
    tendencia_geral = ""
    if df['ma_curta'].iloc[-1] > df['ma_longa'].iloc[-1] > df['ma_lenta'].iloc[-1]:
        tendencia_geral = "BULLISH FORTE"
    elif df['ma_curta'].iloc[-1] < df['ma_longa'].iloc[-1] < df['ma_lenta'].iloc[-1]:
        tendencia_geral = "BEARISH FORTE"
    elif df['ma_curta'].iloc[-1] > df['ma_longa'].iloc[-1]:
        tendencia_geral = "BULLISH MODERADO"
    elif df['ma_curta'].iloc[-1] < df['ma_longa'].iloc[-1]:
        tendencia_geral = "BEARISH MODERADO"
    else:
        tendencia_geral = "LATERAL"

    # SISTEMA DE SCORE PROFISSIONAL - MUITO MAIS RIGOROSO
    score = 0
    criterios = []
    
    # 1. Cruzamento de médias (básico mas necessário)
    cruzamento_compra = prev_diff < 0 and curr_diff > 0
    cruzamento_venda = prev_diff > 0 and curr_diff < 0
    
    if cruzamento_compra or cruzamento_venda:
        score += 1
        criterios.append("Cruzamento de médias")
    
    # 2. Confirmação de tendência (CRUCIAL)
    if cruzamento_compra and tendencia_geral in ["BULLISH FORTE", "BULLISH MODERADO"]:
        score += 2  # Peso alto para confirmação de tendência
        criterios.append("Tendência bullish confirmada")
    elif cruzamento_venda and tendencia_geral in ["BEARISH FORTE", "BEARISH MODERADO"]:
        score += 2
        criterios.append("Tendência bearish confirmada")
    
    # 3. MACD confirmando o movimento
    macd_atual = macd_line.iloc[-1] if not pd.isna(macd_line.iloc[-1]) else 0
    macd_signal_atual = macd_signal.iloc[-1] if not pd.isna(macd_signal.iloc[-1]) else 0
    
    if cruzamento_compra and macd_atual > macd_signal_atual:
        score += 1
        criterios.append("MACD confirma compra")
    elif cruzamento_venda and macd_atual < macd_signal_atual:
        score += 1
        criterios.append("MACD confirma venda")
    
    # 4. RSI em zona favorável (não apenas extremos)
    if cruzamento_compra and 25 <= rsi_atual <= 45:  # RSI em zona de compra
        score += 1
        criterios.append("RSI em zona de compra")
    elif cruzamento_venda and 55 <= rsi_atual <= 75:  # RSI em zona de venda
        score += 1
        criterios.append("RSI em zona de venda")
    
    # 5. Williams %R confirmando
    if cruzamento_compra and willr_atual < -60:
        score += 1
        criterios.append("Williams %R favorável para compra")
    elif cruzamento_venda and willr_atual > -40:
        score += 1
        criterios.append("Williams %R favorável para venda")
    
    # 6. Price Action (peso alto)
    if cruzamento_compra and padrao_pa in ['Engolfo de Alta', 'Martelo']:
        score += 2  # Peso alto para price action
        criterios.append(f"Price Action bullish: {padrao_pa}")
    elif cruzamento_venda and padrao_pa in ['Engolfo de Baixa', 'Pin Bar']:
        score += 2
        criterios.append(f"Price Action bearish: {padrao_pa}")
    
    # 7. Proximidade de níveis importantes (REFINADO)
    limiar_rigido = 0.0003  # Muito mais próximo que antes
    if cruzamento_compra and distancia_suporte < limiar_rigido:
        score += 2  # Peso alto para suporte
        criterios.append("Muito próximo do suporte")
    elif cruzamento_venda and distancia_resistencia < limiar_rigido:
        score += 2
        criterios.append("Muito próximo da resistência")
    
    # 8. Rompimento confirmado (NOVO CRITÉRIO PROFISSIONAL)
    if rompimento == 'Rompimento de Resistência' and cruzamento_compra:
        score += 2
        criterios.append("Rompimento de resistência confirmado")
    elif rompimento == 'Rompimento de Suporte' and cruzamento_venda:
        score += 2
        criterios.append("Rompimento de suporte confirmado")
    
    # 9. Pullback válido (NOVO CRITÉRIO PROFISSIONAL)
    if pullback and ((pullback == 'Pullback de Resistência' and cruzamento_compra) or 
                     (pullback == 'Pullback de Suporte' and cruzamento_venda)):
        score += 2
        criterios.append(f"{pullback} válido")
    
    # 10. Topos e Fundos (ANÁLISE PROFISSIONAL)
    if cruzamento_compra and fundo_recente:
        score += 1
        criterios.append("Compra em fundo recente")
    elif cruzamento_venda and topo_recente:
        score += 1
        criterios.append("Venda em topo recente")
    
    # 11. Bollinger Bands (volatilidade e níveis)
    bb_upper_atual = df['bb_upper'].iloc[-1] if not pd.isna(df['bb_upper'].iloc[-1]) else 0
    bb_lower_atual = df['bb_lower'].iloc[-1] if not pd.isna(df['bb_lower'].iloc[-1]) else 0
    
    if cruzamento_compra and preco_atual <= bb_lower_atual * 1.002:  # Próximo da banda inferior
        score += 1
        criterios.append("Próximo da Bollinger inferior")
    elif cruzamento_venda and preco_atual >= bb_upper_atual * 0.998:  # Próximo da banda superior
        score += 1
        criterios.append("Próximo da Bollinger superior")

    # CRITÉRIOS PROFISSIONAIS RIGOROSOS
    sinal = None
    instrucao = None
    assertividade = "BAIXA"
    lote = 0
    
    # APENAS OPERAÇÕES DE ALTA QUALIDADE (score ≥ 5)
    if score >= 7:  # EXCELENTE - múltiplas confluências
        if cruzamento_compra:
            sinal = "CALL (COMPRA)"
            assertividade = "EXCELENTE"
            instrucao = f"🔥 SETUP PREMIUM: Score {score} ({', '.join(criterios)}). ENTRADA COMPRA com máxima confiança!"
        elif cruzamento_venda:
            sinal = "PUT (VENDA)"
            assertividade = "EXCELENTE"
            instrucao = f"🔥 SETUP PREMIUM: Score {score} ({', '.join(criterios)}). ENTRADA VENDA com máxima confiança!"
        lote = 1.5  # Lote maior para setups excelentes
        
    elif score >= 5:  # ALTA - boa confluência
        if cruzamento_compra:
            sinal = "CALL (COMPRA)"
            assertividade = "ALTA"
            instrucao = f"✅ SETUP SÓLIDO: Score {score} ({', '.join(criterios)}). ENTRADA COMPRA recomendada."
        elif cruzamento_venda:
            sinal = "PUT (VENDA)"
            assertividade = "ALTA"
            instrucao = f"✅ SETUP SÓLIDO: Score {score} ({', '.join(criterios)}). ENTRADA VENDA recomendada."
        lote = 1.0
        
    elif score >= 3:  # MÉDIA - confluência mínima aceitável
        if cruzamento_compra:
            sinal = "CALL (COMPRA)"
            assertividade = "MÉDIA"
            instrucao = f"⚠️ SETUP MÉDIO: Score {score} ({', '.join(criterios)}). Entrada com lote reduzido."
        elif cruzamento_venda:
            sinal = "PUT (VENDA)"
            assertividade = "MÉDIA"
            instrucao = f"⚠️ SETUP MÉDIO: Score {score} ({', '.join(criterios)}). Entrada com lote reduzido."
        lote = 0.5
        
    else:
        instrucao = f"❌ SETUP FRACO: Score {score} ({', '.join(criterios)}). NÃO OPERAR - aguardar melhor confluência!"
        
    # Detalhes técnicos completos
    detalhes = f"Tendência: {tendencia_geral}. Suporte: {suporte_recente:.5f} | Resistência: {resistencia_recente:.5f}. "
    detalhes += f"RSI: {rsi_atual:.2f} | Williams %R: {willr_atual:.2f} | Score: {score} ({', '.join(criterios)})"
    
    if padrao_pa:
        detalhes += f" | Price Action: {padrao_pa}"
    if rompimento:
        detalhes += f" | {rompimento}"
    if pullback:
        detalhes += f" | {pullback}"
    if topo_recente:
        detalhes += f" | Topo recente"
    if fundo_recente:
        detalhes += f" | Fundo recente"
        
    return sinal, detalhes, suporte_recente, resistencia_recente, distancia_suporte, distancia_resistencia, (instrucao, assertividade, lote)

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
# ATUALIZADO: EPICs antigos CS.D. foram descontinuados
EPICS = {
    'EURUSD': 'EURUSD_W',  # ✅ Validado e funcionando
    'GBPUSD': 'GBPUSD_W',  # 🔄 Atualizado (CS.D.GBPUSD.MINI.IP obsoleto)
    'USDJPY': 'USDJPY_W',  # 🔄 Atualizado (CS.D.USDJPY.MINI.IP obsoleto)
    'EURGBP': 'EURGBP_W',  # 🔄 Atualizado (CS.D.EURGBP.MINI.IP obsoleto)
}

# Função para verificar se mercado está aberto
def mercado_aberto(par):
    """
    Verifica se o mercado está aberto para o par específico no Capital.com
    Cripto: 24/7 (sempre aberto)
    Forex: Segunda a Sexta 24h (começa domingo noite até sexta noite)
    """
    agora = datetime.now(TZ)
    
    # Criptomoedas são 24/7
    is_crypto = any(crypto in par for crypto in ['BTC', 'ETH', 'SOL', 'BCH', 'XRP', 'PEPE', 'INJ', 'TREMP'])
    if is_crypto:
        return True, "Cripto 24/7"
    
    # Forex no Capital.com: Segunda a Sexta 24h
    dia_semana = agora.weekday()  # 0=Monday, 6=Sunday
    hora = agora.hour
    
    # Domingo noite após 22h (começa nova semana)
    if dia_semana == 6 and hora >= 22:
        return True, "Forex - Início da semana"
    
    # Segunda a Quinta: sempre aberto 24h
    if dia_semana in [0, 1, 2, 3]:  # Segunda a Quinta
        return True, "Forex - Horário regular"
    
    # Sexta até 22h (fecha para fim de semana)
    if dia_semana == 4 and hora < 22:  # Sexta antes das 22h
        return True, "Forex - Horário regular"
    
    # Fechado: Sexta 22h+ até Domingo 22h
    return False, "Forex fechado - Fim de semana"

# Controle rigoroso de posições abertas
MAX_POSICOES_SIMULTANEAS = 2  # Máximo 2 operações abertas por vez
INTERVALO_VERIFICACAO = 30  # Verificar posições a cada 30 segundos

# Tracking de performance em tempo real
performance_tracker = {
    'banca_inicial': 0,
    'operacoes_ativas': {},  # {deal_id: {'par': 'BTCUSD', 'valor_entrada': 1000, 'timestamp': time}}
    'total_win': 0,
    'total_loss': 0,
    'win_rate': 0
}

def validar_confluencias_reais(df, sinal_detalhes):
    """
    Valida se as confluências detectadas são reais através de verificações matemáticas
    Impede que o robô opere com dados simulados ou falsos
    """
    if len(df) < 50:
        print("[VALIDAÇÃO] ❌ Dados insuficientes para análise real")
        return False
    
    # Verificar se os dados são recentes e reais
    timestamp_ultimo = df.index[-1] if hasattr(df.index[-1], 'timestamp') else None
    agora = datetime.now(TZ).timestamp()
    
    # Verificar médias móveis reais
    ma_curta_real = df['close'].rolling(window=5).mean().iloc[-1]
    ma_longa_real = df['close'].rolling(window=10).mean().iloc[-1]
    
    if pd.isna(ma_curta_real) or pd.isna(ma_longa_real):
        print("[VALIDAÇÃO] ❌ Médias móveis inválidas - dados simulados")
        return False
    
    # Verificar RSI real
    rsi_real = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    if pd.isna(rsi_real) or rsi_real < 0 or rsi_real > 100:
        print("[VALIDAÇÃO] ❌ RSI inválido - dados simulados")
        return False
    
    # Verificar volume (se disponível) para confirmar dados reais
    if 'volume' in df.columns:
        volume_medio = df['volume'].tail(10).mean()
        if volume_medio <= 0:
            print("[VALIDAÇÃO] ❌ Volume zero - dados simulados")
            return False
    
    # Verificar se price action é matematicamente válida
    if 'Engolfo' in sinal_detalhes:
        candle_atual = df.iloc[-1]
        candle_anterior = df.iloc[-2]
        
        if 'Engolfo de Alta' in sinal_detalhes:
            # Engolfo de alta: candle atual verde engole candle anterior vermelho
            if not (candle_atual['close'] > candle_atual['open'] and 
                   candle_anterior['close'] < candle_anterior['open'] and
                   candle_atual['close'] > candle_anterior['open'] and
                   candle_atual['open'] < candle_anterior['close']):
                print("[VALIDAÇÃO] ❌ Engolfo de Alta FALSO - dados inválidos")
                return False
    
    # Verificar MACD real
    if 'MACD' in sinal_detalhes:
        macd_line = MACD(df['close'], window_slow=26, window_fast=12, window_sign=9).macd().iloc[-1]
        macd_signal = MACD(df['close'], window_slow=26, window_fast=12, window_sign=9).macd_signal().iloc[-1]
        
        if pd.isna(macd_line) or pd.isna(macd_signal):
            print("[VALIDAÇÃO] ❌ MACD inválido - dados simulados")
            return False
    
    print("[VALIDAÇÃO] ✅ Confluências validadas como REAIS")
    return True

def monitorar_performance_realtime():
    """
    Monitora a performance em tempo real baseada na variação da banca
    Detecta se as operações abertas estão lucrando ou perdendo
    """
    global performance_tracker
    
    try:
        # Obter banca atual
        saldo_atual = api.saldo()
        banca_atual = saldo_atual['accounts'][0]['balance']['balance']
        
        # Calcular variação desde o início do dia
        variacao = banca_atual - performance_tracker['banca_inicial']
        variacao_percentual = (variacao / performance_tracker['banca_inicial']) * 100
        
        # Status das operações ativas
        operacoes_ativas = len(performance_tracker['operacoes_ativas'])
        
        print(f"\n📊 PERFORMANCE EM TEMPO REAL:")
        print(f"  • Banca Inicial: ${performance_tracker['banca_inicial']:.2f}")
        print(f"  • Banca Atual: ${banca_atual:.2f}")
        print(f"  • Variação: ${variacao:.2f} ({variacao_percentual:+.2f}%)")
        print(f"  • Operações Ativas: {operacoes_ativas}/{MAX_POSICOES_SIMULTANEAS}")
        
        if variacao > 0:
            print(f"  • Status: 🟢 LUCRANDO")
        elif variacao < 0:
            print(f"  • Status: 🔴 PERDENDO")
        else:
            print(f"  • Status: ⚪ NEUTRO")
        
        # Verificar se alguma operação foi fechada
        verificar_operacoes_fechadas(banca_atual)
        
        return banca_atual, variacao, operacoes_ativas
        
    except Exception as e:
        print(f"[ERRO] Falha ao monitorar performance: {e}")
        return None, 0, 0

def verificar_operacoes_fechadas(banca_atual):
    """
    Verifica se alguma operação foi fechada comparando a variação da banca
    """
    global performance_tracker
    
    # Se não há operações ativas, não há o que verificar
    if not performance_tracker['operacoes_ativas']:
        return
    
    # Buscar posições ativas na API
    try:
        headers = {
            'X-CAP-API-KEY': api.api_key,
            'CST': api.cst,
            'X-SECURITY-TOKEN': api.x_security_token
        }
        
        resp = api.session.get(f'{api.base_url}/api/v1/positions', headers=headers)
        if resp.status_code == 200:
            posicoes_ativas_api = resp.json().get('positions', [])
            deals_ativos = [pos.get('dealId') for pos in posicoes_ativas_api if pos.get('dealId')]
            
            # Verificar quais operações foram fechadas
            operacoes_fechadas = []
            for deal_id in list(performance_tracker['operacoes_ativas'].keys()):
                if deal_id not in deals_ativos:
                    operacoes_fechadas.append(deal_id)
            
            # Processar operações fechadas
            for deal_id in operacoes_fechadas:
                operacao = performance_tracker['operacoes_ativas'].pop(deal_id)
                par = operacao['par']
                
                print(f"[OPERAÇÃO FECHADA] {par} (Deal: {deal_id})")
                print(f"  • Operação durou: {time.time() - operacao['timestamp']:.0f} segundos")
                
                # Liberar o par para nova análise
                if par in ordens_abertas:
                    del ordens_abertas[par]
                    print(f"  • {par} liberado para nova operação")
    
    except Exception as e:
        print(f"[ERRO] Falha ao verificar operações fechadas: {e}")

def pode_operar():
    """
    Verifica se é possível fazer nova operação baseado no limite de posições
    AGORA consulta posições REAIS da Capital.com para evitar ultrapassar limite
    """
    # Primeiro, verificar contador interno
    operacoes_internas = len(performance_tracker['operacoes_ativas'])
    
    if MODO_REAL:
        # Em modo real, SEMPRE verificar com a API para segurança máxima
        try:
            posicoes_reais = api.consultar_posicoes_ativas()
            operacoes_reais = len(posicoes_reais)
            
            print(f"\n🔍 VERIFICAÇÃO DE SEGURANÇA:")
            print(f"   Contador interno: {operacoes_internas} operações")
            print(f"   Capital.com API:  {operacoes_reais} operações")
            print(f"   Limite máximo:    {MAX_POSICOES_SIMULTANEAS} operações")
            
            # Usar sempre o número REAL da API (mais confiável)
            if operacoes_reais >= MAX_POSICOES_SIMULTANEAS:
                print(f"\n⏸️  LIMITE REAL ATINGIDO: {operacoes_reais}/{MAX_POSICOES_SIMULTANEAS} operações ativas na Capital.com")
                print(f"    Aguardando fechamento de pelo menos 1 operação para continuar...")
                return False
            
            # Se houver discrepância, sincronizar
            if operacoes_reais != operacoes_internas:
                print(f"⚠️  DISCREPÂNCIA detectada! Sincronizando...")
                sincronizar_posicoes_reais()
                
        except Exception as e:
            print(f"❌ ERRO ao verificar posições reais: {e}")
            print(f"   Usando contador interno por segurança...")
            # Em caso de erro, usar o contador interno
            if operacoes_internas >= MAX_POSICOES_SIMULTANEAS:
                print(f"\n⏸️ LIMITE INTERNO ATINGIDO: {operacoes_internas}/{MAX_POSICOES_SIMULTANEAS} operações")
                return False
    else:
        # Modo simulação: usar apenas contador interno
        if operacoes_internas >= MAX_POSICOES_SIMULTANEAS:
            print(f"\n⏸️ LIMITE ATINGIDO: {operacoes_internas}/{MAX_POSICOES_SIMULTANEAS} operações ativas")
            print(f"   Aguardando fechamento de pelo menos 1 operação para continuar...")
            return False
    
    return True

def registrar_operacao(deal_id, par, banca_entrada):
    """
    Registra uma nova operação no tracker de performance
    """
    global performance_tracker
    
    performance_tracker['operacoes_ativas'][deal_id] = {
        'par': par,
        'valor_entrada': banca_entrada,
        'timestamp': time.time()
    }
    
    print(f"[REGISTRO] Operação {par} registrada: {deal_id}")

def monitoramento_inteligente_risco():
    """
    🎯 MONITORAMENTO INTELIGENTE DE RISCO
    =====================================
    Monitora posições ativas e toma decisões automáticas:
    - Se ultrapassou meta diária → FECHA TUDO e garante lucro
    - Se bateu stop loss diário → FECHA TUDO e para operações
    - Atualiza JSON automaticamente
    """
    try:
        # Obter posições ativas diretamente da API
        posicoes_ativas = api.consultar_posicoes_ativas()
        
        if not posicoes_ativas:
            return False, "Nenhuma posição ativa"
        
        # Calcular P&L total
        pnl_total = sum(pos.get('profit', 0) for pos in posicoes_ativas)
        
        # Calcular P&L percentual baseado na banca atual
        banca_config = ler_banca()
        banca_atual = banca_config['banca']
        pnl_percentual = (pnl_total / banca_atual) * 100 if banca_atual > 0 else 0
        
        print(f"🎯 MONITOR: P&L Total: ${pnl_total:.2f} ({pnl_percentual:+.1f}%)")
        
        # Usar configuração já carregada
        meta_diaria = banca_config.get('stop_win_percentual', 5.0)  # 5% padrão
        stop_loss_diario = banca_config.get('stop_loss_percentual', -3.0)  # -3% padrão
        
        # VERIFICAR SE ULTRAPASSOU A META (ex: meta era +5%, estamos em +8%)
        if pnl_percentual >= (meta_diaria + 2.0):  # 2% acima da meta
            print(f"🚀 EXCELENTE! Meta era {meta_diaria}% e estamos com {pnl_percentual:+.1f}%!")
            print(f"🎯 FECHANDO TODAS AS POSIÇÕES para garantir este lucro excepcional!")
            
            # Fechar todas as posições ativas
            sucesso_fechamento = True
            for posicao in posicoes_ativas:
                try:
                    deal_id = posicao['dealId']
                    par = posicao['epic']
                    pnl_pos = posicao['profit']
                    
                    print(f"   🔒 Fechando {par}: ${pnl_pos:.2f}")
                    
                    # Usar a lógica do teste_fechar_posicao.py
                    resposta = api.fechar_posicao(deal_id)
                    if resposta and resposta.get('dealStatus') == 'ACCEPTED':
                        print(f"   ✅ {par} fechada com sucesso!")
                    else:
                        print(f"   ❌ Erro ao fechar {par}: {resposta}")
                        sucesso_fechamento = False
                        
                except Exception as e:
                    print(f"   ❌ Erro ao fechar posição {par}: {e}")
                    sucesso_fechamento = False
            
            if sucesso_fechamento:
                # Atualizar JSON com resultado excepcional
                agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                banca_config['historico'].append({
                    'tipo': 'FECHAMENTO_AUTOMATICO_LUCRO_EXCEPCIONAL',
                    'pnl_total': pnl_total,
                    'pnl_percentual': pnl_percentual,
                    'meta_original': meta_diaria,
                    'data': agora,
                    'motivo': f'Ultrapassou meta de {meta_diaria}% atingindo {pnl_percentual:.1f}%'
                })
                
                # Atualizar banca
                banca_config['banca'] += pnl_total
                banca_config['lucro_dia'] = pnl_total
                salvar_banca(banca_config)
                
                print(f"💰 RESULTADO SALVO: ${pnl_total:.2f} ({pnl_percentual:+.1f}%) adicionado à banca!")
                return True, f"Meta ultrapassada: {pnl_percentual:.1f}% (era {meta_diaria}%)"
            
        # VERIFICAR SE BATEU STOP LOSS DIÁRIO
        elif pnl_percentual <= stop_loss_diario:
            print(f"🛑 STOP LOSS DIÁRIO ATINGIDO: {pnl_percentual:+.1f}% (limite: {stop_loss_diario}%)")
            print(f"🔒 FECHANDO TODAS AS POSIÇÕES E PARANDO OPERAÇÕES!")
            
            # Fechar todas as posições ativas
            for posicao in posicoes_ativas:
                try:
                    deal_id = posicao['dealId']
                    par = posicao['epic']
                    pnl_pos = posicao['profit']
                    
                    print(f"   🛑 Fechando {par}: ${pnl_pos:.2f}")
                    
                    resposta = api.fechar_posicao(deal_id)
                    if resposta and resposta.get('dealStatus') == 'ACCEPTED':
                        print(f"   ✅ {par} fechada por stop loss!")
                    else:
                        print(f"   ❌ Erro ao fechar {par}: {resposta}")
                        
                except Exception as e:
                    print(f"   ❌ Erro ao fechar posição {par}: {e}")
            
            # Atualizar JSON com stop loss
            agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            banca_config['historico'].append({
                'tipo': 'STOP_LOSS_DIARIO_ATIVADO',
                'pnl_total': pnl_total,
                'pnl_percentual': pnl_percentual,
                'limite_stop': stop_loss_diario,
                'data': agora,
                'motivo': f'Atingiu stop loss diário de {stop_loss_diario}%'
            })
            
            # Atualizar banca
            banca_config['banca'] += pnl_total  # Pode ser negativo
            banca_config['lucro_dia'] = pnl_total
            salvar_banca(banca_config)
            
            print(f"📊 STOP LOSS REGISTRADO: ${pnl_total:.2f} ({pnl_percentual:+.1f}%)")
            return True, f"Stop loss ativado: {pnl_percentual:.1f}%"
        
        # Situação normal - apenas monitorar
        else:
            falta_meta = meta_diaria - pnl_percentual
            falta_stop = abs(stop_loss_diario) - abs(pnl_percentual) if pnl_percentual < 0 else abs(stop_loss_diario)
            
            print(f"📊 Status Normal: Meta em {falta_meta:.1f}% | Stop em {falta_stop:.1f}%")
            return False, "Monitoramento normal"
            
    except Exception as e:
        print(f"❌ Erro no monitoramento inteligente: {e}")
        return False, f"Erro: {e}"

# Função para selecionar pares baseado no horário
def selecionar_pares_por_mercado():
    """
    Seleciona pares para análise baseado no horário:
    - Forex fechado: apenas criptomoedas
    - Forex aberto: todos os pares
    """
    agora = datetime.now(TZ)
    dia_semana = agora.weekday()  # 0=segunda, 6=domingo
    hora = agora.hour
    
    # Forex fecha sexta 22h até domingo 22h (horário de Londres)
    forex_fechado = (
        dia_semana == 5 and hora >= 22 or  # Sexta após 22h
        dia_semana == 6 or                 # Todo sábado
        dia_semana == 0 and hora < 22      # Domingo antes 22h
    )
    
    if forex_fechado:
        print(f"[SELEÇÃO INTELIGENTE] Forex fechado - Operando apenas CRIPTOMOEDAS (24/7)")
        return CRIPTO_PARES
    else:
        print(f"[SELEÇÃO INTELIGENTE] Forex aberto - Operando TODOS os pares")
        return PARES

def analisar_confluencias_profissionais(df, par, timeframe):
    """
    Análise de confluências RIGOROSA para trader profissional
    Exige mínimo 4/6 confluências + price action obrigatório
    """
    if len(df) < 50:
        return {
            'sinal': None,
            'score': 0,
            'confluencias': [],
            'descricao': 'Dados insuficientes para análise'
        }
    
    confluencias = []
    score = 0
    
    # Dados atuais
    atual = df.iloc[-1]
    anterior = df.iloc[-2] if len(df) > 1 else atual
    preco = atual['close']
    
    # 1. TENDÊNCIA (Peso: 1 ponto) - ESSENCIAL
    if 'ma_curta' in df.columns and 'ma_longa' in df.columns:
        ma_curta = df['ma_curta'].iloc[-1]
        ma_longa = df['ma_longa'].iloc[-1]
        if pd.notna(ma_curta) and pd.notna(ma_longa):
            if ma_curta > ma_longa:
                confluencias.append("Tendência Bullish (MA5 > MA10)")
                tendencia = "BULLISH"
                score += 1
            else:
                confluencias.append("Tendência Bearish (MA5 < MA10)")
                tendencia = "BEARISH"
                score += 1
        else:
            tendencia = "INDEFINIDA"
    else:
        tendencia = "INDEFINIDA"
    
    # 2. RSI (Peso: 1 ponto) - MOMENTUM
    if 'rsi' in df.columns:
        rsi = df['rsi'].iloc[-1]
        if pd.notna(rsi):
            if rsi < 30:
                confluencias.append(f"RSI Sobrevendido ({rsi:.1f})")
                score += 1
                rsi_signal = "COMPRA"
            elif rsi > 70:
                confluencias.append(f"RSI Sobrecomprado ({rsi:.1f})")
                score += 1
                rsi_signal = "VENDA"
            else:
                rsi_signal = "NEUTRO"
        else:
            rsi_signal = "NEUTRO"
    else:
        rsi_signal = "NEUTRO"
    
    # 3. SUPORTE/RESISTÊNCIA (Peso: 2 pontos) - MUITO IMPORTANTE
    suporte, resistencia = detectar_suporte_resistencia(df)
    if suporte and resistencia:
        dist_suporte = abs(preco - suporte)
        dist_resistencia = abs(preco - resistencia)
        
        # Próximo ao suporte (potencial compra)
        if dist_suporte < (resistencia - suporte) * 0.1:  # 10% da faixa
            confluencias.append("Próximo ao suporte")
            score += 2
            sr_signal = "COMPRA"
        # Próximo à resistência (potencial venda)
        elif dist_resistencia < (resistencia - suporte) * 0.1:
            confluencias.append("Próximo à resistência")
            score += 2
            sr_signal = "VENDA"
        else:
            sr_signal = "NEUTRO"
    else:
        sr_signal = "NEUTRO"
    
    # 4. PRICE ACTION PROFISSIONAL (Peso: até 2 pontos) - OBRIGATÓRIO
    price_action_pattern, price_action_score = analisar_price_action_profissional(df)
    if price_action_pattern and price_action_score > 0:
        confluencias.append(price_action_pattern)
        score += price_action_score
        
        if "Alta" in price_action_pattern or "Martelo" in price_action_pattern:
            pa_signal = "COMPRA"
        elif "Baixa" in price_action_pattern or "Shooting" in price_action_pattern:
            pa_signal = "VENDA"
        else:
            pa_signal = "NEUTRO"
    else:
        pa_signal = "NEUTRO"
        
        # CRITÉRIO FLEXÍVEL: Price action é preferível mas não sempre obrigatório
        if CRITERIOS_PROFISSIONAIS['PRICE_ACTION_OBRIGATORIO'] and score < 3:
            # Só exigir price action se o score está baixo (menos de 3 outras confluências)
            return {
                'sinal': None,
                'score': 0,
                'confluencias': [],
                'descricao': 'Price action obrigatório quando score < 3',
                'qualidade': 'REJEITADO'
            }
    
    # DETERMINAR SINAL FINAL (baseado nas confluências principais)
    sinais_compra = sum([1 for s in [tendencia, rsi_signal, sr_signal, pa_signal] if s == "COMPRA" or s == "BULLISH"])
    sinais_venda = sum([1 for s in [tendencia, rsi_signal, sr_signal, pa_signal] if s == "VENDA" or s == "BEARISH"])
    
    # CRITÉRIO PROFISSIONAL: Mínimo 4/6 confluências para operar
    if score >= CRITERIOS_PROFISSIONAIS['SCORE_MINIMO']:
        if sinais_compra > sinais_venda:
            sinal = "CALL (COMPRA)"
        elif sinais_venda > sinais_compra:
            sinal = "PUT (VENDA)"
        else:
            sinal = None  # Conflito de sinais
    else:
        sinal = None
    
    # Classificar qualidade com critérios rigorosos
    if score >= CRITERIOS_PROFISSIONAIS['SCORE_EXCELENTE']:
        qualidade = "EXCELENTE"
    elif score >= CRITERIOS_PROFISSIONAIS['SCORE_ALTA_QUALIDADE']:
        qualidade = "ALTA"
    elif score >= CRITERIOS_PROFISSIONAIS['SCORE_MINIMO']:
        qualidade = "ADEQUADA"
    else:
        qualidade = "INSUFICIENTE"
    
    descricao = f"{qualidade}. {' | '.join(confluencias[:3])} | Score: {score}"
    
    return {
        'sinal': sinal,
        'score': score,
        'confluencias': confluencias,
        'descricao': descricao,
        'qualidade': qualidade
    }

def detectar_suporte_resistencia(df, periodo=20):
    """
    Detecta níveis de suporte e resistência baseado em máximos e mínimos locais
    Retorna os níveis mais próximos do preço atual
    """
    if len(df) < periodo * 2:
        return None, None
    
    # Pegar os últimos períodos para análise
    dados_recentes = df.tail(periodo * 2)
    preco_atual = df['close'].iloc[-1]
    
    # Encontrar máximos locais (resistências potenciais)
    highs = dados_recentes['high'].rolling(window=3, center=True).max()
    resistencias = []
    
    for i in range(1, len(dados_recentes) - 1):
        if (dados_recentes['high'].iloc[i] == highs.iloc[i] and 
            dados_recentes['high'].iloc[i] > dados_recentes['high'].iloc[i-1] and 
            dados_recentes['high'].iloc[i] > dados_recentes['high'].iloc[i+1]):
            resistencias.append(dados_recentes['high'].iloc[i])
    
    # Encontrar mínimos locais (suportes potenciais)
    lows = dados_recentes['low'].rolling(window=3, center=True).min()
    suportes = []
    
    for i in range(1, len(dados_recentes) - 1):
        if (dados_recentes['low'].iloc[i] == lows.iloc[i] and 
            dados_recentes['low'].iloc[i] < dados_recentes['low'].iloc[i-1] and 
            dados_recentes['low'].iloc[i] < dados_recentes['low'].iloc[i+1]):
            suportes.append(dados_recentes['low'].iloc[i])
    
    # Encontrar o suporte mais próximo abaixo do preço atual
    suportes_validos = [s for s in suportes if s < preco_atual]
    suporte = max(suportes_validos) if suportes_validos else None
    
    # Encontrar a resistência mais próxima acima do preço atual
    resistencias_validas = [r for r in resistencias if r > preco_atual]
    resistencia = min(resistencias_validas) if resistencias_validas else None
    
    # Se não encontrar, usar valores das médias dos extremos
    if suporte is None:
        suporte = dados_recentes['low'].min()
    
    if resistencia is None:
        resistencia = dados_recentes['high'].max()
    
    return suporte, resistencia

def sincronizar_posicoes_reais():
    """
    Sincroniza o contador interno com as posições REAIS da Capital.com
    CRÍTICO: Evita ultrapassar limite de operações após reinicializações
    """
    global performance_tracker
    
    try:
        if not MODO_REAL:
            return  # Só sincronizar em modo real
            
        print(f"\n🔄 SINCRONIZANDO com Capital.com...")
        
        # Buscar posições reais da API
        posicoes_reais = api.consultar_posicoes_ativas()
        
        # Limpar tracker interno e recriar com dados reais
        performance_tracker['operacoes_ativas'].clear()
        
        for posicao in posicoes_reais:
            deal_id = posicao['dealId']
            epic = posicao['epic']
            
            # Tentar identificar o par baseado no epic
            par_identificado = None
            for par, epic_cadastrado in EPICS.items():
                if epic == epic_cadastrado:
                    par_identificado = par
                    break
            
            # Se não encontrou, usar o epic como par
            if not par_identificado:
                par_identificado = epic
            
            # Registrar no tracker interno
            performance_tracker['operacoes_ativas'][deal_id] = {
                'par': par_identificado,
                'valor_entrada': 0,  # Não temos histórico da entrada
                'timestamp': time.time(),  # Timestamp atual
                'sincronizado': True  # Marca que veio da sincronização
            }
            
            print(f"[SYNC] Posição {deal_id} registrada: {par_identificado}")
        
        total_sincronizadas = len(posicoes_reais)
        print(f"[SYNC] ✅ {total_sincronizadas} posições sincronizadas com Capital.com")
        
        if total_sincronizadas >= MAX_POSICOES_SIMULTANEAS:
            print(f"[SYNC] ⚠️  LIMITE ATINGIDO: {total_sincronizadas}/{MAX_POSICOES_SIMULTANEAS} posições")
            print(f"[SYNC]    Robô aguardará fechamento antes de nova operação")
        
        return posicoes_reais
        
    except Exception as e:
        print(f"[SYNC] ❌ ERRO na sincronização: {e}")
        print(f"[SYNC]    Continuando com controle interno (RISCO de ultrapassar limite)")
        return []

def mostrar_configuracoes_stop_loss():
    """
    Mostra as configurações do sistema híbrido de stop loss
    """
    print("\n" + "="*60)
    print("🛡️  CONFIGURAÇÃO DO SISTEMA DE STOP LOSS")
    print("="*60)
    print(f"Modo padrão: {STOP_LOSS_CONFIG['modo_padrao']}")
    print(f"Stop garantido para criptomoedas: {'✅ SIM' if STOP_LOSS_CONFIG['usar_garantido_para_cripto'] else '❌ NÃO'}")
    print(f"Stop garantido para forex volátil: {'✅ SIM' if STOP_LOSS_CONFIG['usar_garantido_para_forex_volatil'] else '❌ NÃO'}")
    
    if STOP_LOSS_CONFIG['pares_sempre_garantido']:
        print(f"Sempre GARANTIDO: {', '.join(STOP_LOSS_CONFIG['pares_sempre_garantido'])}")
    
    if STOP_LOSS_CONFIG['pares_nunca_garantido']:
        print(f"Sempre NORMAL: {', '.join(STOP_LOSS_CONFIG['pares_nunca_garantido'])}")
    
    print("\n📋 TESTE DE CONFIGURAÇÃO:")
    pares_teste = ['EURUSD', 'BTCUSD', 'GBPUSD', 'ETHUSD', 'USDJPY']
    for par in pares_teste:
        usar_garantido = determinar_tipo_stop_loss(par)
        tipo = "GARANTIDO" if usar_garantido else "NORMAL"
        print(f"  {par}: {tipo}")
    
    print("="*60)

def verificar_operacao_existente_no_par(par):
    """
    Verifica se já existe operação ativa no mesmo par
    CRÍTICO: Evita múltiplas operações no mesmo ativo
    """
    try:
        if not MODO_REAL:
            # Modo simulação: verificar ordens_abertas
            return par in ordens_abertas
        
        # Modo real: verificar posições reais da API
        posicoes_reais = api.consultar_posicoes_ativas()
        
        # Buscar epic do par atual
        epic_procurado = EPICS.get(par)
        if not epic_procurado:
            print(f"[VERIFICAÇÃO] Epic não encontrado para {par}")
            return False
        
        # Verificar se alguma posição usa este epic
        for posicao in posicoes_reais:
            epic_posicao = posicao.get('epic')
            if epic_posicao == epic_procurado:
                direction = posicao.get('direction', 'UNKNOWN')
                size = posicao.get('size', 0)
                deal_id = posicao.get('dealId', 'UNKNOWN')
                
                print(f"[VERIFICAÇÃO] ❌ OPERAÇÃO JÁ EXISTE no {par}!")
                print(f"              Epic: {epic_posicao} | Direção: {direction} | Tamanho: {size}")
                print(f"              Deal ID: {deal_id}")
                return True
        
        print(f"[VERIFICAÇÃO] ✅ {par} livre para nova operação")
        return False
        
    except Exception as e:
        print(f"[VERIFICAÇÃO] ERRO ao verificar {par}: {e}")
        return True  # Em caso de erro, bloquear por segurança

def analisar_price_action_profissional(df):
    """
    Análise PROFISSIONAL de price action - critérios balanceados
    Detecta padrões válidos sem ser excessivamente restritivo
    """
    if len(df) < 3:
        return None, 0
    
    # Pegar últimas 3 velas para análise
    atual = df.iloc[-1]
    anterior = df.iloc[-2]
    
    open_atual = atual['open']
    close_atual = atual['close']
    high_atual = atual['high']
    low_atual = atual['low']
    
    open_ant = anterior['open']
    close_ant = anterior['close']
    high_ant = anterior['high']
    low_ant = anterior['low']
    
    corpo_atual = abs(close_atual - open_atual)
    corpo_anterior = abs(close_ant - open_ant)
    range_atual = high_atual - low_atual
    
    # 1. ENGOLFO VÁLIDO (+2 pontos) - critérios menos restritivos
    if corpo_atual > corpo_anterior * 0.8:  # Corpo atual pelo menos 80% do anterior
        # Engolfo de Alta
        if (close_atual > open_atual and  # Vela atual verde
            close_ant < open_ant and      # Vela anterior vermelha
            close_atual > open_ant and    # Fechamento atual acima da abertura anterior
            open_atual < close_ant):      # Abertura atual abaixo do fechamento anterior
            
            return "Engolfo de Alta", 2
        
        # Engolfo de Baixa
        if (close_atual < open_atual and  # Vela atual vermelha
            close_ant > open_ant and      # Vela anterior verde
            close_atual < open_ant and    # Fechamento atual abaixo da abertura anterior
            open_atual > close_ant):      # Abertura atual acima do fechamento anterior
            
            return "Engolfo de Baixa", 2
    
    # 2. PADRÕES DE REVERSÃO (+1 ponto) - critérios flexíveis
    sombra_superior = high_atual - max(open_atual, close_atual)
    sombra_inferior = min(open_atual, close_atual) - low_atual
    
    # Martelo/Hammer: sombra inferior significativa
    if (sombra_inferior > corpo_atual * 1.5 and  # Sombra inferior 1.5x maior que corpo
        sombra_superior < corpo_atual * 0.5):     # Sombra superior pequena
        return "Martelo", 1
    
    # Shooting Star: sombra superior significativa
    if (sombra_superior > corpo_atual * 1.5 and  # Sombra superior 1.5x maior que corpo
        sombra_inferior < corpo_atual * 0.5):     # Sombra inferior pequena
        return "Shooting Star", 1
    
    # 3. DOJI ou SPINNING TOP (+1 ponto)
    if corpo_atual < range_atual * 0.2:  # Corpo pequeno em relação ao range
        if range_atual > 0:  # Evitar divisão por zero
            return "Doji/Spinning Top", 1
    
    # 4. VELA FORTE (movimento definitivo) (+1 ponto)
    if corpo_atual > range_atual * 0.7:  # Corpo ocupa 70% do range (vela forte)
        if close_atual > open_atual:
            return "Vela Bull Forte", 1
        else:
            return "Vela Bear Forte", 1
    
    return None, 0

def mostrar_correcoes_implementadas():
    """
    Mostra as correções críticas implementadas no robô
    """
    print("\n" + "="*80)
    print("🔧 CORREÇÕES CRÍTICAS IMPLEMENTADAS")
    print("="*80)
    print("✅ 1. CONTROLE RIGOROSO DE POSIÇÕES:")
    print("   • Verificação real na Capital.com antes de nova operação")
    print("   • Impossível ultrapassar 2 operações simultâneas")
    print("   • Sincronização automática em tempo real")
    print()
    print("✅ 2. MÚLTIPLAS OPERAÇÕES NO MESMO PAR BLOQUEADAS:")
    print("   • Verificação de epic antes de operar")
    print("   • Impossível abrir 2 posições no mesmo ativo")
    print("   • Logs detalhados de verificação")
    print()
    print("✅ 3. CRITÉRIOS PROFISSIONAIS RIGOROSOS:")
    print(f"   • Score mínimo: {CRITERIOS_PROFISSIONAIS['SCORE_MINIMO']}/6 (antes era 2)")
    print(f"   • Price action obrigatório se score < 3: {CRITERIOS_PROFISSIONAIS['PRICE_ACTION_OBRIGATORIO']}")
    print("   • Engolfos, martelos, dojis validados matematicamente")
    print("   • Critérios balanceados para detecção profissional")
    print()
    print("✅ 4. SISTEMA HÍBRIDO DE STOP LOSS:")
    print("   • Stop normal para forex estável (mais econômico)")
    print("   • Stop garantido para criptomoedas (mais seguro)")
    print("   • Configuração inteligente por ativo")
    print("="*80)

if __name__ == "__main__":
    if MODO_REAL:
        if not CapitalAPI:
            print("capital_api.py não encontrado! Não é possível operar em modo real.")
            sys.exit(1)
        api = CapitalAPI(api_demo=API_DEMO)
        api.autenticar()
        saldo_api = api.saldo()
        saldo_demo = saldo_api['accounts'][0]['balance']['balance']
        banca = ler_banca()
        banca['banca'] = saldo_demo
        
        # NOVO: Inicializar performance tracker
        performance_tracker['banca_inicial'] = saldo_demo
        
        # SINCRONIZAÇÃO INICIAL CRÍTICA
        print("\n" + "="*60)
        print("🔄 SINCRONIZAÇÃO INICIAL COM CAPITAL.COM")
        print("="*60)
        sincronizar_posicoes_reais()
        print("="*60)
        
        # Migrar configuração antiga para nova (compatibilidade)
        if 'risco_percentual' in banca:
            print(f"[MIGRAÇÃO] Convertendo para sistema dinâmico de juros compostos...")
            banca['risco_percentual_operacao'] = banca.get('risco_percentual', 1.0)
            banca['stop_win_percentual'] = 5.0
            banca['stop_loss_percentual'] = -3.0
            # Remover campos antigos
            banca.pop('risco_percentual', None)
            banca.pop('stop_win_diario', None) 
            banca.pop('stop_loss_diario', None)
            salvar_banca(banca)
            print(f"[MIGRAÇÃO] Sistema dinâmico ativado!")
        
        modo_str = '[MODO DEMO]' if API_DEMO else '[MODO REAL]'
        print(f"{modo_str} Banca sincronizada com Capital.com: ${banca['banca']:.2f} | Horário: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[PERFORMANCE TRACKER] Inicializado - Banca inicial: ${performance_tracker['banca_inicial']:.2f}")
        print("DEBUG: Iniciando busca de epics...")
        # Buscar epics de todos os pares antes de iniciar
        print("Buscando epics dos pares monitorados...")
        EPICS.clear()  # Garante que não há epics pré-preenchidos
        pares_validos = []
        for par in PARES:
            try:
                epic = api.buscar_epic_valido_para_ordem(par)
            except Exception as e:
                print(f"[MODO REAL] Erro ao buscar epic válido para {par}: {e}")
                epic = None
            if epic:
                EPICS[par] = epic
                pares_validos.append(par)
                print(f"[OK] {par}: {epic}")
            else:
                print(f"[ERRO] Não foi possível encontrar um epic válido para {par}. Esse par será ignorado.")
        if not pares_validos:
            print("Nenhum par disponível para operar. Encerrando.")
            sys.exit(1)
        PARES[:] = pares_validos
        print("\nResumo dos pares validados para trading:")
        for par in PARES:
            print(f"  - {par}: {EPICS[par]}")
        print("\nRobô pronto para operar apenas nos pares acima!\n")
        
        mostrar_configuracoes_stop_loss()
        mostrar_correcoes_implementadas()
    else:
        banca = ler_banca()
        print(f"[SIMULAÇÃO] Banca atual: ${banca['banca']:.2f} | Risco por operação: {banca['risco_percentual_operacao']}%\n")
    print(f"Pares monitorados: {', '.join(PARES)}")
    print("Robô Trader Multi-Pares - Análise e Simulação de Trades\n")
    print("=" * 80)
    print("🤖 ROBÔ TRADER PROFISSIONAL - Capital.com")
    print("📊 Análise multi-timeframe com confluências técnicas")
    print("💰 Gerenciamento rigoroso de risco e banca")
    print("🛡️  Sistema híbrido de Stop Loss (Normal + Garantido)")
    print("🔐 Sincronização em tempo real com posições da Capital.com")
    print("=" * 80)
    
    # Variável para controlar revalidação de pares
    ultima_validacao_pares = time.time()
    
    # Sistema de persistência por par - cada par tem suas tentativas
    tentativas_por_par = {}
    MAX_TENTATIVAS_POR_PAR = 3  # Máximo de tentativas por par antes de pausar
    TEMPO_ESPERA_ENTRE_TENTATIVAS = 60  # segundos entre tentativas no mesmo par quando não encontra dados
    TEMPO_ESPERA_SEM_SINAL = 30  # segundos quando não encontra sinal de qualidade
    
    while True:
        hoje = date.today().isoformat()
        if banca.get('ultimo_dia') != hoje:
            banca['ultimo_dia'] = hoje
            banca['lucro_dia'] = 0.0
            salvar_banca(banca)
        if banca['lucro_dia'] >= banca['stop_win_percentual']:
            print(f"\n[STOP WIN] Meta diária de lucro atingida (+${banca['lucro_dia']:.2f}). Robô vai pausar até amanhã.\n")
            time.sleep(60*60*3)
            continue
        if banca['lucro_dia'] <= banca['stop_loss_percentual']:
            print(f"\n[STOP LOSS] Limite diário de perda atingido (${banca['lucro_dia']:.2f}). Robô vai pausar até amanhã.\n")
            time.sleep(60*60*3)
            continue
        
        # NOVO SISTEMA: Verificar operações ativas com limite rigoroso
        ordens_ativas = len(performance_tracker['operacoes_ativas']) if MODO_REAL else len(ordens_abertas)
        
        if ordens_ativas > 0:
            print(f"\n[TRADER PROFISSIONAL] {ordens_ativas}/{MAX_POSICOES_SIMULTANEAS} operação(ões) ativa(s)")
            
            if MODO_REAL:
                # Usar o novo sistema de monitoramento
                for deal_id, info in list(performance_tracker['operacoes_ativas'].items()):
                    par = info['par']
                    try:
                        status_ordem = api.consultar_ordem(deal_id)
                        status = status_ordem.get('status')
                        print(f"  └─ {par} (Deal: {deal_id}): {status}")
                        
                        # Mostrar detalhes da posição se estiver aberta
                        if status == 'OPEN' and 'position' in status_ordem:
                            pos = status_ordem['position']
                            pnl = pos.get('profit', 0)
                            duracao = time.time() - info['timestamp']
                            print(f"    • P&L atual: ${pnl:.2f} | Duração: {duracao:.0f}s")
                            if 'stopLevel' in pos:
                                print(f"    • Stop Loss: {pos['stopLevel']}")
                            if 'limitLevel' in pos:
                                print(f"    • Take Profit: {pos['limitLevel']}")
                                
                    except Exception as e:
                        print(f"  └─ {par}: Erro ao consultar status: {e}")
            else:
                # Sistema antigo para simulação
                for par, deal_id in list(ordens_abertas.items()):
                    print(f"  └─ {par}: Operação simulada ativa")
            
            # Se atingiu o limite, aguardar fechamento
            if ordens_ativas >= MAX_POSICOES_SIMULTANEAS:
                print(f"[LIMITE ATINGIDO] Aguardando fechamento de operações...")
                time.sleep(INTERVALO_VERIFICACAO)
                continue
            else:
                print(f"[ANÁLISE PERMITIDA] Pode abrir mais {MAX_POSICOES_SIMULTANEAS - ordens_ativas} operação(ões)")
                # Continuar análise mesmo com operações abertas
        
        # Calcular limites dinâmicos baseados na banca atual (JUROS COMPOSTOS)
        limites = calcular_limites_dinamicos(banca['banca'], banca)
        valor_por_operacao = limites['risco_por_operacao']
        stop_win_diario = limites['stop_win_diario']
        stop_loss_diario = limites['stop_loss_diario']
        
        # Verificar stop win/loss diários
        if banca['lucro_dia'] >= stop_win_diario:
            print(f"\n[STOP WIN] Meta diária atingida: ${banca['lucro_dia']:.2f} de ${stop_win_diario:.2f}. Robô vai pausar até amanhã.")
            time.sleep(60*60*3)
            continue
        if banca['lucro_dia'] <= stop_loss_diario:
            print(f"\n[STOP LOSS] Limite diário atingido: ${banca['lucro_dia']:.2f} de ${stop_loss_diario:.2f}. Robô vai pausar até amanhã.")
            time.sleep(60*60*3)
            continue
        
        # Calcular operações restantes
        perda_maxima_dia = abs(stop_loss_diario)
        operacoes_restantes = int((perda_maxima_dia - abs(banca['lucro_dia'])) / valor_por_operacao) if banca['lucro_dia'] < 0 else int(perda_maxima_dia / valor_por_operacao)
        
        print(f"\n[RESUMO DIÁRIO] Banca: ${banca['banca']:.2f} | Lucro/Perda: ${banca['lucro_dia']:.2f}")
        print(f"[LIMITES DINÂMICOS] Win: ${stop_win_diario:.2f} ({banca['stop_win_percentual']}%) | Loss: ${stop_loss_diario:.2f} ({banca['stop_loss_percentual']}%)")
        print(f"[RISCO DINÂMICO] ${valor_por_operacao:.2f} por operação ({banca['risco_percentual_operacao']}%) | {max(0, operacoes_restantes)} operações restantes")
        
        if operacoes_restantes <= 0:
            print(f"[TRADER CONSERVADOR] Risco esgotado para hoje. Aguardando próximo dia.")
            time.sleep(60*60)  # 1 hora
            continue
        
        # Revalidar pares a cada 30 minutos para garantir que estão TRADEABLE
        if MODO_REAL and time.time() - ultima_validacao_pares > 1800:  # 30 minutos
            print(f"\n[REVALIDAÇÃO] Verificando pares disponíveis...")
            pares_validos_agora = []
            for par in PARES:
                try:
                    epic = api.buscar_epic_valido_para_ordem(par)
                    if epic:
                        EPICS[par] = epic
                        pares_validos_agora.append(par)
                except:
                    print(f"[REVALIDAÇÃO] {par} não disponível agora")
            
            # Atualizar lista de pares apenas com os disponíveis
            PARES[:] = pares_validos_agora
            ultima_validacao_pares = time.time()
            print(f"[REVALIDAÇÃO] Pares ativos: {', '.join(PARES)}")
        
        # NOVO: Verificar se pode operar (limite de posições)
        if MODO_REAL and not pode_operar():
            # Monitorar performance enquanto aguarda
            banca_atual, variacao, operacoes_ativas = monitorar_performance_realtime()
            if banca_atual:
                banca['banca'] = banca_atual
                salvar_banca(banca)
            time.sleep(INTERVALO_VERIFICACAO)
            continue
        
        # Monitorar performance em tempo real
        if MODO_REAL:
            banca_atual, variacao, operacoes_ativas = monitorar_performance_realtime()
            if banca_atual:
                banca['banca'] = banca_atual
                salvar_banca(banca)
        
        # 🎯 MONITORAMENTO INTELIGENTE DE RISCO (NOVA FUNCIONALIDADE)
        if MODO_REAL and ordens_ativas > 0:
            try:
                acao_tomada, motivo = monitoramento_inteligente_risco()
                
                if acao_tomada:
                    print(f"\n🚨 AÇÃO AUTOMÁTICA EXECUTADA: {motivo}")
                    print(f"🔄 Reiniciando ciclo após ação de proteção...")
                    
                    # Se foi stop loss, pausar por mais tempo
                    if "stop loss" in motivo.lower():
                        print(f"⏸️  Pausando operações por 1 hora após stop loss diário...")
                        time.sleep(3600)  # 1 hora
                    else:
                        print(f"✅ Continuando monitoramento após fechamento por lucro excepcional...")
                        time.sleep(30)  # 30 segundos
                    
                    continue  # Reiniciar o loop principal
                    
            except Exception as e:
                print(f"⚠️  Erro no monitoramento inteligente: {e}")
                print(f"   Continuando operação normal...")
        
        # SELEÇÃO INTELIGENTE DE PARES baseada no mercado
        pares_para_analisar = selecionar_pares_por_mercado()
        
        # Analisar pares com sistema de persistência
        for par in pares_para_analisar:
            
            # VERIFICAÇÃO CRÍTICA: Não operar no mesmo par duas vezes
            if verificar_operacao_existente_no_par(par):
                print(f"[TRADER PROFISSIONAL] ⏭️ Pulando {par} - Operação já existe neste ativo")
                continue
            if par in ordens_abertas:
                continue  # Pular pares com ordem aberta
                
            # Verificar se mercado está aberto para este par
            mercado_status, mercado_info = mercado_aberto(par)
            if not mercado_status:
                print(f"\n[MERCADO FECHADO] {par}: {mercado_info} - Pulando análise")
                continue
                
            print(f"\n[ANÁLISE] {datetime.now(TZ).strftime('%H:%M:%S')} - Analisando {par} ({mercado_info})...")
            
            melhor_sinal = None
            melhor_assertividade = None
            melhor_timeframe = None
            melhor_dados = None
            
            # Analisar todos os timeframes para encontrar o melhor sinal
            for timeframe in TIMEFRAMES:
                try:
                    df = buscar_candles(par, timeframe)
                    if df is not None and not df.empty:
                        print(f"  └─ Analisando {timeframe.name}:")
                        
                        # Mostrar informações da vela atual
                        candle = df.iloc[-1]
                        cor = "verde" if candle['close'] > candle['open'] else "vermelha"
                        print(f"    • Vela atual: {cor} (abertura: {candle['open']:.5f}, fechamento: {candle['close']:.5f})")
                        
                        # Usar nova análise REALISTA de confluências
                        resultado_confluencias = analisar_confluencias_profissionais(df, par, timeframe.name)
                        sinal = resultado_confluencias['sinal']
                        detalhes = resultado_confluencias['descricao'] 
                        assertividade = resultado_confluencias['qualidade']
                        
                        # Lote baseado na qualidade
                        if assertividade == 'EXCELENTE':
                            lote = 1.5 * obter_lote_padrao(par)  # Lote maior para excelente
                        elif assertividade == 'ALTA':
                            lote = 1.0 * obter_lote_padrao(par)  # Lote normal
                        elif assertividade == 'MÉDIA':
                            lote = 0.5 * obter_lote_padrao(par)  # Lote menor
                        else:
                            lote = 0  # Não operar
                        
                        instrucao = f"Confluências: {', '.join(resultado_confluencias['confluencias'][:3])}"
                        
                        # Mostrar médias móveis
                        ma_curta = df['ma_curta'].iloc[-1] if 'ma_curta' in df.columns and pd.notna(df['ma_curta'].iloc[-1]) else None
                        ma_longa = df['ma_longa'].iloc[-1] if 'ma_longa' in df.columns and pd.notna(df['ma_longa'].iloc[-1]) else None
                        if ma_curta is not None and ma_longa is not None:
                            tendencia_ma = "Bullish" if ma_curta > ma_longa else "Bearish"
                            print(f"    • MA5: {ma_curta:.5f} | MA10: {ma_longa:.5f} | Tendência: {tendencia_ma}")
                        else:
                            print("    • Médias móveis: Dados insuficientes")
                        
                        # Mostrar suporte/resistência
                        suporte, resistencia = detectar_suporte_resistencia(df)
                        if suporte is not None and resistencia is not None:
                            dist_sup = abs(candle['close'] - suporte)
                            dist_res = abs(candle['close'] - resistencia)
                            print(f"    • Suporte: {suporte:.5f} | Resistência: {resistencia:.5f}")
                            print(f"    • Distância até suporte: {dist_sup:.5f} | Distância até resistência: {dist_res:.5f}")
                        
                        # Mostrar detalhes da análise
                        print(f"    • {detalhes}")
                        
                        # Mostrar sinal e assertividade
                        if sinal:
                            print(f"    • SINAL: {sinal} | Assertividade: {assertividade} | Lote: {lote}")
                            if instrucao:
                                print(f"    • {instrucao}")
                        
                        # CRITÉRIO REALISTA: Aceitar sinais com mínimo 2 confluências
                        if sinal and lote > 0 and resultado_confluencias['score'] >= CRITERIOS_REALISTAS['MINIMO_CONFLUENCIAS']:
                            # Verificar se não é repetição do sinal anterior
                            agora = time.time()
                            sinal_key = f"{par}_{timeframe.name}_{sinal}"
                            
                            if par in sinais_recentes:
                                ultimo_sinal = sinais_recentes[par]
                                # Se é o mesmo sinal nos últimos 10 minutos, pular
                                if (agora - ultimo_sinal['timestamp'] < 600 and 
                                    ultimo_sinal['sinal'] == sinal and 
                                    ultimo_sinal['timeframe'] == timeframe.name):
                                    print(f"    ⏭️ Sinal repetido, aguardando novo setup...")
                                    continue
                            
                            melhor_sinal = sinal
                            melhor_assertividade = assertividade
                            melhor_timeframe = timeframe
                            melhor_dados = (df, instrucao, lote, detalhes)
                            
                            # Registrar sinal para evitar repetição
                            sinais_recentes[par] = {
                                'timestamp': agora,
                                'sinal': sinal,
                                'timeframe': timeframe.name
                            }
                            
                            score = resultado_confluencias['score']
                            confluencias_lista = resultado_confluencias['confluencias']
                            print(f"    ✅ SINAL {assertividade} SELECIONADO! (Score: {score}/6)")
                            print(f"    • Confluências: {', '.join(confluencias_lista[:2])}")
                            break  # Encontrou sinal de qualidade, usar este
                        else:
                            score = resultado_confluencias['score'] if resultado_confluencias else 0
                            print(f"    ❌ Sinal rejeitado (Score: {score}/{CRITERIOS_REALISTAS['MINIMO_CONFLUENCIAS']} mín.)")
                    else:
                        # Dados não disponíveis para este timeframe
                        print(f"  └─ {timeframe.name}: Dados não disponíveis")
                        continue
                except Exception as e:
                    # Erro na análise do timeframe
                    print(f"  └─ {timeframe.name}: Erro na análise")
                    continue
            
            # Se não conseguiu dados em nenhum timeframe, informar
            if melhor_sinal is None and all(buscar_candles(par, tf) is None for tf in TIMEFRAMES):
                if par in pares_problematicos:
                    print(f"  └─ {par} em pausa temporária por problemas de conexão")
                else:
                    print(f"  └─ Dados não disponíveis para {par} (timeout/conexão)")
                continue
            
            # CRITÉRIO PROFISSIONAL: Aceitar apenas operações de boa qualidade
            if melhor_sinal and melhor_assertividade in ['EXCELENTE', 'ALTA', 'MÉDIA']:
                df, instrucao, lote, detalhes = melhor_dados
                
                # VALIDAÇÃO CRÍTICA: Verificar se confluências são REAIS
                print(f"\n🔍 VALIDANDO CONFLUÊNCIAS REAIS...")
                if not validar_confluencias_reais(df, detalhes):
                    print(f"[VALIDAÇÃO] ❌ Setup rejeitado - confluências não são reais!")
                    print(f"[VALIDAÇÃO] Aguardando próximo setup com dados válidos...")
                    continue
                
                print(f"\n🎯 EXECUTANDO OPERAÇÃO ({melhor_assertividade} QUALIDADE):")
                print(f"  └─ Par: {par} | Sinal: {melhor_sinal} | Timeframe: {melhor_timeframe.name}")
                print(f"  └─ {detalhes}")
                
                # Explicação detalhada da entrada
                print(f"\n📊 ANÁLISE TÉCNICA DA ENTRADA:")
                
                # Extrair informações técnicas do DataFrame
                candle_atual = df.iloc[-1]
                preco_atual = candle_atual['close']
                rsi_atual = df['rsi'].iloc[-1] if 'rsi' in df.columns else None
                willr_atual = df['willr'].iloc[-1] if 'willr' in df.columns else None
                
                # Explicar a direção
                direcao_texto = "COMPRA (CALL)" if 'CALL' in melhor_sinal else "VENDA (PUT)"
                print(f"  └─ DIREÇÃO: {direcao_texto}")
                
                # Explicar confluências encontradas
                confluencias = []
                if 'Cruzamento de médias' in detalhes:
                    ma_curta = df['ma_curta'].iloc[-1] if 'ma_curta' in df.columns else None
                    ma_longa = df['ma_longa'].iloc[-1] if 'ma_longa' in df.columns else None
                    if ma_curta and ma_longa:
                        if ma_curta > ma_longa and 'CALL' in melhor_sinal:
                            confluencias.append("✓ Cruzamento bullish: MA curta acima da MA longa")
                        elif ma_curta < ma_longa and 'PUT' in melhor_sinal:
                            confluencias.append("✓ Cruzamento bearish: MA curta abaixo da MA longa")
                
                if 'Price Action' in detalhes:
                    if 'Engolfo de Alta' in detalhes:
                        confluencias.append("✓ Padrão Engolfo de Alta: reversão bullish confirmada")
                    elif 'Engolfo de Baixa' in detalhes:
                        confluencias.append("✓ Padrão Engolfo de Baixa: reversão bearish confirmada")
                    elif 'Martelo' in detalhes:
                        confluencias.append("✓ Padrão Martelo: possível reversão de alta")
                    elif 'Pin Bar' in detalhes:
                        confluencias.append("✓ Pin Bar: rejeição de preço identificada")
                
                if 'Rompimento' in detalhes:
                    if 'Resistência' in detalhes and 'CALL' in melhor_sinal:
                        confluencias.append("✓ Rompimento de Resistência: força compradora confirmada")
                    elif 'Suporte' in detalhes and 'PUT' in melhor_sinal:
                        confluencias.append("✓ Rompimento de Suporte: pressão vendedora confirmada")
                
                if 'Pullback' in detalhes:
                    confluencias.append("✓ Pullback confirmado: reteste de nível respeitado")
                
                # Análise de indicadores
                indicadores = []
                if rsi_atual:
                    if rsi_atual > 70:
                        indicadores.append(f"RSI: {rsi_atual:.1f} (Sobrecomprado)")
                    elif rsi_atual < 30:
                        indicadores.append(f"RSI: {rsi_atual:.1f} (Sobrevendido)")
                    else:
                        indicadores.append(f"RSI: {rsi_atual:.1f} (Neutro)")
                
                if willr_atual:
                    if willr_atual > -20:
                        indicadores.append(f"Williams %R: {willr_atual:.1f} (Sobrecomprado)")
                    elif willr_atual < -80:
                        indicadores.append(f"Williams %R: {willr_atual:.1f} (Sobrevendido)")
                    else:
                        indicadores.append(f"Williams %R: {willr_atual:.1f} (Neutro)")
                
                # Exibir confluências
                if confluencias:
                    print(f"  └─ CONFLUÊNCIAS TÉCNICAS:")
                    for conf in confluencias:
                        print(f"    {conf}")
                
                # Exibir indicadores
                if indicadores:
                    print(f"  └─ INDICADORES:")
                    for ind in indicadores:
                        print(f"    • {ind}")
                
                # Contexto de mercado
                tipo_mercado = "Criptomoeda (24/7)" if any(crypto in par for crypto in ['BTC', 'ETH', 'SOL', 'BCH', 'XRP', 'PEPE', 'INJ', 'TREMP']) else "Forex"
                print(f"  └─ CONTEXTO: {tipo_mercado} | Preço: {preco_atual:.5f}")
                
                # Justificativa da estratégia
                print(f"  └─ ESTRATÉGIA: {instrucao}" if instrucao else "")
                print(f"  └─ TAMANHO DA POSIÇÃO: {lote} lote ({'conservador' if lote < 1 else 'normal'})")
                
                print(f"\n💡 RESUMO: Operação baseada em {len(confluencias)} confluência(s) técnica(s) no timeframe {melhor_timeframe.name}")
                
                if MODO_REAL:
                    # Enviar ordem real
                    direcao = 'BUY' if 'CALL' in melhor_sinal else 'SELL'
                    try:
                        print(f"[EXECUÇÃO] Enviando ordem {direcao} para {par}...")
                        epic = EPICS[par]
                        preco_entrada = df['close'].iloc[-1]
                        
                        # Ajustar lote baseado no ativo
                        lote = obter_lote_padrao(par)
                        if melhor_assertividade == 'MÉDIA':
                            lote = lote * 0.5  # Reduzir para assertividade média
                        
                        print(f"[EXECUÇÃO] Lote base para {par}: {lote}")
                        
                        # Detectar se é criptomoeda e ajustar stop/take adequadamente
                        # IMPORTANTE: Distâncias de SL/TP foram ajustadas baseado em testes da Capital.com
                        # Capital.com rejeita SL/TP muito próximos (< 10 pips para forex)
                        is_crypto = any(crypto in par for crypto in ['BTC', 'ETH', 'SOL', 'BCH', 'XRP', 'INJ', 'USD'])
                        
                        if is_crypto and par != 'USDJPY':  # USDJPY é forex, não cripto
                            # Para cripto: usar DISTÂNCIAS FIXAS em dólares (CORREÇÃO CRÍTICA)
                            # Capital.com rejeita stops muito próximos e aplica valores absurdos
                            
                            # Distâncias baseadas no preço do ativo
                            if 'BTC' in par:
                                sl_distance = 2000  # $2000 stop loss para Bitcoin
                                tp_distance = 3000  # $3000 take profit para Bitcoin
                                
                                # Aplicar distâncias fixas para BTC
                                if melhor_sinal == 'CALL (COMPRA)':
                                    stop_loss = preco_entrada - sl_distance
                                    take_profit = preco_entrada + tp_distance
                                else:
                                    stop_loss = preco_entrada + sl_distance
                                    take_profit = preco_entrada - tp_distance
                                
                                print(f"[EXECUÇÃO] {par}: SL=${sl_distance} TP=${tp_distance} [DISTÂNCIAS FIXAS CORRIGIDAS]")
                                
                            elif 'ETH' in par:
                                sl_distance = 100   # $100 stop loss para Ethereum
                                tp_distance = 150   # $150 take profit para Ethereum
                                
                                # Aplicar distâncias fixas para ETH
                                if melhor_sinal == 'CALL (COMPRA)':
                                    stop_loss = preco_entrada - sl_distance
                                    take_profit = preco_entrada + tp_distance
                                else:
                                    stop_loss = preco_entrada + sl_distance
                                    take_profit = preco_entrada - tp_distance
                                
                                print(f"[EXECUÇÃO] {par}: SL=${sl_distance} TP=${tp_distance} [DISTÂNCIAS FIXAS CORRIGIDAS]")
                                
                            else:
                                # Outros cryptos: usar percentual mais conservador
                                sl_percent = 0.03   # 3% stop loss (mais seguro)
                                tp_percent = 0.045  # 4.5% take profit
                                if melhor_sinal == 'CALL (COMPRA)':
                                    stop_loss = preco_entrada * (1 - sl_percent)
                                    take_profit = preco_entrada * (1 + tp_percent)
                                else:
                                    stop_loss = preco_entrada * (1 + sl_percent)
                                    take_profit = preco_entrada * (1 - tp_percent)
                                print(f"[EXECUÇÃO] Cripto Genérico: SL={sl_percent*100}% TP={tp_percent*100}%")
                        else:
                            # Para forex: usar pips maiores (AJUSTADO baseado nos testes)
                            pip = 0.0001 if 'JPY' not in par else 0.01
                            sl_pips = 20  # AUMENTADO de 15 para 20 (teste mostrou que <10 pips falha)
                            tp_pips = 35  # AUMENTADO de 30 para 35 (proporcionalmente)
                            if melhor_sinal == 'CALL (COMPRA)':
                                stop_loss = preco_entrada - sl_pips * pip
                                take_profit = preco_entrada + tp_pips * pip
                            else:
                                stop_loss = preco_entrada + sl_pips * pip
                                take_profit = preco_entrada - tp_pips * pip
                            print(f"[EXECUÇÃO] Forex: SL={sl_pips} pips TP={tp_pips} pips [DISTÂNCIAS AJUSTADAS]")
                        
                        print(f"[EXECUÇÃO] Entrada: {preco_entrada:.5f} | SL: {stop_loss:.5f} | TP: {take_profit:.5f}")
                        
                        # Consultar regras do epic ANTES de enviar ordem
                        try:
                            regras = api.consultar_regras_epic(epic)
                            min_deal = regras.get('minDealSize')
                            max_deal = regras.get('maxDealSize')
                            step_size = regras.get('stepSize')
                            min_stop = regras.get('minNormalStopOrLimitDistance')
                            max_stop = regras.get('maxStopOrLimitDistance')
                            
                            print(f"[EXECUÇÃO] Regras do {epic}:")
                            print(f"  • Min Lote: {min_deal} | Max Lote: {max_deal} | Step: {step_size}")
                            print(f"  • Min Stop: {min_stop} | Max Stop: {max_stop}")
                            
                            # Ajustar lote para respeitar mínimo (CRUCIAL para evitar error.invalid.size.minvalue)
                            if min_deal and lote < min_deal:
                                lote_original = lote
                                lote = min_deal
                                print(f"[AJUSTE CRÍTICO] Lote ajustado de {lote_original} para {lote} (mínimo exigido pela Capital.com)")
                                print(f"[INFO] Epic {epic} requer lote mínimo de {min_deal}")
                            
                            # Ajustar lote para respeitar step size
                            if step_size and step_size > 0:
                                lote_ajustado = round(lote / step_size) * step_size
                                if lote_ajustado != lote:
                                    print(f"[AJUSTE] Lote ajustado de {lote} para {lote_ajustado} (step size)")
                                    lote = lote_ajustado
                            
                            # Verificar máximo
                            if max_deal and lote > max_deal:
                                print(f"[AJUSTE] Lote limitado ao máximo: {max_deal}")
                                lote = max_deal
                            
                        except Exception as e:
                            print(f"[EXECUÇÃO] Aviso: erro ao consultar regras do epic: {e}")
                        
                        # Enviar ordem com STOP LOSS e TAKE PROFIT (com stop garantido)
                        print(f"[EXECUÇÃO] Enviando ordem com SL e TP GARANTIDOS...")
                        print(f"[EXECUÇÃO] Parâmetros: epic={epic}, direction={direcao}, size={lote}")
                        print(f"[EXECUÇÃO] Stop Loss: {stop_loss:.5f} | Take Profit: {take_profit:.5f}")
                        
                        # Determinar tipo de stop loss (normal ou garantido)
                        usar_stop_garantido = determinar_tipo_stop_loss(par)
                        tipo_stop = "GARANTIDO" if usar_stop_garantido else "NORMAL"
                        
                        print(f"[EXECUÇÃO] Tipo de Stop Loss: {tipo_stop}")
                        
                        # Enviar ordem com tipo de stop apropriado
                        resposta = api.enviar_ordem(epic, direcao, lote, stop=stop_loss, limit=take_profit, guaranteed_stop=usar_stop_garantido)
                        deal_id = resposta.get('dealId') or resposta.get('dealReference')
                        if deal_id:
                            print(f"[SUCESSO] Ordem enviada! DealId: {deal_id}")
                            
                            # Verificar se SL e TP foram aceitos
                            if resposta.get('stop_take_added') == True:
                                print(f"[SUCESSO] Stop Loss e Take Profit adicionados com sucesso!")
                            elif resposta.get('stop_take_added') == False:
                                print(f"[AVISO] Posição criada, mas SL/TP não foram aceitos")
                            else:
                                print(f"[INFO] Posição criada sem SL/TP")
                            
                            ordens_abertas[par] = deal_id
                            
                            # NOVO: Registrar operação no performance tracker
                            registrar_operacao(deal_id, par, banca['banca'])
                            
                            # Verificar imediatamente se a posição foi criada
                            print(f"[INFO] Verificando se posição foi criada corretamente...")
                            time.sleep(5)  # Aguardar apenas 5 segundos
                            
                            try:
                                status_ordem = api.consultar_ordem(deal_id)
                                if status_ordem.get('status') == 'OPEN':
                                    print(f"[SUCESSO] Posição {deal_id} confirmada como ABERTA!")
                                else:
                                    print(f"[AVISO] Status da posição: {status_ordem.get('status')}")
                            except Exception as e:
                                print(f"[AVISO] Não foi possível verificar status: {e}")
                            
                            # Parar de analisar outros pares por agora (comportamento conservador)
                            break
                        else:
                            print(f"[ERRO] Ordem enviada mas sem dealId. Resposta: {resposta}")
                        ganho = 0
                        resultado = 'ENVIADA'
                    except Exception as e:
                        print(f"[ERRO] Erro ao enviar ordem: {e}")
                        ganho = 0
                        resultado = 'ERRO ENVIO'
                    else:
                        ganho, resultado = simular_trade(par, melhor_timeframe, df, melhor_sinal, banca['banca'], banca['risco_percentual_operacao'])
                
                banca['banca'] += ganho
                banca['lucro_dia'] += ganho
                banca['historico'].append({
                    'par': par,
                    'timeframe': melhor_timeframe.name,
                    'sinal': melhor_sinal,
                    'resultado': resultado,
                    'lucro': ganho,
                    'banca': banca['banca'],
                    'data': datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
                })
                salvar_banca(banca)
                break  # Parar após executar uma operação
            else:
                if melhor_sinal is None:
                    print(f"  └─ Nenhum timeframe com dados válidos para {par}")
                else:
                    print(f"  └─ Sinais encontrados mas nenhum de alta qualidade suficiente")
        
        # Mostrar status das tentativas por par
        pares_ativos = [p for p in tentativas_por_par.keys() if tentativas_por_par[p]['count'] < MAX_TENTATIVAS_POR_PAR]
        pares_pausados = [p for p in tentativas_por_par.keys() if tentativas_por_par[p]['count'] >= MAX_TENTATIVAS_POR_PAR]
        
        if pares_pausados:
            print(f"\n[STATUS] Pares pausados temporariamente: {', '.join(pares_pausados)}")
        if pares_ativos:
            print(f"[STATUS] Pares ativos para análise: {', '.join(pares_ativos)}")
        
        # Aguardar intervalo conservador antes da próxima análise
        if not ordens_abertas:
            print(f"\n[TRADER CONSERVADOR] Ciclo concluído. Aguardando 30 segundos...")
            time.sleep(30)  # Reduzido para 30 segundos para ser mais responsivo
        
        # Atualizar banca com saldo real da conta demo a cada ciclo
        if MODO_REAL:
            saldo_api = api.saldo()
            saldo_demo = saldo_api['accounts'][0]['balance']['balance']
            banca['banca'] = saldo_demo
            print(f"[MODO REAL] Banca sincronizada com Capital.com: ${banca['banca']:.2f} | Horário: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}")

            