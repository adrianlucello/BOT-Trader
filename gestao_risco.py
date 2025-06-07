#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🧠 MÓDULO DE GESTÃO INTELIGENTE DE RISCO
========================================
Sistema que monitora posições ativas e ajusta stops/takes automaticamente
como um trader profissional, protegendo lucros e maximizando ganhos.
"""

from capital_api import CapitalAPI
import json
from datetime import datetime
import pytz
import time

class GestaoRiscoInteligente:
    def __init__(self, api: CapitalAPI):
        self.api = api
        self.timezone = pytz.timezone('America/Sao_Paulo')
        
        # Configurações de gestão de risco
        self.config = {
            # Breakeven: quando lucro >= X USD, move stop para entrada
            'breakeven_lucro_minimo': 50.0,
            
            # Trailing Stop: quando lucro >= X USD, ativa trailing
            'trailing_lucro_minimo': 80.0,
            'trailing_distancia_pips': 20,  # Distância do trailing em pips
            
            # Take Profit automático baseado em R:R
            'take_profit_rr_ratio': 2.0,  # Risk:Reward 1:2
            
            # Proteção de lucro: quando lucro >= X%, protege Y% do lucro
            'protecao_lucro_minimo_pct': 15,  # 15% de lucro mínimo
            'protecao_percentual': 70,       # Protege 70% do lucro
            
            # Configurações por timeframe
            'monitoramento_intervalo': 30,   # Verifica a cada 30 segundos
        }
        
        self.posicoes_monitoramento = {}  # Cache de posições
        
    def log(self, mensagem):
        """Log com timestamp"""
        agora = datetime.now(self.timezone)
        timestamp = agora.strftime('%d/%m %H:%M:%S')
        print(f"[{timestamp}] 🧠 GESTÃO: {mensagem}")
        
    def iniciar_monitoramento(self):
        """
        Loop principal de monitoramento de posições
        Roda continuamente analisando e ajustando posições
        """
        self.log("Iniciando monitoramento inteligente de posições...")
        
        while True:
            try:
                # Consultar posições ativas
                posicoes = self.api.consultar_posicoes_ativas()
                
                if posicoes:
                    self.log(f"Monitorando {len(posicoes)} posição(ões) ativa(s)")
                    
                    for posicao in posicoes:
                        self.analisar_e_ajustar_posicao(posicao)
                else:
                    self.log("Nenhuma posição ativa - aguardando...")
                
                # Aguardar próxima verificação
                time.sleep(self.config['monitoramento_intervalo'])
                
            except KeyboardInterrupt:
                self.log("Monitoramento interrompido pelo usuário")
                break
            except Exception as e:
                self.log(f"Erro no monitoramento: {e}")
                time.sleep(60)  # Aguardar 1 minuto em caso de erro
                
    def analisar_e_ajustar_posicao(self, posicao):
        """
        Analisa uma posição específica e aplica gestão inteligente
        """
        deal_id = posicao['dealId']
        epic = posicao['epic']
        direction = posicao['direction']
        size = posicao['size']
        profit = posicao['profit']
        stop_atual = posicao['stopLevel']
        take_atual = posicao['limitLevel']
        
        # Obter dados do mercado para preço atual
        preco_atual = self.obter_preco_atual(epic, direction)
        if not preco_atual:
            return
            
        preco_entrada = self.calcular_preco_entrada(posicao, preco_atual, profit)
        
        self.log(f"Analisando {epic} {direction} {size} - P&L: ${profit:.2f}")
        
        # 1. ADICIONAR TAKE PROFIT se não existir
        if not take_atual and profit > 20:  # Só adiciona TP se já está em lucro
            novo_take = self.calcular_take_profit_inteligente(posicao, preco_atual, preco_entrada)
            if novo_take:
                self.definir_take_profit(deal_id, novo_take, epic, direction)
        
        # 2. BREAKEVEN: Mover stop para entrada quando lucro >= X
        if profit >= self.config['breakeven_lucro_minimo']:
            if not self.ja_esta_em_breakeven(stop_atual, preco_entrada, direction):
                self.mover_stop_para_breakeven(deal_id, preco_entrada, epic, direction, profit)
        
        # 3. TRAILING STOP: Ativar quando lucro >= Y
        if profit >= self.config['trailing_lucro_minimo']:
            self.aplicar_trailing_stop(deal_id, posicao, preco_atual, preco_entrada)
        
        # 4. PROTEÇÃO DE LUCRO: Proteger % do lucro quando muito alto
        if profit > 0:
            lucro_pct = (profit / (abs(preco_entrada - stop_atual) * size * 10)) * 100  # Estimativa
            if lucro_pct >= self.config['protecao_lucro_minimo_pct']:
                self.aplicar_protecao_lucro(deal_id, posicao, preco_atual, preco_entrada, profit)
                
    def obter_preco_atual(self, epic, direction):
        """Obtém preço atual do mercado"""
        try:
            url = f'{self.api.base_url}/api/v1/markets/{epic}'
            headers = {
                'X-CAP-API-KEY': self.api.api_key,
                'CST': self.api.cst,
                'X-SECURITY-TOKEN': self.api.x_security_token
            }
            
            resp = self.api.session.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                snapshot = data.get('snapshot', {})
                bid = snapshot.get('bid')
                offer = snapshot.get('offer')
                
                # Para BUY usa bid, para SELL usa offer
                return bid if direction == 'BUY' else offer
        except:
            pass
        return None
        
    def calcular_preco_entrada(self, posicao, preco_atual, profit):
        """Calcula preço de entrada baseado no P&L atual"""
        try:
            # Extrair dados da posição
            level = posicao['raw']['position'].get('level')
            if level:
                return float(level)
                
            # Fallback: calcular baseado no P&L
            direction = posicao['direction']
            size = posicao['size']
            
            if direction == 'BUY':
                # Para BUY: entrada = preço_atual - (profit / size)
                return preco_atual - (profit / size)
            else:
                # Para SELL: entrada = preço_atual + (profit / size)
                return preco_atual + (profit / size)
        except:
            return preco_atual  # Fallback
            
    def calcular_take_profit_inteligente(self, posicao, preco_atual, preco_entrada):
        """
        Calcula take profit baseado em análise técnica e R:R
        """
        direction = posicao['direction']
        stop_atual = posicao['stopLevel']
        
        if not stop_atual:
            return None
            
        # Calcular distância do stop
        distancia_stop = abs(preco_entrada - stop_atual)
        
        # Take profit baseado em Risk:Reward ratio
        if direction == 'BUY':
            take_profit = preco_entrada + (distancia_stop * self.config['take_profit_rr_ratio'])
        else:
            take_profit = preco_entrada - (distancia_stop * self.config['take_profit_rr_ratio'])
            
        self.log(f"TP calculado: Entrada {preco_entrada:.2f} | Stop {stop_atual:.2f} | TP {take_profit:.2f}")
        return take_profit
        
    def ja_esta_em_breakeven(self, stop_atual, preco_entrada, direction):
        """Verifica se stop já está em breakeven"""
        if not stop_atual:
            return False
            
        tolerancia = 5  # 5 pontos de tolerância
        
        if direction == 'BUY':
            return stop_atual >= (preco_entrada - tolerancia)
        else:
            return stop_atual <= (preco_entrada + tolerancia)
            
    def mover_stop_para_breakeven(self, deal_id, preco_entrada, epic, direction, profit):
        """
        Move stop loss para preço de entrada (breakeven)
        """
        try:
            # Adicionar pequeno buffer para garantir breakeven
            buffer = 2 if direction == 'BUY' else -2
            novo_stop = preco_entrada + buffer
            
            success = self.atualizar_stop_loss(deal_id, novo_stop)
            if success:
                self.log(f"🎯 BREAKEVEN: {epic} - Stop movido para {novo_stop:.2f} (lucro ${profit:.2f})")
                return True
        except Exception as e:
            self.log(f"Erro ao mover stop para breakeven: {e}")
        return False
        
    def aplicar_trailing_stop(self, deal_id, posicao, preco_atual, preco_entrada):
        """
        Aplica trailing stop inteligente
        """
        direction = posicao['direction']
        stop_atual = posicao['stopLevel']
        epic = posicao['epic']
        profit = posicao['profit']
        
        # Calcular novo stop baseado no trailing
        trailing_distance = self.config['trailing_distancia_pips']
        
        if direction == 'BUY':
            novo_stop = preco_atual - trailing_distance
            # Só move stop para cima
            if novo_stop > stop_atual:
                success = self.atualizar_stop_loss(deal_id, novo_stop)
                if success:
                    self.log(f"📈 TRAILING: {epic} - Stop movido de {stop_atual:.2f} para {novo_stop:.2f} (P&L ${profit:.2f})")
        else:
            novo_stop = preco_atual + trailing_distance
            # Só move stop para baixo
            if novo_stop < stop_atual:
                success = self.atualizar_stop_loss(deal_id, novo_stop)
                if success:
                    self.log(f"📉 TRAILING: {epic} - Stop movido de {stop_atual:.2f} para {novo_stop:.2f} (P&L ${profit:.2f})")
                    
    def aplicar_protecao_lucro(self, deal_id, posicao, preco_atual, preco_entrada, profit):
        """
        Protege percentual do lucro quando muito alto
        """
        direction = posicao['direction']
        stop_atual = posicao['stopLevel']
        epic = posicao['epic']
        
        # Calcular stop que protege X% do lucro
        lucro_protegido = profit * (self.config['protecao_percentual'] / 100)
        
        if direction == 'BUY':
            novo_stop = preco_atual - (profit - lucro_protegido)
            if novo_stop > stop_atual:
                success = self.atualizar_stop_loss(deal_id, novo_stop)
                if success:
                    self.log(f"🛡️ PROTEÇÃO: {epic} - Protegendo ${lucro_protegido:.2f} de ${profit:.2f}")
        else:
            novo_stop = preco_atual + (profit - lucro_protegido)
            if novo_stop < stop_atual:
                success = self.atualizar_stop_loss(deal_id, novo_stop)
                if success:
                    self.log(f"🛡️ PROTEÇÃO: {epic} - Protegendo ${lucro_protegido:.2f} de ${profit:.2f}")
                    
    def definir_take_profit(self, deal_id, take_profit, epic, direction):
        """Define take profit para uma posição"""
        try:
            success = self.api.adicionar_stop_take(deal_id, limit=take_profit)
            if success:
                self.log(f"🎯 TAKE PROFIT: {epic} - Definido em {take_profit:.2f}")
                return True
        except Exception as e:
            self.log(f"Erro ao definir take profit: {e}")
        return False
        
    def atualizar_stop_loss(self, deal_id, novo_stop):
        """Atualiza stop loss de uma posição"""
        try:
            success = self.api.adicionar_stop_take(deal_id, stop=novo_stop)
            return success
        except Exception as e:
            self.log(f"Erro ao atualizar stop loss: {e}")
            return False
            
    def relatorio_posicoes(self):
        """
        Gera relatório detalhado das posições gerenciadas
        """
        posicoes = self.api.consultar_posicoes_ativas()
        
        if not posicoes:
            self.log("Nenhuma posição ativa para relatório")
            return
            
        self.log("📊 RELATÓRIO DE POSIÇÕES GERENCIADAS:")
        self.log("=" * 50)
        
        total_profit = 0
        for pos in posicoes:
            epic = pos['epic']
            direction = pos['direction']
            size = pos['size']
            profit = pos['profit']
            stop = pos['stopLevel']
            take = pos['limitLevel']
            guaranteed = pos['guaranteedStop']
            
            total_profit += profit
            
            status_sl = f"Stop: {stop:.2f}" if stop else "Sem Stop"
            status_tp = f"TP: {take:.2f}" if take else "Sem TP"
            stop_type = "(Garantido)" if guaranteed else "(Normal)"
            
            profit_emoji = "🟢" if profit > 0 else "🔴" if profit < 0 else "⚪"
            
            self.log(f"{profit_emoji} {epic} {direction} {size}")
            self.log(f"   P&L: ${profit:.2f} | {status_sl} {stop_type} | {status_tp}")
            
        self.log("=" * 50)
        profit_emoji = "🟢" if total_profit > 0 else "🔴" if total_profit < 0 else "⚪"
        self.log(f"{profit_emoji} TOTAL P&L: ${total_profit:.2f}")


def main():
    """Função principal para teste do módulo"""
    print("🧠 INICIANDO GESTÃO INTELIGENTE DE RISCO")
    print("=" * 50)
    
    # Conectar API
    api = CapitalAPI(api_demo=True)
    api.autenticar()
    
    # Iniciar gestão de risco
    gestao = GestaoRiscoInteligente(api)
    
    # Relatório inicial
    gestao.relatorio_posicoes()
    
    print("\n⚡ Iniciando monitoramento contínuo...")
    print("   Pressione Ctrl+C para parar")
    
    # Iniciar monitoramento
    gestao.iniciar_monitoramento()

if __name__ == '__main__':
    main() 