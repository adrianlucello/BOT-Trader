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
        # epic: código do ativo (ex: 'CS.D.EURUSD.MINI.IP')
        # direction: 'BUY' ou 'SELL'
        # size: lote
        # order_type: 'MARKET' ou 'LIMIT'
        # stop/limit: preço de SL/TP
        pass

if __name__ == '__main__':
    api = CapitalAPI()
    api.autenticar()
    saldo = api.saldo()
    print('Saldo da conta:', json.dumps(saldo, indent=2, ensure_ascii=False)) 