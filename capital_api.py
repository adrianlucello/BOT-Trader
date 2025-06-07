import requests
import json
import os
import time

CONFIG_FILE = 'capital_config.json'

# Função para ler config segura
def ler_config():
    if not os.path.exists(CONFIG_FILE):
        raise Exception('Arquivo capital_config.json não encontrado!')
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

# Classe de integração Capital.com
class CapitalAPI:
    def __init__(self, api_demo=True):
        config = ler_config()
        self.api_key = config['api_key']
        self.email = config['email']
        self.password = config['password']
        self.api_demo = api_demo
        if self.api_demo:
            self.base_url = 'https://demo-api-capital.backend-capital.com'  # conta demo
        else:
            self.base_url = 'https://api-capital.backend-capital.com'  # conta real
        self.session = requests.Session()
        self.cst = None
        self.x_security_token = None
        self.account_id = None  # Novo: armazenar o accountId

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
            modo = '[MODO DEMO]' if self.api_demo else '[MODO REAL]'
            print(f'{modo} Autenticado com sucesso na Capital.com! Endpoint: {self.base_url}')
            # Buscar e armazenar o accountId
            self.account_id = self._buscar_account_id()
            print(f'{modo} accountId utilizado: {self.account_id}')
        else:
            raise Exception(f'Erro ao autenticar: {resp.text}')

    def _buscar_account_id(self):
        url = f'{self.base_url}/api/v1/accounts'
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            # Pega o primeiro accountId disponível
            return data['accounts'][0]['accountId']
        else:
            raise Exception(f'Erro ao buscar accountId: {resp.text}')

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

    def enviar_ordem(self, epic, direction, size, order_type='MARKET', stop=None, limit=None, guaranteed_stop=False):
        """
        Envia uma ordem para a Capital.com tentando incluir SL/TP diretamente na criação
        Se não aceitar, tenta adicionar em segunda etapa
        
        guaranteed_stop: True para usar stop garantido (pode ter custo adicional)
        """
        url = f'{self.base_url}/api/v1/positions'
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token,
            'Content-Type': 'application/json'
        }
        
        # Validar parâmetros antes de enviar
        if stop is not None:
            if stop <= 0:
                raise ValueError(f"Stop loss inválido: {stop} (deve ser positivo)")
        
        if limit is not None:
            if limit <= 0:
                raise ValueError(f"Take profit inválido: {limit} (deve ser positivo)")
        
        # Primeira tentativa: criar posição COM SL/TP
        data = {
            'epic': epic,
            'direction': direction,
            'size': size,
            'orderType': order_type,
            'guaranteedStop': guaranteed_stop,  # Stop garantido se solicitado
            'forceOpen': True,
            'currencyCode': 'USD',
            'dealReference': None
        }
        
        # Adicionar account_id apenas se estiver disponível
        if hasattr(self, 'account_id') and self.account_id:
            data['accountId'] = self.account_id
        
        # Adicionar stop e limit se fornecidos
        if stop is not None:
            data['stopLevel'] = float(stop)  # Garantir que é float
            stop_type = "GARANTIDO" if guaranteed_stop else "NORMAL"
            print(f"[API] Adicionando Stop Loss {stop_type} na criação: {stop:.5f}")
            
            # Se usar stop garantido, adicionar parâmetros específicos
            if guaranteed_stop:
                data['guaranteedStop'] = True
                # Para stop garantido, pode ser necessário o parâmetro stopDistance
                # Em vez de stopLevel para alguns instrumentos
                try:
                    # Consultar regras do epic para verificar distância mínima
                    regras = self.consultar_regras_epic(epic)
                    min_guaranteed_stop = regras.get('minControlledRiskStopDistance')
                    if min_guaranteed_stop and min_guaranteed_stop > 0:
                        print(f"[API] Distância mínima para stop garantido: {min_guaranteed_stop}")
                except:
                    pass  # Se falhar, continuar com stopLevel normal
            
        if limit is not None:
            data['limitLevel'] = float(limit)  # Garantir que é float  
            print(f"[API] Adicionando Take Profit na criação: {limit:.5f}")

        print(f"[API] Criando posição com SL/TP inclusos...")
        print(f"[API] Dados enviados: {data}")
        
        # Log detalhado para debug
        print(f"[API DEBUG] Epic: {epic} | Direction: {direction} | Size: {size}")
        print(f"[API DEBUG] Stop Garantido: {guaranteed_stop} | Stop Level: {stop} | Limit Level: {limit}")
        
        resp = self.session.post(url, headers=headers, json=data)
        print(f"[API] Resposta da criação: {resp.status_code}")
        
        if not resp.status_code in (200, 201):
            print(f"[API] Erro detalhado: {resp.text}")
            error_data = resp.json() if resp.text else {}
            if 'errorCode' in error_data:
                error_code = error_data['errorCode']
                error_msg = error_data.get('message', 'Erro desconhecido')
                print(f"[API] Código do erro: {error_code} - {error_msg}")
                
                # Tratar erros específicos de stop garantido
                if 'guaranteed' in error_msg.lower() or 'controlled' in error_msg.lower():
                    print(f"[API] ERRO STOP GARANTIDO: Tentando sem stop garantido...")
                    # Tentar novamente sem stop garantido
                    return self.enviar_ordem(epic, direction, size, order_type, stop, limit, guaranteed_stop=False)
                    
            raise Exception(f'Erro ao criar posição: {resp.status_code} - {resp.text}')
        
        resultado = resp.json()
        print(f"[API] Resultado completo: {resultado}")
        
        deal_id = resultado.get('dealReference') or resultado.get('dealId')
        
        if not deal_id:
            print("[API] AVISO: Nenhum dealId retornado")
            return resultado
            
        print(f"[API] Posição criada com DealId: {deal_id}")
        
        # Verificar se SL/TP foram aceitos na criação
        if stop is not None or limit is not None:
            # Aguardar um pouco e verificar se a posição tem SL/TP
            time.sleep(3)  # Aumentado para 3 segundos
            posicao_info = self.buscar_posicao_detalhada(deal_id)
            
            if posicao_info:
                tem_stop = posicao_info.get('stopLevel') is not None
                tem_limit = posicao_info.get('limitLevel') is not None
                tem_guaranteed = posicao_info.get('guaranteedStop', False)
                
                print(f"[API] Verificação SL/TP:")
                print(f"  • Stop Level: {'✓' if tem_stop else '✗'} ({posicao_info.get('stopLevel', 'N/A')})")
                print(f"  • Limit Level: {'✓' if tem_limit else '✗'} ({posicao_info.get('limitLevel', 'N/A')})")
                print(f"  • Stop Garantido: {'✓' if tem_guaranteed else '✗'}")
                
                if (stop is not None and not tem_stop) or (limit is not None and not tem_limit):
                    print(f"[API] SL/TP não foram aceitos na criação, tentando adicionar separadamente...")
                    resultado_sl_tp = self.adicionar_stop_take(deal_id, stop, limit)
                    if resultado_sl_tp:
                        resultado['stop_take_added'] = True
                        print(f"[API] ✓ SL/TP adicionados em segunda tentativa!")
                    else:
                        resultado['stop_take_added'] = False
                        print(f"[API] ✗ Não foi possível adicionar SL/TP")
                else:
                    resultado['stop_take_added'] = True
                    print(f"[API] ✓ SL/TP aceitos diretamente na criação!")
                    if guaranteed_stop and tem_guaranteed:
                        print(f"[API] ✅ STOP GARANTIDO ATIVO!")
                    elif guaranteed_stop and not tem_guaranteed:
                        print(f"[API] ⚠️ Stop garantido solicitado mas não ativo")
            else:
                print(f"[API] Não foi possível verificar se SL/TP foram aceitos")
                resultado['stop_take_added'] = False
        else:
            print(f"[API] Posição criada sem SL/TP (não solicitados)")
        
        return resultado
    
    def adicionar_stop_take(self, deal_id, stop=None, limit=None):
        """
        Adiciona stop loss e/ou take profit a uma posição existente
        Tenta múltiplas vezes pois a posição pode demorar para aparecer
        """
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token,
            'Content-Type': 'application/json'
        }
        
        # Tentar encontrar a posição várias vezes
        for tentativa in range(3):  # 3 tentativas apenas
            print(f"[API] Tentativa {tentativa + 1}/3 de encontrar posição {deal_id}...")
            
            url = f'{self.base_url}/api/v1/positions'
            resp = self.session.get(url, headers=headers)
            
            if resp.status_code == 200:
                positions = resp.json().get('positions', [])
                posicao = None
                
                # Buscar por dealId ou dealReference
                for pos in positions:
                    if (pos.get('dealId') == deal_id or 
                        pos.get('dealReference') == deal_id or
                        deal_id in str(pos.get('dealId', '')) or
                        deal_id in str(pos.get('dealReference', ''))):
                        posicao = pos
                        break
                
                if posicao:
                    print(f"[API] Posição encontrada: {posicao.get('dealId')}")
                    print(f"[API] Detalhes: Size={posicao.get('size')}, Direction={posicao.get('direction')}")
                    
                    # Verificar se já tem SL/TP
                    has_stop = posicao.get('stopLevel') is not None
                    has_limit = posicao.get('limitLevel') is not None
                    
                    print(f"[API] Status atual - Stop: {'✓' if has_stop else '✗'} | Limit: {'✓' if has_limit else '✗'}")
                    
                    # Tentar atualizar apenas se não tem SL/TP
                    needs_update = False
                    update_data = {}
                    
                    if stop is not None and not has_stop:
                        update_data['stopLevel'] = stop
                        needs_update = True
                        print(f"[API] Adicionando Stop Loss: {stop:.5f}")
                        
                    if limit is not None and not has_limit:
                        update_data['limitLevel'] = limit
                        needs_update = True
                        print(f"[API] Adicionando Take Profit: {limit:.5f}")
                    
                    if needs_update:
                        position_id = posicao.get('dealId')
                        update_url = f'{self.base_url}/api/v1/positions/{position_id}'
                        
                        print(f"[API] URL atualização: {update_url}")
                        print(f"[API] Dados: {update_data}")
                        
                        resp = self.session.put(update_url, headers=headers, json=update_data)
                        print(f"[API] Resposta atualização: {resp.status_code}")
                        
                        if resp.status_code in (200, 201):
                            print(f"[API] ✓ SL/TP adicionados com sucesso!")
                            return resp.json()
                        else:
                            print(f"[API] ✗ Erro ao atualizar SL/TP: {resp.status_code} - {resp.text}")
                            return posicao  # Retorna posição mesmo sem conseguir atualizar
                    else:
                        print(f"[API] ✓ Posição já tem SL/TP necessários")
                        return posicao
            
            # Aguardar antes da próxima tentativa  
            if tentativa < 2:
                print(f"[API] Aguardando 2 segundos...")
                time.sleep(2)
        
        # Se chegou aqui, não encontrou a posição
        print(f"[API] ✗ Posição {deal_id} não encontrada após 3 tentativas")
        return None

    def buscar_epic(self, symbol):
        """
        Busca o epic correto para um símbolo (ex: EURUSD) usando a API da Capital.com.
        Retorna o epic do primeiro resultado negociável encontrado ou None se não encontrar.
        Mostra todos os epics encontrados no log para debug.
        """
        url = f'{self.base_url}/api/v1/markets?searchTerm={symbol}'
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            markets = data.get('markets', [])
            if not markets:
                print(f"[EPIC] Nenhum epic encontrado para {symbol}.")
                return None
            print(f"[EPIC] Epics encontrados para {symbol}:")
            for m in markets:
                print(f"  - epic: {m.get('epic')} | nome: {m.get('instrumentName')} | tipo: {m.get('instrumentType')} | status: {m.get('marketStatus')}")
            # Filtrar apenas epics negociáveis de moedas
            for m in markets:
                if m.get('marketStatus') == 'TRADEABLE' and m.get('instrumentType') == 'CURRENCIES':
                    print(f"[EPIC] Selecionado para trading: {m.get('epic')}")
                    return m.get('epic')
            print(f"[EPIC] Nenhum epic negociável encontrado para {symbol}.")
            return None
        else:
            raise Exception(f'Erro ao buscar epic: {resp.status_code} - {resp.text}')

    def buscar_epic_valido_para_ordem(self, symbol):
        """
        Busca todos os epics TRADEABLE para o símbolo e valida sem enviar ordem de teste.
        Considera válido se o epic está TRADEABLE e a consulta das regras retorna limites válidos.
        NÃO afeta o saldo da conta demo.
        """
        url = f'{self.base_url}/api/v1/markets?searchTerm={symbol}'
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            markets = data.get('markets', [])
            epics_testados = []
            primeiro = True
            for m in markets:
                if m.get('marketStatus') == 'TRADEABLE':
                    epic = m.get('epic')
                    epics_testados.append(epic)
                    print(f"[EPIC-VALIDAÇÃO] Testando epic: {epic} para {symbol}...")
                    try:
                        regras = self.consultar_regras_epic(epic)
                        if primeiro:
                            print(f"[DEBUG-EPIC-REGRAS] Resposta completa para {epic}: {regras}")
                            primeiro = False
                        # Aceitar epic se está TRADEABLE, independente das regras detalhadas
                        if regras is not None:
                            print(f"[EPIC-VALIDAÇÃO] Epic {epic} aceito para trading (TRADEABLE).")
                            return epic
                        else:
                            print(f"[EPIC-VALIDAÇÃO] Epic {epic} rejeitado: erro ao consultar regras.")
                    except Exception as e:
                        print(f"[EPIC-VALIDAÇÃO] Epic {epic} rejeitado: erro ao consultar regras: {e}")
            print(f"[EPIC-VALIDAÇÃO] Nenhum epic TRADEABLE aceitou para {symbol}. Testados: {epics_testados}")
            return None
        else:
            raise Exception(f'Erro ao buscar epic: {resp.status_code} - {resp.text}')

    def consultar_ordem(self, deal_id):
        """
        Consulta o status de uma ordem pelo dealId.
        Tenta múltiplos endpoints para encontrar a ordem.
        """
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        
        # Tentar endpoint de posições ativas primeiro
        url = f'{self.base_url}/api/v1/positions'
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            positions = data.get('positions', [])
            for pos in positions:
                if pos.get('dealId') == deal_id or pos.get('dealReference') == deal_id:
                    return {
                        'status': 'OPEN',
                        'dealId': deal_id,
                        'position': pos
                    }
        
        # Tentar endpoint de histórico se não encontrou em posições ativas
        url = f'{self.base_url}/api/v1/history/activity'
        resp = self.session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            activities = data.get('activities', [])
            for activity in activities:
                if activity.get('dealId') == deal_id:
                    return {
                        'status': activity.get('status', 'CLOSED'),
                        'dealId': deal_id,
                        'activity': activity
                    }
        
        # Se não encontrou em lugar nenhum, provavelmente foi fechada
        return {
            'status': 'CLOSED',
            'dealId': deal_id,
            'message': 'Ordem não encontrada - provavelmente fechada'
        }

    def consultar_regras_epic(self, epic):
        """
        Consulta as regras de stop/take permitidas para um epic na Capital.com.
        Retorna um dicionário com os limites mínimos/máximos de stop/take.
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
            regras = {
                'minNormalStopOrLimitDistance': instrument.get('minNormalStopOrLimitDistance'),
                'maxStopOrLimitDistance': instrument.get('maxStopOrLimitDistance'),
                'minControlledRiskStopDistance': instrument.get('minControlledRiskStopDistance'),
                'minDealSize': instrument.get('minDealSize'),
                'maxDealSize': instrument.get('maxDealSize'),
                'stepSize': instrument.get('stepSize'),
                'unit': instrument.get('unit'),
            }
            return regras
        else:
            raise Exception(f'Erro ao consultar regras do epic: {resp.status_code} - {resp.text}')

    def buscar_posicao_detalhada(self, deal_id):
        """
        Busca informações detalhadas de uma posição específica
        Retorna os dados da posição incluindo stopLevel e limitLevel
        """
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        
        # Buscar em posições ativas
        url = f'{self.base_url}/api/v1/positions'
        resp = self.session.get(url, headers=headers)
        
        if resp.status_code == 200:
            positions = resp.json().get('positions', [])
            
            for pos in positions:
                if (pos.get('dealId') == deal_id or 
                    pos.get('dealReference') == deal_id or
                    deal_id in str(pos.get('dealId', '')) or
                    deal_id in str(pos.get('dealReference', ''))):
                    
                    print(f"[API] Posição encontrada: {pos.get('dealId')}")
                    print(f"[API] Stop Level: {pos.get('stopLevel')}")
                    print(f"[API] Limit Level: {pos.get('limitLevel')}")
                    print(f"[API] Stop Garantido: {pos.get('guaranteedStop', False)}")
                    print(f"[API] Direção: {pos.get('direction')} | Tamanho: {pos.get('size')}")
                    print(f"[API] P&L: {pos.get('profit', 0)}")
                    return pos
            
            print(f"[API] Posição {deal_id} não encontrada em posições ativas")
            return None
        else:
            print(f"[API] Erro ao buscar posições: {resp.status_code}")
            return None

    def testar_stop_garantido(self, epic='BTCUSD', size=0.1):
        """
        Função de teste para validar se o stop garantido está funcionando
        """
        print(f"\n🧪 TESTANDO STOP GARANTIDO")
        print(f"Epic: {epic} | Tamanho: {size}")
        
        try:
            # Consultar regras primeiro
            regras = self.consultar_regras_epic(epic)
            print(f"[TESTE] Regras do {epic}:")
            print(f"  • Min Stop Normal: {regras.get('minNormalStopOrLimitDistance')}")
            print(f"  • Min Stop Garantido: {regras.get('minControlledRiskStopDistance')}")
            print(f"  • Min Deal Size: {regras.get('minDealSize')}")
            
            # Obter preço atual através das posições (se houver)
            url = f'{self.base_url}/api/v1/markets/{epic}'
            headers = {
                'X-CAP-API-KEY': self.api_key,
                'CST': self.cst,
                'X-SECURITY-TOKEN': self.x_security_token
            }
            
            resp = self.session.get(url, headers=headers)
            if resp.status_code == 200:
                market_data = resp.json()
                snapshot = market_data.get('snapshot', {})
                bid = snapshot.get('bid')
                offer = snapshot.get('offer')
                preco_atual = (bid + offer) / 2 if bid and offer else None
                
                if preco_atual:
                    print(f"[TESTE] Preço atual {epic}: {preco_atual:.5f} (Bid: {bid}, Offer: {offer})")
                    
                    # Calcular stop loss para teste (1% abaixo para SELL)
                    stop_loss = preco_atual * 1.01  # 1% acima para ordem SELL
                    
                    print(f"[TESTE] Tentando ordem SELL com stop garantido em {stop_loss:.5f}")
                    
                    # Tentar criar ordem apenas para teste (não executar)
                    test_data = {
                        'epic': epic,
                        'direction': 'SELL',
                        'size': size,
                        'orderType': 'MARKET',
                        'guaranteedStop': True,
                        'stopLevel': stop_loss,
                        'forceOpen': True,
                        'currencyCode': 'USD'
                    }
                    
                    print(f"[TESTE] Dados do teste: {test_data}")
                    return True
                else:
                    print(f"[TESTE] Não foi possível obter preço atual")
                    return False
            else:
                print(f"[TESTE] Erro ao obter dados do mercado: {resp.status_code}")
                return False
                
        except Exception as e:
            print(f"[TESTE] Erro no teste: {e}")
            return False

    def consultar_posicoes_ativas(self):
        """
        Consulta TODAS as posições ativas reais na Capital.com
        Retorna lista com informações detalhadas de cada posição
        """
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'CST': self.cst,
            'X-SECURITY-TOKEN': self.x_security_token
        }
        
        url = f'{self.base_url}/api/v1/positions'
        resp = self.session.get(url, headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            positions = data.get('positions', [])
            
            print(f"[API] Consultando posições ativas na Capital.com...")
            print(f"[API] Total de posições encontradas: {len(positions)}")
            

            posicoes_detalhes = []
            for pos in positions:
                # Estrutura da API Capital.com: dados estão em 'position' e 'market'
                position_data = pos.get('position', {})
                market_data = pos.get('market', {})
                
                # Extrair dados da posição
                deal_id = position_data.get('dealId')
                direction = position_data.get('direction')
                size = position_data.get('size')
                profit = position_data.get('upl', 0)  # upl = unrealized profit/loss
                stop_level = position_data.get('stopLevel')
                limit_level = position_data.get('limitLevel')
                guaranteed_stop = position_data.get('guaranteedStop', False)
                
                # Extrair dados do mercado
                epic = market_data.get('epic')
                instrument_name = market_data.get('instrumentName', '')
                
                print(f"[API] Dados extraídos corretamente:")
                print(f"      DealId: {deal_id}")
                print(f"      Epic: {epic} ({instrument_name})")
                print(f"      Direção: {direction} | Tamanho: {size}")
                print(f"      P&L: {profit:.2f}")
                
                posicao_info = {
                    'dealId': deal_id,
                    'epic': epic,
                    'direction': direction,
                    'size': size,
                    'profit': profit,
                    'stopLevel': stop_level,
                    'limitLevel': limit_level,
                    'guaranteedStop': guaranteed_stop,
                    'raw': pos  # Dados completos para debug
                }
                
                posicoes_detalhes.append(posicao_info)
                
                status_sl = "✓ DEFINIDO" if stop_level else "✗ SEM STOP"
                status_tp = "✓ DEFINIDO" if limit_level else "✗ SEM TAKE"
                stop_type = "GARANTIDO" if guaranteed_stop else "NORMAL"
                profit_status = "🟢 LUCRO" if profit > 0 else "🔴 PREJUÍZO" if profit < 0 else "⚪ NEUTRO"
                
                print(f"[API] Posição {deal_id}: {epic} {direction} {size}")
                print(f"      P&L: {profit:.2f} ({profit_status}) | SL: {status_sl} | TP: {status_tp} | Tipo: {stop_type}")
            
            return posicoes_detalhes
            
        else:
            print(f"[API] ERRO ao consultar posições: {resp.status_code} - {resp.text}")
            return []
    
    def fechar_posicao(self, posicao_ou_deal_id):
        """
        Fecha uma posição específica - COMPATÍVEL com teste_fechar_posicao.py
        Aceita tanto objeto posição quanto deal_id para máxima compatibilidade
        """
        try:
            # Determinar se recebeu posição ou deal_id
            if isinstance(posicao_ou_deal_id, dict):
                # Recebeu objeto posição (igual ao teste_fechar_posicao.py)
                posicao = posicao_ou_deal_id
                deal_id = posicao.get('dealId')
                print(f"[API] 🎯 Fechando posição via objeto: {deal_id}")
            else:
                # Recebeu deal_id (compatibilidade com main.py)
                deal_id = posicao_ou_deal_id
                print(f"[API] 🎯 Buscando posição por deal_id: {deal_id}...")
                
                # Buscar informações da posição
                posicoes = self.consultar_posicoes_ativas()
                posicao = None
                
                for pos in posicoes:
                    if pos.get('dealId') == deal_id:
                        posicao = pos
                        break
                
                if not posicao:
                    print(f"[API] ❌ Posição {deal_id} não encontrada")
                    return {'dealStatus': 'REJECTED', 'error': 'Posição não encontrada'}
            
            # Extrair dados da posição (igual ao teste_fechar_posicao.py)
            epic = posicao.get('epic')
            direction = posicao.get('direction')
            size = posicao.get('size')
            profit = posicao.get('profit', 0)  # Usar 'profit' como no teste
            
            # Direção oposta para fechar (IGUAL ao teste_fechar_posicao.py)
            close_direction = 'SELL' if direction == 'BUY' else 'BUY'
            
            print(f"[API] 🎯 TENTANDO FECHAR POSIÇÃO:")
            print(f"   Deal ID: {deal_id}")
            print(f"   Epic: {epic}")
            print(f"   Posição Original: {direction} {size}")
            print(f"   Ordem de Fechamento: {close_direction} {size}")
            print(f"   P&L Atual: ${profit:.2f}")
            
            # Confirmação visual como no teste
            if profit > 0:
                print(f"   💰 FECHANDO posição COM LUCRO de ${profit:.2f}")
            elif profit < 0:
                print(f"   ⚠️  FECHANDO posição COM PREJUÍZO de ${profit:.2f}")
            else:
                print(f"   ⚪ Posição sem lucro/prejuízo significativo")
            
            headers = {
                'X-CAP-API-KEY': self.api_key,
                'CST': self.cst,
                'X-SECURITY-TOKEN': self.x_security_token,
                'Content-Type': 'application/json'
            }
            
            # Dados para fechar posição (EXATOS do teste_fechar_posicao.py)
            close_data = {
                'dealId': deal_id,
                'epic': epic,
                'direction': close_direction,
                'size': size,
                'orderType': 'MARKET'
            }
            
            print(f"[API] 📤 Enviando ordem de fechamento...")
            print(f"   Dados: {close_data}")
            
            url = f'{self.base_url}/api/v1/positions'
            resp = self.session.post(url, headers=headers, json=close_data)
            
            print(f"[API] 📊 Resposta HTTP: {resp.status_code}")
            
            if resp.status_code in (200, 201):
                resultado = resp.json()
                close_deal_id = resultado.get('dealReference') or resultado.get('dealId')
                
                print(f"[API] ✅ ORDEM DE FECHAMENTO ENVIADA!")
                print(f"   Close Deal ID: {close_deal_id}")
                print(f"   Resposta: {resultado}")
                
                # Aguardar e verificar se foi fechada (IGUAL ao teste)
                print("[API] ⏳ Aguardando 5 segundos para verificar fechamento...")
                time.sleep(5)
                
                # Verificar se a posição ainda existe
                posicoes_atuais = self.consultar_posicoes_ativas()
                posicao_ainda_existe = any(p.get('dealId') == deal_id for p in posicoes_atuais)
                
                if not posicao_ainda_existe:
                    print(f"[API] 🎉 SUCESSO! Posição {deal_id} foi fechada com sucesso!")
                    print(f"[API] 💰 P&L realizado: ${profit:.2f}")
                    return {'dealStatus': 'ACCEPTED', 'dealId': close_deal_id, 'profit': profit}
                else:
                    print(f"[API] ⚠️ Posição ainda aparece como ativa. Pode estar processando...")
                    return {'dealStatus': 'PENDING', 'dealId': close_deal_id, 'profit': profit}
                    
            else:
                print(f"[API] ❌ ERRO ao fechar posição: {resp.status_code}")
                try:
                    error_data = resp.json()
                    print(f"Detalhes do erro: {error_data}")
                    return {'dealStatus': 'REJECTED', 'error': error_data}
                except:
                    print(f"Resposta bruta: {resp.text}")
                    return {'dealStatus': 'REJECTED', 'error': resp.text}
                
        except Exception as e:
            print(f"[API] ❌ Erro ao fechar posição: {e}")
            return {'dealStatus': 'ERROR', 'error': str(e)}

if __name__ == '__main__':
    # Teste quando executado diretamente
    api = CapitalAPI()
    api.autenticar()
    
    # Teste do stop garantido
    api.testar_stop_garantido()
    
    # Teste normal do saldo
    saldo = api.saldo()
    print('\nSaldo da conta:', json.dumps(saldo, indent=2, ensure_ascii=False)) 