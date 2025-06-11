import threading
import time

class Paciencia:
    def __init__(self, get_entrada_executada, trocar_par_callback, get_par_atual, get_proximo_par, tempo_minutos=15):
        self.get_entrada_executada = get_entrada_executada  # Função que retorna True se houve entrada
        self.trocar_par_callback = trocar_par_callback      # Função para trocar de par
        self.get_par_atual = get_par_atual                  # Função para saber o par atual
        self.get_proximo_par = get_proximo_par              # Função para saber o próximo par
        self.tempo_minutos = tempo_minutos
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._stop_event.clear()
        if not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            par = self.get_par_atual()
            print(f'[PACIENCIA] Iniciando timer de {self.tempo_minutos} minutos para o par {par}...')
            tempo_restante = self.tempo_minutos * 60
            while tempo_restante > 0 and not self._stop_event.is_set():
                if self.get_entrada_executada():
                    print(f'[PACIENCIA] Entrada executada em {par}, resetando timer.')
                    break
                time.sleep(5)
                tempo_restante -= 5
            else:
                # Timer acabou sem entrada
                if not self.get_entrada_executada():
                    proximo = self.get_proximo_par()
                    print(f'[PACIENCIA] Volume fraco em {par}, pulando para o próximo ativo: {proximo}')
                    self.trocar_par_callback()
            # Aguarda um pouco antes de reiniciar o ciclo
            time.sleep(2) 