"""
=============================================================================
  PROJETO: Urna Eletrônica Universitária (Trabalho de Faculdade)
  LINGUAGEM: Python 3 com Framework Flask
  DESCRIÇÃO: Sistema web simulando uma urna eletrônica para eleição municipal,
             com tela de votação, apuração em tempo real, boletim de urna e
             painel administrativo de candidatos.
=============================================================================
"""

import os
import json
import re
from datetime import datetime
from urllib.parse import parse_qs
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, send_from_directory
)
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.utils import secure_filename

# ─── Configurações Iniciais ──────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Pasta /api
ROOT_DIR = os.path.dirname(BASE_DIR)                   # Raiz do projeto

app = Flask(__name__)
app.secret_key = "urna_faculdade_chave_secreta_2026"

# ─── Middleware para Vercel ──────────────────────────────────────────────────
# Na Vercel, as requisições chegam reescritas com o parâmetro __path.
# Esse pequeno middleware restaura o caminho correto da URL.
class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        if "__path" in qs and qs["__path"]:
            environ["PATH_INFO"] = "/" + qs["__path"][0].lstrip("/")
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

# ─── Carregamento de Templates ───────────────────────────────────────────────
# Garante que o Flask encontre os arquivos HTML tanto localmente quanto na Vercel
template_dirs = [
    os.path.join(ROOT_DIR, "templates"),
    os.path.join(BASE_DIR, "templates"),
    os.path.join(BASE_DIR, "api", "templates"),
]
valid_dirs = [d for d in template_dirs if os.path.exists(d)]
if valid_dirs:
    app.jinja_loader = ChoiceLoader([FileSystemLoader(d) for d in valid_dirs])

# ─── Arquivos de Dados (Persistência em JSON) ─────────────────────────────────

TMP_DIR = "/tmp" if os.path.exists("/tmp") else BASE_DIR

