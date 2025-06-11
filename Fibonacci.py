import pandas as pd
from typing import Dict, Tuple, Optional, Any

def detectar_swing_high_low(df: pd.DataFrame, n: int = 20) -> Tuple[float, float]:
    """
    Detecta o último swing high e swing low relevantes usando pivôs locais.
    n: número de candles para considerar como janela de pivô.
    Retorna (swing_low, swing_high)
    """
    highs = df['high'].values
    lows = df['low'].values
    swing_high = None
    swing_low = None
    # Swing high: máximo que é maior que n anteriores e n posteriores
    for i in range(n, len(df) - n):
        if highs[i] == max(highs[i - n:i + n + 1]):
            swing_high = highs[i]
    # Swing low: mínimo que é menor que n anteriores e n posteriores
    for i in range(n, len(df) - n):
        if lows[i] == min(lows[i - n:i + n + 1]):
            swing_low = lows[i]
    return swing_low, swing_high

def calcular_fibonacci(
    df: pd.DataFrame,
    n: int = 100,
    direcao: Optional[str] = None,
    swing_window: int = 20,
    incluir_extensoes: bool = True
) -> Dict[str, Any]:
    """
    Calcula níveis de Fibonacci (retracement e extensões) a partir do último swing high/low relevante.
    Retorna contexto completo: níveis, direção, swing points, distância do preço, tendência, ATR, etc.
    """
    ultimos = df.tail(n)
    swing_low, swing_high = detectar_swing_high_low(ultimos, n=swing_window)
    if swing_low is None or swing_high is None:
        # fallback para min/max
        swing_low = ultimos['low'].min()
        swing_high = ultimos['high'].max()
    close = ultimos['close'].iloc[-1]
    # Direção automática
    if direcao is None:
        # Se o último close está mais próximo do high, assume tendência de alta
        if abs(close - swing_high) < abs(close - swing_low):
            direcao = 'baixa'
        else:
            direcao = 'alta'
    diff = swing_high - swing_low
    # Níveis de retração
    if direcao == 'alta':
        retracements = {
            '0.0': swing_high,
            '0.236': swing_high - 0.236 * diff,
            '0.382': swing_high - 0.382 * diff,
            '0.5': swing_high - 0.5 * diff,
            '0.618': swing_high - 0.618 * diff,
            '0.786': swing_high - 0.786 * diff,
            '1.0': swing_low
        }
        # Extensões para cima
        extensoes = {
            '1.272': swing_high + 0.272 * diff,
            '1.618': swing_high + 0.618 * diff,
            '2.0': swing_high + 1.0 * diff,
            '2.618': swing_high + 1.618 * diff
        } if incluir_extensoes else {}
    else:
        # Traça do swing_high (0) ao swing_low (1)
        retracements = {
            '0.0': swing_low,
            '0.236': swing_low + 0.236 * diff,
            '0.382': swing_low + 0.382 * diff,
            '0.5': swing_low + 0.5 * diff,
            '0.618': swing_low + 0.618 * diff,
            '0.786': swing_low + 0.786 * diff,
            '1.0': swing_high
        }
        # Extensões para baixo
        extensoes = {
            '1.272': swing_low - 0.272 * diff,
            '1.618': swing_low - 0.618 * diff,
            '2.0': swing_low - 1.0 * diff,
            '2.618': swing_low - 1.618 * diff
        } if incluir_extensoes else {}
    # ATR para tolerância dinâmica
    atr = ultimos['high'].rolling(window=14).max() - ultimos['low'].rolling(window=14).min()
    atr_val = atr.iloc[-1] if not atr.isna().iloc[-1] else (ultimos['high'].max() - ultimos['low'].min()) / 14
    # Tendência simples
    tendencia = 'alta' if swing_high > swing_low else 'baixa'
    # Distância do preço para cada nível
    distancias = {nivel: abs(close - valor) for nivel, valor in {**retracements, **extensoes}.items()}
    # Retorno profissional
    return {
        'retracements': retracements,
        'extensoes': extensoes,
        'swing_high': swing_high,
        'swing_low': swing_low,
        'direcao': direcao,
        'tendencia': tendencia,
        'close': close,
        'distancias': distancias,
        'atr': atr_val
    }

def encontrar_zona_fibonacci(
    close: float,
    levels: Dict[str, float],
    tolerancia: Optional[float] = None,
    atr: Optional[float] = None
) -> Tuple[Optional[str], Optional[float]]:
    """
    Verifica se o preço está próximo de algum nível de Fibonacci.
    Se tolerância não for informada, usa 0.5 * ATR como tolerância dinâmica.
    """
    if tolerancia is None and atr is not None:
        tolerancia = 0.5 * atr
    elif tolerancia is None:
        tolerancia = 0.001  # fallback
    for nivel, valor in levels.items():
        if nivel in ['swing_high', 'swing_low', 'direcao']:
            continue
        if abs(close - valor) <= tolerancia:
            return nivel, valor
    return None, None 