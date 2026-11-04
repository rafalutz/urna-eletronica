import os
import json
import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for
from jinja2 import ChoiceLoader, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

app = Flask(__name__)

from urllib.parse import parse_qs

class VercelPathMiddleware:
    """Restaura o caminho original da requisicao no WSGI a partir do parametro __path ou x-matched-path da Vercel."""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        if "__path" in qs and qs["__path"]:
            sub = "/" + qs["__path"][0].lstrip("/")
            environ["PATH_INFO"] = sub
        else:
            matched_path = environ.get("HTTP_X_MATCHED_PATH") or environ.get("HTTP_X_FORWARDED_URI")
            if matched_path:
                clean_path = matched_path.split("?")[0]
                if clean_path not in ("/api/index", "/api/index.py"):
                    environ["PATH_INFO"] = clean_path
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

# Configura busca de templates em todos os locais possiveis (api/templates e raiz/templates)
template_dirs = [
    os.path.join(BASE_DIR, "templates"),
    os.path.join(ROOT_DIR, "templates"),
    os.path.join(BASE_DIR, "api", "templates"),
]
valid_dirs = [d for d in template_dirs if os.path.exists(d)]
if valid_dirs:
    app.jinja_loader = ChoiceLoader([FileSystemLoader(d) for d in valid_dirs])

def resolver_arquivo(nome):
    candidatos = [
        os.path.join(BASE_DIR, nome),
        os.path.join(ROOT_DIR, nome),
        nome
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return os.path.join(BASE_DIR, nome)

ELEITORES_DB_FILE = resolver_arquivo("eleitores_votados.json")
VOTOS_DB_FILE = resolver_arquivo("votos.json")

CANDIDATOS = [
    {"numero": "10", "nome": "Ana Silva",    "partido": "PARTIDO A", "vice": "Carlos Lima",   "foto_char": "👩", "cor": "#3b82f6"},
    {"numero": "20", "nome": "Bruno Santos", "partido": "PARTIDO B", "vice": "Diana Costa",   "foto_char": "👨", "cor": "#10b981"},
    {"numero": "30", "nome": "Clara Melo",   "partido": "PARTIDO C", "vice": "Eduardo Neto",  "foto_char": "👩", "cor": "#8b5cf6"},
    {"numero": "40", "nome": "Daniel Rocha", "partido": "PARTIDO D", "vice": "Fernanda Dias", "foto_char": "👨", "cor": "#f59e0b"},
    {"numero": "50", "nome": "Elena Braga",  "partido": "PARTIDO E", "vice": "Gabriel Souza", "foto_char": "👩", "cor": "#ec4899"},
]

TMP_DIR = "/tmp" if os.path.exists("/tmp") else BASE_DIR

_MEMORIA_CACHE = {}

def carregar_json(arquivo, padrao):
    if arquivo in _MEMORIA_CACHE:
        return _MEMORIA_CACHE[arquivo]
    nome = os.path.basename(arquivo)
    tmp_path = os.path.join(TMP_DIR, nome)
    if os.path.exists(tmp_path):
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                _MEMORIA_CACHE[arquivo] = dados
                return dados
        except Exception:
            pass
    if os.path.exists(arquivo):
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                _MEMORIA_CACHE[arquivo] = dados
                return dados
        except Exception:
            return padrao
    _MEMORIA_CACHE[arquivo] = padrao
    return padrao

def salvar_json(arquivo, dados):
    _MEMORIA_CACHE[arquivo] = dados
    try:
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except (OSError, IOError, PermissionError):
        pass
    try:
        nome = os.path.basename(arquivo)
        tmp_path = os.path.join(TMP_DIR, nome)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def sanitizar_sigilo_votos(votos):
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

    contagem = {c["numero"]: 0 for c in CANDIDATOS}
    outros_votos = 0
    for v in votos:
        num = str(v.get("numero_cand", "")).strip()
        if num in contagem:
            contagem[num] += 1
        else:
            outros_votos += 1

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

    candidatos_apuracao.sort(key=lambda x: (x["votos"], -int(x["numero"])), reverse=True)

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

def render_tela_apuracao(dados):
    try:
        return render_template("index.html", dados=dados)
    except Exception:
        return render_template("apuracao.html", dados=dados)

@app.route("/")
@app.route("/index")
@app.route("/apuracao")
@app.route("/api/index")
@app.route("/api/index/")
def index():
    p = request.args.get("__path", "").strip("/").split("?")[0]
    if p == "boletim":
        return boletim()
    elif p == "api/apuracao":
        return api_apuracao()
    elif p == "api/votar" and request.method == "POST":
        return api_votar()
    elif p == "api/zerar" and request.method == "POST":
        return zerar()

    dados = obter_dados_apuracao()
    return render_tela_apuracao(dados)

@app.route("/api/apuracao")
@app.route("/api/index/api/apuracao")
def api_apuracao():
    dados = obter_dados_apuracao()
    return jsonify(dados)

@app.route("/boletim")
@app.route("/api/index/boletim")
def boletim():
    dados = obter_dados_apuracao()
    return render_template("boletim.html", dados=dados)

@app.route("/api/zerar", methods=["POST"])
@app.route("/api/index/api/zerar", methods=["POST"])
def zerar():
    salvar_json(VOTOS_DB_FILE, [])
    salvar_json(ELEITORES_DB_FILE, [])
    return jsonify({"success": True, "message": "Urna zerada com sucesso. Zerésima emitida!"})

@app.route("/api/votar", methods=["POST"])
@app.route("/api/index/api/votar", methods=["POST"])
def api_votar():
    try:
        dados = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "error": "JSON inválido"}), 400

    if not dados or "voto" not in dados:
        return jsonify({"success": False, "error": "Dados de voto ausentes"}), 400

    voto_recebido = dados.get("voto", {})
    cpf_eleitor = str(dados.get("cpf_eleitor", "")).strip()

    eleitores = carregar_json(ELEITORES_DB_FILE, [])
    votos = carregar_json(VOTOS_DB_FILE, [])

    if cpf_eleitor:
        if cpf_eleitor in eleitores:
            return jsonify({"success": False, "error": "Eleitor já votou nesta eleição."}), 400
        eleitores.append(cpf_eleitor)

    campos_permitidos = ["numero_cand", "nome_cand", "partido_cand"]
    voto_limpo = {k: voto_recebido[k] for k in campos_permitidos if k in voto_recebido}

    import random
    votos.append(voto_limpo)
    random.shuffle(votos)

    salvar_json(VOTOS_DB_FILE, votos)
    salvar_json(ELEITORES_DB_FILE, eleitores)

    return jsonify({
        "success": True,
        "message": "Voto computado com sucesso na nuvem!",
        "total_votos": len(votos)
    })

@app.route("/<path:subpath>", methods=["GET", "POST"])
def catch_all(subpath):
    clean = subpath.strip("/").replace("api/index/", "")
    if clean == "boletim":
        return boletim()
    elif clean == "api/apuracao":
        return api_apuracao()
    elif clean == "api/votar" and request.method == "POST":
        return api_votar()
    elif clean == "api/zerar" and request.method == "POST":
        return zerar()
    dados = obter_dados_apuracao()
    return render_tela_apuracao(dados)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
