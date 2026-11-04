import os
import json
import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for

app = Flask(__name__)

# Arquivos de persistência
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ELEITORES_DB_FILE = os.path.join(BASE_DIR, "eleitores_votados.json")
VOTOS_DB_FILE = os.path.join(BASE_DIR, "votos.json")

# Lista oficial de candidatos
CANDIDATOS = [
    {
        "numero": "10",
        "nome": "Ana Silva",
        "partido": "PARTIDO A",
        "vice": "Carlos Lima",
        "foto_char": "👩",
        "cor": "#3b82f6"  # Azul
    },
    {
        "numero": "20",
        "nome": "Bruno Santos",
        "partido": "PARTIDO B",
        "vice": "Diana Costa",
        "foto_char": "👨",
        "cor": "#10b981"  # Verde
    },
    {
        "numero": "30",
        "nome": "Clara Melo",
        "partido": "PARTIDO C",
        "vice": "Eduardo Neto",
        "foto_char": "👩",
        "cor": "#8b5cf6"  # Roxo
    },
    {
        "numero": "40",
        "nome": "Daniel Rocha",
        "partido": "PARTIDO D",
        "vice": "Fernanda Dias",
        "foto_char": "👨",
        "cor": "#f59e0b"  # Laranja
    },
    {
        "numero": "50",
        "nome": "Elena Braga",
        "partido": "PARTIDO E",
        "vice": "Gabriel Souza",
        "foto_char": "👩",
        "cor": "#ec4899"  # Rosa
    },
]

def carregar_json(arquivo, padrao):
    if os.path.exists(arquivo):
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return padrao
    return padrao

def salvar_json(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def sanitizar_sigilo_votos(votos):
    """
    Garante o sigilo do voto:
    Remove qualquer campo de identificação de eleitor caso exista.
    """
    alterado = False
    votos_limpos = []
    campos_proibidos = ["cpf_eleitor", "cpf", "nome_eleitor", "eleitor", "identificacao"]
    
    for v in votos:
        novo_voto = {}
        for k, val in v.items():
            if k.lower() in campos_proibidos:
                alterado = True
            else:
                novo_voto[k] = val
        votos_limpos.append(novo_voto)
    
    if alterado:
        salvar_json(VOTOS_DB_FILE, votos_limpos)
    return votos_limpos

def obter_dados_apuracao():
    votos_raw = carregar_json(VOTOS_DB_FILE, [])
    votos = sanitizar_sigilo_votos(votos_raw)
    eleitores_votados = carregar_json(ELEITORES_DB_FILE, [])

    total_votos = len(votos)
    total_comparecimento = len(eleitores_votados)

    # Contagem de votos por candidato
    contagem = {c["numero"]: 0 for c in CANDIDATOS}
    outros_votos = 0

    for v in votos:
        num = str(v.get("numero_cand", "")).strip()
        if num in contagem:
            contagem[num] += 1
        else:
            outros_votos += 1

    # Monta a lista consolidada de apuração
    candidatos_apuracao = []
    for c in CANDIDATOS:
        qnt = contagem[c["numero"]]
        perc = (qnt / total_votos * 100) if total_votos > 0 else 0.0
        candidatos_apuracao.append({
            "numero": c["numero"],
            "nome": c["nome"],
            "partido": c["partido"],
            "vice": c["vice"],
            "foto_char": c["foto_char"],
            "cor": c["cor"],
            "votos": qnt,
            "percentual": round(perc, 2),
            "percentual_formatado": f"{perc:.2f}%"
        })

    # Ordena por mais votado
    candidatos_apuracao.sort(key=lambda x: (x["votos"], -int(x["numero"])), reverse=True)

    # Atribui ranking e status
    for i, c in enumerate(candidatos_apuracao, 1):
        c["posicao"] = i
        if total_votos > 0:
            if i == 1 and c["votos"] > 0:
                if c["percentual"] > 50.0:
                    c["status_badge"] = "Maioria Absoluta"
                else:
                    c["status_badge"] = "Líder"
            else:
                c["status_badge"] = f"{i}º Lugar"
        else:
            c["status_badge"] = "0 Votos"

    lider = candidatos_apuracao[0] if total_votos > 0 and candidatos_apuracao[0]["votos"] > 0 else None

    # Resumo para auditoria de sigilo
    sigilo_info = {
        "sigiloso": True,
        "campos_voto": ["numero_cand", "nome_cand", "partido_cand"],
        "desvinculado_eleitor": True,
        "mensagem": "Votos armazenados anonimamente sem vínculo com CPF ou eleitor."
    }

    agora = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    return {
        "total_votos": total_votos,
        "total_comparecimento": total_comparecimento,
        "candidatos": candidatos_apuracao,
        "lider": lider,
        "sigilo": sigilo_info,
        "ultima_atualizacao": agora
    }

@app.route("/")
def index():
    dados = obter_dados_apuracao()
    return render_template("apuracao.html", dados=dados)

@app.route("/api/apuracao")
def api_apuracao():
    dados = obter_dados_apuracao()
    return jsonify(dados)

@app.route("/boletim")
def boletim():
    dados = obter_dados_apuracao()
    return render_template("boletim.html", dados=dados)

@app.route("/api/zerar", methods=["POST"])
def zerar():
    """Zera a urna para iniciar uma nova eleição/teste (Gera Zerésima)."""
    salvar_json(VOTOS_DB_FILE, [])
    salvar_json(ELEITORES_DB_FILE, [])
    return jsonify({"success": True, "message": "Urna zerada com sucesso. Zerésima emitida!"})

if __name__ == "__main__":
    print("=" * 60)
    print("  🗳  SISTEMA DE APURAÇÃO ELEITORAL EM FLASK")
    print("  🔒  Sigilo de votos ativado (padrão RDV)")
    print("  🌐  Acesse no navegador: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
