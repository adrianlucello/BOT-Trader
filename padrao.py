import pandas as pd
from typing import Dict, List

# Função utilitária para identificar pivôs (topos e fundos)
def encontrar_pivos(df: pd.DataFrame, lookback: int = 5) -> Dict[str, List[int]]:
    """
    Retorna índices de topos e fundos no gráfico.
    """
    topos = []
    fundos = []
    for i in range(lookback, len(df) - lookback):
        max_v = df['high'].iloc[i - lookback:i + lookback + 1].max()
        min_v = df['low'].iloc[i - lookback:i + lookback + 1].min()
        if df['high'].iloc[i] == max_v:
            topos.append(i)
        if df['low'].iloc[i] == min_v:
            fundos.append(i)
    return {'topos': topos, 'fundos': fundos}

# Detecta triângulo (simples, para início)
def detectar_triangulo(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    fundos = pivos['fundos']
    if len(topos) < 2 or len(fundos) < 2:
        return {'status': False}
    # Verifica convergência de linhas de tendência
    # (Aperfeiçoar: regressão linear, ângulo, distância entre linhas)
    ultimos_topos = df['high'].iloc[topos[-2:]].values
    ultimos_fundos = df['low'].iloc[fundos[-2:]].values
    if ultimos_topos[1] < ultimos_topos[0] and ultimos_fundos[1] > ultimos_fundos[0]:
        return {
            'status': True,
            'tipo': 'Triângulo Simétrico',
            'direcao': 'Indefinida',
            'pontos': {'topos': topos[-2:], 'fundos': fundos[-2:]}
        }
    return {'status': False}

# Detecta bandeira (flag)
def detectar_bandeira(df: pd.DataFrame) -> Dict:
    # Critério: forte movimento (mastro) seguido de consolidação inclinada
    n = 20
    if len(df) < n + 10:
        return {'status': False}
    mastro = df['close'].iloc[-n-10:-10]
    consolidacao = df['close'].iloc[-10:]
    if abs(mastro[-1] - mastro[0]) > 2 * consolidacao.std():
        inclinacao = consolidacao[-1] - consolidacao[0]
        direcao = 'Alta' if mastro[-1] > mastro[0] else 'Baixa'
        return {
            'status': True,
            'tipo': 'Bandeira',
            'direcao': direcao,
            'pontos': {'inicio_mastro': len(df)-n-10, 'fim_mastro': len(df)-10, 'consolidacao': (len(df)-10, len(df)-1)}
        }
    return {'status': False}

# Detecta OCO (Ombro-Cabeça-Ombro)
def detectar_oco(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    if len(topos) < 3:
        return {'status': False}
    # Padrão: topo-esquerda < topo-central > topo-direita (simples)
    h, c, d = topos[-3:]
    v_h, v_c, v_d = df['high'].iloc[[h, c, d]]
    if v_c > v_h and v_c > v_d and abs(v_h - v_d) / v_c < 0.05:
        return {
            'status': True,
            'tipo': 'OCO',
            'direcao': 'Baixa',
            'pontos': {'ombro_esq': h, 'cabeca': c, 'ombro_dir': d}
        }
    return {'status': False}

# Detecta retângulo (consolidação)
def detectar_retangulo(df: pd.DataFrame) -> Dict:
    n = 20
    if len(df) < n:
        return {'status': False}
    max_v = df['high'].iloc[-n:].max()
    min_v = df['low'].iloc[-n:].min()
    if (max_v - min_v) / min_v < 0.01:  # amplitude pequena
        return {
            'status': True,
            'tipo': 'Retângulo',
            'direcao': 'Lateral',
            'pontos': {'max': max_v, 'min': min_v, 'inicio': len(df)-n, 'fim': len(df)-1}
        }
    return {'status': False}

# Triângulo Ascendente
def detectar_triangulo_ascendente(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    fundos = pivos['fundos']
    if len(topos) < 2 or len(fundos) < 2:
        return {'status': False}
    ultimos_topos = df['high'].iloc[topos[-2:]].values
    ultimos_fundos = df['low'].iloc[fundos[-2:]].values
    if abs(ultimos_topos[1] - ultimos_topos[0]) < 1e-5 and ultimos_fundos[1] > ultimos_fundos[0]:
        return {
            'status': True,
            'tipo': 'Triângulo Ascendente',
            'direcao': 'Alta',
            'pontos': {'topos': topos[-2:], 'fundos': fundos[-2:]}
        }
    return {'status': False}

# Triângulo Descendente
def detectar_triangulo_descendente(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    fundos = pivos['fundos']
    if len(topos) < 2 or len(fundos) < 2:
        return {'status': False}
    ultimos_topos = df['high'].iloc[topos[-2:]].values
    ultimos_fundos = df['low'].iloc[fundos[-2:]].values
    if ultimos_topos[1] < ultimos_topos[0] and abs(ultimos_fundos[1] - ultimos_fundos[0]) < 1e-5:
        return {
            'status': True,
            'tipo': 'Triângulo Descendente',
            'direcao': 'Baixa',
            'pontos': {'topos': topos[-2:], 'fundos': fundos[-2:]}
        }
    return {'status': False}

# Flâmula (Pennant)
def detectar_flamula(df: pd.DataFrame) -> Dict:
    n = 20
    if len(df) < n + 10:
        return {'status': False}
    mastro = df['close'].iloc[-n-10:-10]
    consolidacao = df['close'].iloc[-10:]
    if abs(mastro[-1] - mastro[0]) > 2 * consolidacao.std():
        # Flâmula: consolidação curta e inclinada, menor que bandeira
        if consolidacao.max() - consolidacao.min() < (mastro.max() - mastro.min()) * 0.3:
            direcao = 'Alta' if mastro[-1] > mastro[0] else 'Baixa'
            return {
                'status': True,
                'tipo': 'Flâmula',
                'direcao': direcao,
                'pontos': {'inicio_mastro': len(df)-n-10, 'fim_mastro': len(df)-10, 'consolidacao': (len(df)-10, len(df)-1)}
            }
    return {'status': False}

# Cunha de Alta (Rising Wedge)
def detectar_cunha_alta(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    fundos = pivos['fundos']
    if len(topos) < 2 or len(fundos) < 2:
        return {'status': False}
    ultimos_topos = df['high'].iloc[topos[-2:]].values
    ultimos_fundos = df['low'].iloc[fundos[-2:]].values
    if ultimos_topos[1] > ultimos_topos[0] and ultimos_fundos[1] > ultimos_fundos[0] and (ultimos_topos[1] - ultimos_topos[0]) < (ultimos_fundos[1] - ultimos_fundos[0]):
        return {
            'status': True,
            'tipo': 'Cunha de Alta',
            'direcao': 'Baixa',
            'pontos': {'topos': topos[-2:], 'fundos': fundos[-2:]}
        }
    return {'status': False}

# Cunha de Baixa (Falling Wedge)
def detectar_cunha_baixa(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    fundos = pivos['fundos']
    if len(topos) < 2 or len(fundos) < 2:
        return {'status': False}
    ultimos_topos = df['high'].iloc[topos[-2:]].values
    ultimos_fundos = df['low'].iloc[fundos[-2:]].values
    if ultimos_topos[1] < ultimos_topos[0] and ultimos_fundos[1] < ultimos_fundos[0] and abs(ultimos_topos[1] - ultimos_topos[0]) < abs(ultimos_fundos[1] - ultimos_fundos[0]):
        return {
            'status': True,
            'tipo': 'Cunha de Baixa',
            'direcao': 'Alta',
            'pontos': {'topos': topos[-2:], 'fundos': fundos[-2:]}
        }
    return {'status': False}

# Canal de Alta
def detectar_canal_alta(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    fundos = pivos['fundos']
    if len(topos) < 2 or len(fundos) < 2:
        return {'status': False}
    ultimos_topos = df['high'].iloc[topos[-2:]].values
    ultimos_fundos = df['low'].iloc[fundos[-2:]].values
    if ultimos_topos[1] > ultimos_topos[0] and ultimos_fundos[1] > ultimos_fundos[0]:
        return {
            'status': True,
            'tipo': 'Canal de Alta',
            'direcao': 'Alta',
            'pontos': {'topos': topos[-2:], 'fundos': fundos[-2:]}
        }
    return {'status': False}

# Canal de Baixa
def detectar_canal_baixa(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    fundos = pivos['fundos']
    if len(topos) < 2 or len(fundos) < 2:
        return {'status': False}
    ultimos_topos = df['high'].iloc[topos[-2:]].values
    ultimos_fundos = df['low'].iloc[fundos[-2:]].values
    if ultimos_topos[1] < ultimos_topos[0] and ultimos_fundos[1] < ultimos_fundos[0]:
        return {
            'status': True,
            'tipo': 'Canal de Baixa',
            'direcao': 'Baixa',
            'pontos': {'topos': topos[-2:], 'fundos': fundos[-2:]}
        }
    return {'status': False}

# Topo Duplo
def detectar_topo_duplo(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    topos = pivos['topos']
    if len(topos) < 2:
        return {'status': False}
    v1, v2 = df['high'].iloc[topos[-2:]]
    if abs(v1 - v2) / v1 < 0.01:
        return {
            'status': True,
            'tipo': 'Topo Duplo',
            'direcao': 'Baixa',
            'pontos': {'topos': topos[-2:]}
        }
    return {'status': False}

# Fundo Duplo
def detectar_fundo_duplo(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    fundos = pivos['fundos']
    if len(fundos) < 2:
        return {'status': False}
    v1, v2 = df['low'].iloc[fundos[-2:]]
    if abs(v1 - v2) / v1 < 0.01:
        return {
            'status': True,
            'tipo': 'Fundo Duplo',
            'direcao': 'Alta',
            'pontos': {'fundos': fundos[-2:]}
        }
    return {'status': False}

# Cup and Handle (Xícara com Alça)
def detectar_cup_handle(df: pd.DataFrame) -> Dict:
    n = 30
    if len(df) < n + 10:
        return {'status': False}
    min_v = df['low'].iloc[-n-10:-10].min()
    max_v = df['high'].iloc[-n-10:-10].max()
    alca = df['close'].iloc[-10:]
    if (df['close'].iloc[-n-10] > min_v and df['close'].iloc[-10] > min_v and max_v - min_v > 2 * alca.std() and alca.mean() > min_v):
        return {
            'status': True,
            'tipo': 'Cup and Handle',
            'direcao': 'Alta',
            'pontos': {'inicio': len(df)-n-10, 'fundo': min_v, 'alca': (len(df)-10, len(df)-1)}
        }
    return {'status': False}

# OCO Invertido
def detectar_oco_invertido(df: pd.DataFrame) -> Dict:
    pivos = encontrar_pivos(df, lookback=5)
    fundos = pivos['fundos']
    if len(fundos) < 3:
        return {'status': False}
    h, c, d = fundos[-3:]
    v_h, v_c, v_d = df['low'].iloc[[h, c, d]]
    if v_c < v_h and v_c < v_d and abs(v_h - v_d) / v_c < 0.05:
        return {
            'status': True,
            'tipo': 'OCO Invertido',
            'direcao': 'Alta',
            'pontos': {'ombro_esq': h, 'cabeca': c, 'ombro_dir': d}
        }
    return {'status': False}

# Engolfo de Alta/Baixa (candlestick)
def detectar_engolfo(df: pd.DataFrame) -> Dict:
    if len(df) < 2:
        return {'status': False}
    o1, c1 = df['open'].iloc[-2], df['close'].iloc[-2]
    o2, c2 = df['open'].iloc[-1], df['close'].iloc[-1]
    if c1 < o1 and c2 > o2 and c2 > o1 and o2 < c1:
        return {
            'status': True,
            'tipo': 'Engolfo de Alta',
            'direcao': 'Alta',
            'pontos': {'candle1': len(df)-2, 'candle2': len(df)-1}
        }
    if c1 > o1 and c2 < o2 and c2 < o1 and o2 > c1:
        return {
            'status': True,
            'tipo': 'Engolfo de Baixa',
            'direcao': 'Baixa',
            'pontos': {'candle1': len(df)-2, 'candle2': len(df)-1}
        }
    return {'status': False}

# Função principal: retorna todos os padrões detectados
def detectar_padroes(df: pd.DataFrame) -> List[Dict]:
    padroes = []
    funcoes = [
        detectar_triangulo, detectar_triangulo_ascendente, detectar_triangulo_descendente,
        detectar_bandeira, detectar_flamula,
        detectar_oco, detectar_oco_invertido,
        detectar_retangulo, detectar_cunha_alta, detectar_cunha_baixa,
        detectar_canal_alta, detectar_canal_baixa,
        detectar_topo_duplo, detectar_fundo_duplo,
        detectar_cup_handle, detectar_engolfo
    ]
    for func in funcoes:
        resultado = func(df)
        if resultado.get('status'):
            padroes.append(resultado)
    return padroes 