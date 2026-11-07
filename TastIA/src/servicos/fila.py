"""Módulo de Fila de Tarefas em Segundo Plano do TastIA.

Gerencia a execução assíncrona/serializada de tarefas pesadas de IA
(detecção de objetos por foto e geração de receitas) usando filas nativas e Threads.
"""

import queue
import threading
import uuid
import time
import logging
from typing import Any, Callable, Dict, Optional

# Estados possíveis de uma tarefa
ESTADO_PENDENTE = "pendente"
ESTADO_PROCESSANDO = "processando"
ESTADO_CONCLUIDO = "concluido"
ESTADO_ERRO = "erro"


class FilaTarefas:
    def __init__(self, num_workers: int = 1):
        """Inicializa a fila com 1 worker por padrão para serializar o uso pesado de CPU/RAM pelos modelos de IA."""
        self.fila = queue.Queue()
        self.resultados: Dict[str, Dict[str, Any]] = {}
        self.trava_resultados = threading.Lock()
        self.ativo = True
        self.workers = []

        for i in range(num_workers):
            t = threading.Thread(target=self._trabalhador, name=f"WorkerIA-{i+1}", daemon=True)
            t.start()
            self.workers.append(t)

    def _trabalhador(self):
        while self.ativo:
            try:
                # Aguarda até 1 segundo por uma nova tarefa para permitir encerramento limpo
                tarefa_id, funcao, args, kwargs = self.fila.get(timeout=1.0)
            except queue.Empty:
                continue

            # Atualiza estado para processando
            with self.trava_resultados:
                if tarefa_id in self.resultados:
                    self.resultados[tarefa_id]["status"] = ESTADO_PROCESSANDO
                    self.resultados[tarefa_id]["inicio_em"] = time.time()

            try:
                # Executa a função pesada (ex.: gerar_receita ou pipeline.executar)
                resultado = funcao(*args, **kwargs)

                with self.trava_resultados:
                    self.resultados[tarefa_id]["status"] = ESTADO_CONCLUIDO
                    self.resultados[tarefa_id]["resultado"] = resultado
                    self.resultados[tarefa_id]["concluido_em"] = time.time()
            except Exception as e:
                logging.exception(f"Erro ao processar tarefa {tarefa_id} na fila em segundo plano:")
                with self.trava_resultados:
                    self.resultados[tarefa_id]["status"] = ESTADO_ERRO
                    self.resultados[tarefa_id]["erro"] = str(e)
                    self.resultados[tarefa_id]["concluido_em"] = time.time()
            finally:
                self.fila.task_done()

    def submeter(self, funcao: Callable, *args, **kwargs) -> str:
        """Adiciona uma tarefa à fila e retorna seu ID único."""
        tarefa_id = str(uuid.uuid4())
        with self.trava_resultados:
            self.resultados[tarefa_id] = {
                "id": tarefa_id,
                "status": ESTADO_PENDENTE,
                "criado_em": time.time(),
                "resultado": None,
                "erro": None,
            }
        self.fila.put((tarefa_id, funcao, args, kwargs))
        return tarefa_id

    def obter_status(self, tarefa_id: str) -> Optional[Dict[str, Any]]:
        """Consulta o estado atual e resultado de uma tarefa."""
        with self.trava_resultados:
            return self.resultados.get(tarefa_id)

    def limpar_antigos(self, max_idade_segundos: int = 3600):
        """Remove resultados de tarefas antigas da memória RAM."""
        agora = time.time()
        with self.trava_resultados:
            remover = [
                tid for tid, info in self.resultados.items()
                if agora - info.get("criado_em", agora) > max_idade_segundos
            ]
            for tid in remover:
                del self.resultados[tid]


# Instância Singleton global da Fila
_fila_unica: Optional[FilaTarefas] = None
_trava_singleton = threading.Lock()


def obter_fila() -> FilaTarefas:
    global _fila_unica
    with _trava_singleton:
        if _fila_unica is None:
            _fila_unica = FilaTarefas(num_workers=1)
    return _fila_unica