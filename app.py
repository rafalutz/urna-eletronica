"""
=============================================================================
  PROJETO: Urna Eletrônica Universitária (Trabalho de Faculdade)
  ARQUIVO: app.py
  EXECUÇÃO: python app.py
=============================================================================
"""

import sys
import os

# Adiciona a pasta raiz e a pasta api ao caminho de importação do Python
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_ATUAL not in sys.path:
    sys.path.insert(0, DIRETORIO_ATUAL)

from api.index import app

if __name__ == "__main__":
    print("=" * 60)
    print("  🗳️  URNA ELETRÔNICA UNIVERSITÁRIA - PROJETO ACADÊMICO")
    print("  🌐  Servidor rodando em: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
