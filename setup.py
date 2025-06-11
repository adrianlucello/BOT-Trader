import json
import time
from capital_api import CapitalAPI

# Carregar config
with open('capital_config.json', 'r') as f:
    config = json.load(f)

# Autenticação e setup
class CapitalSetup:
    def __init__(self):
        self.api = CapitalAPI()
        self.api.autenticar()
        self.saldo = self.api.saldo()['accounts'][0]['balance']['balance']
        print(f"[SETUP] Autenticado na conta demo Capital.com. Saldo: ${self.saldo:.2f}")
        self.meta_percent = 1.0  # Meta diária de 1%
        self.meta_lucro = self.saldo * (self.meta_percent / 100)
        print(f"[SETUP] Meta diária de lucro: ${self.meta_lucro:.2f}")
        self.operando = False

    def entrar_operacao(self, epic, direction, preco_entrada, stop_pips=20, rr=2.0):
        if self.operando:
            print("[SETUP] Já em operação, aguardando resultado...")
            return
        print(f"[SETUP] Entrando em operação: {direction} | Epic: {epic} | Preço: {preco_entrada}")
        regras = self.api.consultar_regras_epic(epic)
        lote_min = regras.get('minDealSize', 0.001)
        # Enviar ordem
        resposta = self.api.enviar_ordem(epic, direction, lote_min)
        print(f"[SETUP] Ordem enviada! Resposta: {resposta}")
        self.operando = True
        deal_id = resposta.get('dealId') or resposta.get('dealReference')
        # Monitorar até stop win/loss
        self.monitorar_operacao(deal_id, preco_entrada, direction, stop_pips, rr)

    def monitorar_operacao(self, deal_id, preco_entrada, direction, stop_pips, rr):
        print(f"[SETUP] Monitorando operação {deal_id}...")
        while True:
            pos = self.api.consultar_ordem(deal_id)
            if pos['status'] == 'CLOSED':
                print(f"[SETUP] Operação encerrada. Detalhes: {pos}")
                break
            # Consultar lucro/prejuízo em tempo real
            pos_aberta = self.api.consultar_posicao_aberta(deal_id=deal_id)
            if pos_aberta and pos_aberta.get('profit') is not None:
                print(f"[SETUP] Lucro/Prejuízo atual: {pos_aberta['profit']}")
            else:
                print(f"[SETUP] Operação aberta. Aguardando... (status: {pos['status']})")
            time.sleep(30)
        self.operando = False
        print("[SETUP] Pronto para nova operação!")

# Instância global para integração
capital_setup = CapitalSetup()

def executar_entrada(epic, direction, preco_entrada, stop_pips=20, rr=2.0):
    capital_setup.entrar_operacao(epic, direction, preco_entrada, stop_pips, rr)

def exibir_posicoes_abertas():
    print("\n[SETUP] Posições abertas na conta:")
    posicoes = capital_setup.api.listar_posicoes_abertas()
    if not posicoes:
        print("Nenhuma posição aberta no momento.")
        return
    for p in posicoes:
        print(f"- DealId: {p['dealId']} | Epic: {p['epic']} | Direção: {p['direcao']} | Preço entrada: {p['preco_entrada']} | Preço atual: {p['preco_atual']} | Lucro/Prejuízo: {p['lucro_prejuizo']}")

# Exibir posições abertas ao rodar o setup.py diretamente
if __name__ == '__main__':
    exibir_posicoes_abertas() 