def obter_caminho_arquivo(nome):
    """Retorna o caminho onde o arquivo JSON deve ser lido ou salvo."""
    candidatos = [
        os.path.join(BASE_DIR, nome),
        os.path.join(ROOT_DIR, nome),
        nome
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return os.path.join(BASE_DIR, nome)

ARQUIVO_ELEITORES  = obter_caminho_arquivo("eleitores_votados.json")
ARQUIVO_VOTOS      = obter_caminho_arquivo("votos.json")
ARQUIVO_CANDIDATOS = obter_caminho_arquivo("candidatos.json")

# Pasta para salvar fotos dos candidatos enviados pelo admin
PASTA_FOTOS = os.path.join(BASE_DIR, "static", "fotos")
os.makedirs(PASTA_FOTOS, exist_ok=True)

# Candidatos padrão caso o arquivo candidatos.json ainda não exista
CANDIDATOS_PADRAO = [
    {"numero": "10", "nome": "Ana Silva",    "partido": "PARTIDO A", "vice": "Carlos Lima",   "foto_char": "👩", "cor": "#2563eb", "foto_path": ""},
    {"numero": "20", "nome": "Bruno Santos", "partido": "PARTIDO B", "vice": "Diana Costa",   "foto_char": "👨", "cor": "#16a34a", "foto_path": ""},
    {"numero": "30", "nome": "Clara Melo",   "partido": "PARTIDO C", "vice": "Eduardo Neto",  "foto_char": "👩", "cor": "#9333ea", "foto_path": ""},
    {"numero": "40", "nome": "Daniel Rocha", "partido": "PARTIDO D", "vice": "Fernanda Dias", "foto_char": "👨", "cor": "#ea580c", "foto_path": ""},
    {"numero": "50", "nome": "Elena Braga",  "partido": "PARTIDO E", "vice": "Gabriel Souza", "foto_char": "👩", "cor": "#db2777", "foto_path": ""},
]

# Cache em memória simples para evitar leitura repetida e contornar read-only na Vercel
_MEMORIA = {}

def carregar_json(caminho, padrao):
    """Lê dados de um arquivo JSON de forma segura."""
    if caminho in _MEMORIA:
        return _MEMORIA[caminho]

    nome = os.path.basename(caminho)
    tmp_path = os.path.join(TMP_DIR, nome)

    if os.path.exists(tmp_path):
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                _MEMORIA[caminho] = dados
                return dados
        except Exception:
            pass

    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
                _MEMORIA[caminho] = dados
                return dados
        except Exception:
            return padrao

    _MEMORIA[caminho] = padrao
    return padrao

def salvar_json(caminho, dados):
    """Salva dados em um arquivo JSON e atualiza o cache."""
    _MEMORIA[caminho] = dados
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        nome = os.path.basename(caminho)
        tmp_path = os.path.join(TMP_DIR, nome)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ─── Validação de CPF ────────────────────────────────────────────────────────

def validar_cpf(cpf):
    """
    Valida o CPF usando o algoritmo oficial dos dois dígitos verificadores.
    Nível iniciante: fácil de entender e explicar na apresentação do trabalho.
    """
    cpf = re.sub(r"\D", "", str(cpf))  # Deixa apenas números

    # O CPF deve ter exatamente 11 dígitos e não pode ter todos os dígitos repetidos
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    # 1º Dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    d1 = 0 if resto >= 10 else resto
    if d1 != int(cpf[9]):
        return False

    # 2º Dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    d2 = 0 if resto >= 10 else resto
    if d2 != int(cpf[10]):
        return False

    return True

# ─── Gerenciamento de Candidatos ─────────────────────────────────────────────

def obter_candidatos():
    """Retorna a lista de candidatos cadastrados."""
    _MEMORIA.pop(ARQUIVO_CANDIDATOS, None)
    cands = carregar_json(ARQUIVO_CANDIDATOS, None)
    if cands is None or len(cands) == 0:
        salvar_json(ARQUIVO_CANDIDATOS, CANDIDATOS_PADRAO)
        return list(CANDIDATOS_PADRAO)
    return cands

def salvar_candidatos(lista):
    """Salva a lista atualizada de candidatos."""
    salvar_json(ARQUIVO_CANDIDATOS, lista)
    _MEMORIA.pop(ARQUIVO_CANDIDATOS, None)

# ─── Apuração dos Votos ──────────────────────────────────────────────────────

def calcular_apuracao():
    """
    Calcula o resultado da eleição:
    - Lê todos os votos anônimos
    - Conta os votos de cada candidato
    - Calcula as porcentagens
    - Identifica o vencedor/líder
    """
    candidatos = obter_candidatos()
    votos = carregar_json(ARQUIVO_VOTOS, [])
    eleitores = carregar_json(ARQUIVO_ELEITORES, [])

    total_votos = len(votos)
    total_eleitores = len(eleitores)

    # Inicializa contagem
    contagem = {c["numero"]: 0 for c in candidatos}
    votos_brancos = 0
    votos_nulos = 0

    for v in votos:
        num = str(v.get("numero_cand", "")).strip()
        nome = str(v.get("nome_cand", "")).upper()
        if num == "00" or "BRANCO" in nome:
            votos_brancos += 1
        elif num in contagem:
            contagem[num] += 1
        else:
            votos_nulos += 1

    # Formata os dados de cada candidato com seus votos e porcentagens
    apuracao_candidatos = []
    for c in candidatos:
        qnt = contagem.get(c["numero"], 0)
        perc = (qnt / total_votos * 100) if total_votos > 0 else 0.0
        apuracao_candidatos.append({
            "numero": c["numero"],
            "nome": c["nome"],
            "partido": c["partido"],
            "vice": c.get("vice", ""),
            "foto_char": c.get("foto_char", "🗳️"),
            "foto_path": c.get("foto_path", ""),
            "cor": c.get("cor", "#2563eb"),
            "votos": qnt,
            "percentual": round(perc, 1),
            "percentual_formatado": f"{perc:.1f}%"
        })

    # Ordena pelo candidato mais votado
    apuracao_candidatos.sort(key=lambda x: x["votos"], reverse=True)

    # Define o ranking (1º, 2º, ...)
    for i, c in enumerate(apuracao_candidatos, 1):
        c["posicao"] = i

    lider = apuracao_candidatos[0] if (total_votos > 0 and apuracao_candidatos[0]["votos"] > 0) else None
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    return {
        "total_votos": total_votos,
        "total_comparecimento": total_eleitores,
        "votos_brancos": votos_brancos,
        "votos_nulos": votos_nulos,
        "candidatos": apuracao_candidatos,
        "lider": lider,
        "ultima_atualizacao": agora
    }

# ─── Rotas Principais (Páginas Web) ──────────────────────────────────────────

@app.route("/")
@app.route("/apuracao")
def rota_apuracao():
    """Página principal: Apuração dos votos em tempo real."""
    dados = calcular_apuracao()
    return render_template("index.html", dados=dados)

@app.route("/votar")
def rota_votar():
    """Página da Urna Eletrônica para votar."""
    return render_template("votar.html")

@app.route("/boletim")
def rota_boletim():
    """Página do Boletim de Urna (imprimível)."""
    dados = calcular_apuracao()
    return render_template("boletim.html", dados=dados)

# ─── Rotas da API (Chamadas AJAX / JSON) ──────────────────────────────────────

@app.route("/api/candidatos")
def rota_api_candidatos():
    """Retorna os candidatos em JSON para a urna carregar."""
    return jsonify(obter_candidatos())

@app.route("/api/apuracao")
def rota_api_apuracao():
    """Retorna os dados da apuração em JSON para atualização automática."""
    return jsonify(calcular_apuracao())

@app.route("/api/votar", methods=["POST"])
def rota_api_votar():
    """
    Recebe e processa o voto:
    1. EXIGE o CPF do eleitor (impede votar sem CPF)
    2. Valida o formato e os dígitos do CPF
    3. Verifica se o CPF já votou (impede voto duplo)
    4. Salva o voto anonimamente (respeitando o sigilo do voto)
    """
    try:
        dados = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "error": "Requisição inválida."}), 400

    if not dados:
        return jsonify({"success": False, "error": "Nenhum dado recebido."}), 400

    # 1. VALIDAÇÃO DO CPF (OBRIGATÓRIO)
    cpf_bruto = str(dados.get("cpf_eleitor", "")).strip()
    cpf_limpo = re.sub(r"\D", "", cpf_bruto)

    if not cpf_limpo:
        return jsonify({
            "success": False,
            "error": "O CPF é obrigatório para votar! Por favor, digite seu CPF."
        }), 400

    if not validar_cpf(cpf_limpo):
        return jsonify({
            "success": False,
            "error": "CPF inválido! Verifique os números digitados."
        }), 400

    # 2. VERIFICAÇÃO DE VOTO DUPLO
    eleitores = carregar_json(ARQUIVO_ELEITORES, [])
    if cpf_limpo in eleitores:
        return jsonify({
            "success": False,
            "error": "Este CPF já votou nesta eleição! Voto duplicado não permitido."
        }), 400

    # 3. EXTRAÇÃO DO VOTO
    voto = dados.get("voto", {})
    numero = str(voto.get("numero_cand", "")).strip()
    nome   = str(voto.get("nome_cand", "")).strip()
    partido= str(voto.get("partido_cand", "")).strip()

    if not numero:
        return jsonify({"success": False, "error": "Número do candidato não informado."}), 400

    # 4. REGISTRO DO ELEITOR (Para garantir que não vote de novo)
    eleitores.append(cpf_limpo)
    salvar_json(ARQUIVO_ELEITORES, eleitores)

    # 5. REGISTRO DO VOTO ANONIMIZADO (Sem vínculo com CPF para sigilo eleitoral)
    votos = carregar_json(ARQUIVO_VOTOS, [])
    votos.append({
        "numero_cand": numero,
        "nome_cand": nome,
        "partido_cand": partido
    })
    salvar_json(ARQUIVO_VOTOS, votos)

    return jsonify({
        "success": True,
        "message": "Voto computado com sucesso!",
        "total_votos": len(votos)
    })

