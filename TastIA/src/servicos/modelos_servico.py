import os
from huggingface_hub import snapshot_download
from config import Config, MODELS_DIR

def garantir_diretorio_modelos():
    if not os.path.exists(MODELS_DIR):
        os.makedirs(MODELS_DIR)
        print(f"Pasta criada com sucesso: {MODELS_DIR}")

def baixar_ou_carregar_modelos():
    garantir_diretorio_modelos()

    print("=== A verificar e a carregar modelos de IA ===")
    
    for chave, repo_id in Config.MODELOS.items():
        pasta_modelo = os.path.join(MODELS_DIR, chave)
        
        print(f"-> A verificar o modelo [{chave}] ({repo_id})...")
        
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=pasta_modelo,
                local_dir_use_symlinks=False,
                resume_download=True
            )
            print(f"   Sucesso: Modelo {chave} pronto para uso local.")
        except Exception as e:
            print(f"   Aviso/Erro ao carregar o modelo {chave}: {e}")
            print("   (Certifique-se de que tem ligação à internet na primeira execução para o download inicial).")

    print("Processo de modelos concluído")
