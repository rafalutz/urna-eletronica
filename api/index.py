import os
import sys

# Adiciona o diretorio raiz ao sys.path para importar o app Flask
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app
