import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_DIR = os.path.join(BASE_DIR, 'banco_dados')
DB_PATH = os.path.join(DB_DIR, 'tastia.db')
MODELS_DIR = os.path.join(BASE_DIR, 'modelos_huggingface')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'chave-padrao-fallback-insegura'
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    
    MODELOS = {
        "deteccao_objetos": "florence-community/Florence-2-base",
        "classificacao_ingredientes": "openai/clip-vit-base-patch32",
        "geracao_receita": "HuggingFaceTB/SmolLM3-3B",
        "recomendacao_bebida": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    }