import requests
import json
import os

CONFIG_FILE = 'capital_config.json'

# Função para ler config segura
def ler_config():
    if not os.path.exists(CONFIG_FILE):
        raise Exception('Arquivo capital_config.json não encontrado!')
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

# Classe de integração Capital.com
class CapitalAPI:
    def __init__(self):
        config = ler_config()
        self.api_key = config['api_key']
        self.email = config['email']
        self.password = config['password']
        self.base_url = 'https://demo-api-capital.backend-capital.com'  # para conta demo
        self.session = requests.Session()
        self.cst = None
        self.x_security_token = None

    def autenticar(self):
        url = f'{self.base_url}/api/v1/session'
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }
        data = {
            'identifier': self.email,
            'password': self.password
        }
        resp = self.session.post(url, headers=headers, json=data)
        if resp.status_code == 200:
            self.cst = resp.headers.get('CST')
            self.x_security_token = resp.headers.get('X-SECURITY-TOKEN')
            print('Autenticado com sucesso na Capital.com!')
        else:
            raise Exception(f'Erro ao autenticar: {resp.text}')

    def saldo(self):
        url = f'{self.base_url}/api/v1/accounts'
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            return data
        else:
            raise Exception(f'Erro ao consultar saldo: {resp.text}')

    # Estrutura para envio de ordens (a implementar)
    def enviar_ordem(self, epic, direction, size, order_type='MARKET', stop=None, limit=None):
        url = f"{self.base_url}/api/v1/positions"
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token,
            'Content-Type': 'application/json'
        }
        data = {
            "epic": epic,
            "direction": direction,
            "size": size,
            "orderType": order_type,
            "currencyCode": "USD"
        }
        if stop is not None:
            data["stopLevel"] = stop
        if limit is not None:
            data["limitLevel"] = limit
        resp = self.session.post(url, headers=headers, json=data)
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            print(f"Erro ao enviar ordem: {resp.status_code} - {resp.text}")
            return None

    def consultar_regras_epic(self, epic):
        """
        Consulta as regras de negociação (minDealSize, etc) para um epic.
        """
        url = f'{self.base_url}/api/v1/markets/{epic}'
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            instrument = data.get('instrument', {})
            return instrument
        else:
            raise Exception(f'Erro ao consultar regras do epic: {resp.status_code} - {resp.text}')

    def consultar_ordem(self, deal_id):
        """
        Consulta o status de uma ordem pelo dealReference (deal_id).
        Retorna status, lucro/prejuízo atual e preço atual, se disponíveis.
        """
        url = f"{self.base_url}/api/v1/confirms/{deal_id}"
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get('status', 'UNKNOWN')
            # Tentar extrair lucro/prejuízo e preço atual
            profit = None
            price = None
            # Verifica se há deals ou affectedDeals
            deals = data.get('affectedDeals') or data.get('deals')
            if deals and isinstance(deals, list) and len(deals) > 0:
                deal_info = deals[0]
                profit = deal_info.get('profitAndLoss') or deal_info.get('profit')
                price = deal_info.get('level') or deal_info.get('openLevel')
            return {
                'status': status,
                'profit': profit,
                'price': price,
                'detalhes': data
            }
        else:
            return {'status': 'UNKNOWN', 'erro': resp.text}

    def consultar_posicao_aberta(self, deal_id=None, epic=None):
        url = f"{self.base_url}/api/v1/positions"
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            positions = data.get('positions', [])
            for pos in positions:
                # Suporte a ambos formatos: dict direto ou dict com 'position'
                p = pos.get('position', pos)
                if (deal_id and p.get('dealId') == deal_id) or (epic and (p.get('epic') == epic or pos.get('epic') == epic)):
                    # Pega o P&L em tempo real ('upl'), se não houver, tenta 'profitAndLoss'
                    pnl = p.get('upl')
                    if pnl is None:
                        pnl = p.get('profitAndLoss')
                    return {
                        'status': 'OPEN',
                        'profit': pnl,
                        'price': p.get('level'),
                        'detalhes': pos
                    }
            return {'status': 'NOT_FOUND'}
        else:
            return {'status': 'UNKNOWN', 'erro': resp.text}

    def listar_posicoes_abertas(self):
        """
        Retorna uma lista de todas as posições abertas com P&L em tempo real, epic, direção, preço de entrada e preço atual.
        """
        url = f"{self.base_url}/api/v1/positions"
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            positions = data.get('positions', [])
            resultado = []
            for pos in positions:
                # Alguns campos podem estar em subdicionários dependendo do formato
                p = pos.get('position', pos)
                m = pos.get('market', {})
                resultado.append({
                    'dealId': p.get('dealId'),
                    'epic': p.get('epic') or m.get('epic'),
                    'direcao': p.get('direction'),
                    'preco_entrada': p.get('level'),
                    'preco_atual': m.get('bid') or m.get('offer'),
                    'lucro_prejuizo': p.get('upl') or p.get('profitAndLoss'),
                    'detalhes': pos
                })
            return resultado
        else:
            raise Exception(f'Erro ao listar posições abertas: {resp.status_code} - {resp.text}')

if __name__ == '__main__':
    api = CapitalAPI()
    api.autenticar()
    saldo = api.saldo()
    print('Saldo da conta:', json.dumps(saldo, indent=2, ensure_ascii=False)) 