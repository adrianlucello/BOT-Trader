# Robô Analista Gráfico para Trading

Este projeto é um robô Python que analisa gráficos de pares de moedas utilizando APIs públicas gratuitas (exemplo: TradingView, Yahoo Finance, Alpha Vantage) e fornece sinais para operações de M5 (5 minutos).

## Tecnologias
- Python 3
- Flet (interface gráfica)
- Requests (requisições HTTP)
- Pandas (análise de dados)

## Objetivo
- Baixar e analisar dados de pares de moedas.
- Exibir gráficos e sinais para o trader.
- Interface amigável para visualização dos dados.

## Como rodar
1. Crie o ambiente virtual:
   ```bash
   python -m venv venv
   ```
2. Ative o ambiente virtual:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Execute o projeto:
   ```bash
   python main.py
   ```

## Próximos passos
- Integração com API pública de dados financeiros.
- Análise de candles M5.
- Geração de sinais automáticos.
- Interface gráfica com Flet. 