# ─── Painel Administrativo ───────────────────────────────────────────────────

def admin_logado():
    return session.get("admin_logado") is True

@app.route("/api/zerar", methods=["POST"])
def rota_api_zerar():
    """Zera a votação (apenas o administrador logado pode executar)."""
    if not admin_logado():
        return jsonify({"success": False, "error": "Acesso restrito ao administrador."}), 403
    salvar_json(ARQUIVO_VOTOS, [])
    salvar_json(ARQUIVO_ELEITORES, [])
    return jsonify({"success": True, "message": "Urna zerada com sucesso!"})

@app.route("/admin/login", methods=["GET", "POST"])
def rota_admin_login():
    """Tela de login do administrador (admin / 1234)."""
    erro = None
    if request.method == "POST":
        usuario = request.form.get("username", "").strip()
        senha   = request.form.get("senha", "").strip()
        if usuario == "admin" and senha == "1234":
            session["admin_logado"] = True
            return redirect(url_for("rota_admin"))
        else:
            erro = "Usuário ou senha incorretos."
    return render_template("admin_login.html", erro=erro)

@app.route("/admin/logout")
def rota_admin_logout():
    session.pop("admin_logado", None)
    return redirect(url_for("rota_admin_login"))

@app.route("/admin")
def rota_admin():
    """Painel com a lista de candidatos e botões de gerenciamento."""
    if not admin_logado():
        return redirect(url_for("rota_admin_login"))
    candidatos = obter_candidatos()
    msg = request.args.get("msg", "")
    return render_template("admin.html", candidatos=candidatos, msg=msg)

@app.route("/admin/candidatos/adicionar", methods=["GET", "POST"])
def rota_admin_adicionar():
    """Cadastra um novo candidato."""
    if not admin_logado():
        return redirect(url_for("rota_admin_login"))
    erro = None
    if request.method == "POST":
        numero = request.form.get("numero", "").strip()
        nome = request.form.get("nome", "").strip()
        partido = request.form.get("partido", "").strip()
        vice = request.form.get("vice", "").strip()
        foto_char = request.form.get("foto_char", "🗳️").strip()
        cor = request.form.get("cor", "#2563eb").strip()
        foto_path = ""

        candidatos = obter_candidatos()
        if not numero or not nome:
            erro = "Número e nome do candidato são obrigatórios."
        elif any(c["numero"] == numero for c in candidatos):
            erro = f"Já existe um candidato com o número {numero}."
        else:
            foto = request.files.get("foto")
            if foto and foto.filename:
                fname = secure_filename(f"{numero}_{foto.filename}")
                foto.save(os.path.join(PASTA_FOTOS, fname))
                foto_path = f"/static/fotos/{fname}"

            candidatos.append({
                "numero": numero,
                "nome": nome,
                "partido": partido,
                "vice": vice,
                "foto_char": foto_char,
                "cor": cor,
                "foto_path": foto_path
            })
            salvar_candidatos(candidatos)
            return redirect(url_for("rota_admin", msg=f"Candidato {nome} cadastrado com sucesso!"))

    return render_template("admin_form.html", modo="add", candidato=None, erro=erro)

@app.route("/admin/candidatos/editar/<numero>", methods=["GET", "POST"])
def rota_admin_editar(numero):
    """Edita um candidato existente."""
    if not admin_logado():
        return redirect(url_for("rota_admin_login"))

    candidatos = obter_candidatos()
    candidato = next((c for c in candidatos if c["numero"] == numero), None)
    if not candidato:
        return redirect(url_for("rota_admin", msg="Candidato não encontrado."))

    erro = None
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        partido = request.form.get("partido", "").strip()
        vice = request.form.get("vice", "").strip()
        foto_char = request.form.get("foto_char", candidato.get("foto_char", "🗳️")).strip()
        cor = request.form.get("cor", candidato.get("cor", "#2563eb")).strip()
        foto_path = candidato.get("foto_path", "")

        if not nome:
            erro = "O nome é obrigatório."
        else:
            foto = request.files.get("foto")
            if foto and foto.filename:
                fname = secure_filename(f"{numero}_{foto.filename}")
                foto.save(os.path.join(PASTA_FOTOS, fname))
                foto_path = f"/static/fotos/{fname}"

            for c in candidatos:
                if c["numero"] == numero:
                    c["nome"] = nome
                    c["partido"] = partido
                    c["vice"] = vice
                    c["foto_char"] = foto_char
                    c["cor"] = cor
                    c["foto_path"] = foto_path
                    break

            salvar_candidatos(candidatos)
            return redirect(url_for("rota_admin", msg=f"Candidato {nome} atualizado com sucesso!"))

    return render_template("admin_form.html", modo="edit", candidato=candidato, erro=erro)

@app.route("/admin/candidatos/excluir/<numero>", methods=["POST"])
def rota_admin_excluir(numero):
    """Remove um candidato."""
    if not admin_logado():
        return redirect(url_for("rota_admin_login"))

    candidatos = obter_candidatos()
    candidatos = [c for c in candidatos if c["numero"] != numero]
    salvar_candidatos(candidatos)
    return redirect(url_for("rota_admin", msg=f"Candidato número {numero} removido com sucesso."))

# ─── Arquivos Estáticos ───────────────────────────────────────────────────────

@app.route("/static/<path:filename>")
def rota_static(filename):
    static_dir = os.path.join(BASE_DIR, "static")
    return send_from_directory(static_dir, filename)

# ─── Fallback para Vercel ─────────────────────────────────────────────────────

@app.route("/<path:subpath>", methods=["GET", "POST"])
def rota_fallback(subpath):
    limpo = subpath.strip("/").replace("api/index/", "")
    if limpo == "votar":
        return rota_votar()
    elif limpo in ("", "index", "apuracao"):
        return rota_apuracao()
    elif limpo == "boletim":
        return rota_boletim()
    elif limpo == "admin":
        return rota_admin()
    elif limpo == "admin/login":
        return rota_admin_login()
    elif limpo == "admin/logout":
        return rota_admin_logout()
    elif limpo == "api/apuracao":
        return rota_api_apuracao()
    elif limpo == "api/candidatos":
        return rota_api_candidatos()
    elif limpo == "api/votar" and request.method == "POST":
        return rota_api_votar()
    elif limpo == "api/zerar" and request.method == "POST":
        return rota_api_zerar()
    return rota_apuracao()

# ─── Execução Local ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  🗳️  URNA ELETRÔNICA UNIVERSITÁRIA - FLASK")
    print("  🌐  Acesse no navegador: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
