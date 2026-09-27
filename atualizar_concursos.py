#!/usr/bin/env python3
"""
Atualiza concursos.json com notícias de concursos públicos coletadas do
Google Notícias, classificadas por âmbito (nacional/estadual/municipal),
tipo (Abertura/Previsto/Alteração/Resultado/Notícia) e outros metadados.

Roda a partir do GitHub Actions (.github/workflows/atualizar.yml), server-side,
sem precisar de proxies CORS (esses só são necessários quando a busca roda
dentro do navegador, no site).

Uso local (opcional, para testar antes de commitar):
    pip install requests
    python scripts/atualizar_concursos.py
"""
import json
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "concursos.json"
NOTIF_PATH = ROOT / "notificados.json"
SITE_URL = "https://mgworld74.github.io/busca-concursos/"
MAX_NOTIFICADOS = 6000  # teto de itens lembrados, para o arquivo não crescer sem limite

UFS = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
       'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']
UFNAMES = {
    'AC':'Acre','AL':'Alagoas','AP':'Amapá','AM':'Amazonas','BA':'Bahia','CE':'Ceará',
    'DF':'Distrito Federal','ES':'Espírito Santo','GO':'Goiás','MA':'Maranhão',
    'MT':'Mato Grosso','MS':'Mato Grosso do Sul','MG':'Minas Gerais','PA':'Pará',
    'PB':'Paraíba','PR':'Paraná','PE':'Pernambuco','PI':'Piauí','RJ':'Rio de Janeiro',
    'RN':'Rio Grande do Norte','RS':'Rio Grande do Sul','RO':'Rondônia','RR':'Roraima',
    'SC':'Santa Catarina','SP':'São Paulo','SE':'Sergipe','TO':'Tocantins'
}


TTL_DIAS = 30          # itens mais antigos que isso são descartados a cada execução
MAX_ITENS = 1200       # teto de tamanho do concursos.json
JANELA_BUSCA = '3d'    # "when:" do Google Notícias (roda a cada poucas horas, então 3d já cobre com folga)
PAUSA_ENTRE_BUSCAS = 0.4  # segundos, para não bater forte no Google Notícias
TIMEOUT = 12
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; BuscaConcursosBot/1.0; +https://github.com/)'}


def norm(s):
    if s is None:
        return ''
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.lower()


NAME_LIST = sorted(
    [(uf, norm(nome)) for uf, nome in UFNAMES.items() if uf != 'PA'],
    key=lambda e: -len(e[1])
)

RX_ALT = re.compile(r'\b(retifica\w*|altera\w*|prorroga\w*|reabre\w*|reabertura|suspende\w*|suspens\w*|cancela\w*|adia\w*|anula\w*|errata)\b')
RX_RES = re.compile(r'\b(gabarito\w*|resultado\w*|classificad\w*|classificacao|homologa\w*|convoca\w*|convocacao|nomea\w*|aprovad\w*|nota final|notas|chamamento)\b')
RX_PREV = re.compile(r'\b(autoriza\w*|previst\w*|preve\w*|comissao|banca (definida|escolhida|contratada)|solicita\w*|pedido|em breve|planeja\w*|deve abrir|sera aberto|anuncia\w*)\b')
RX_ABR = re.compile(r'\b(abre\w*|abertas?|edital|lanca\w*|publica\w*|inscricoes|vagas?|oferece\w*|seleciona\w*|contrata\w*)\b')


def classify(n):
    if RX_ALT.search(n): return 'Alteração'
    if RX_RES.search(n): return 'Resultado'
    if RX_PREV.search(n): return 'Previsto'
    if RX_ABR.search(n): return 'Abertura'
    return 'Notícia'


def modalidade(n):
    if re.search(r'\bestagio\b', n): return 'Estágio'
    if re.search(r'(processo seletivo|teste seletivo|selecao|selecoes)', n): return 'Processo seletivo'
    return 'Concurso'


def escolaridade(n):
    out = []
    if re.search(r'fundamental', n): out.append('Fundamental')
    if re.search(r'(ensino medio|nivel medio|\bmedio\b)', n): out.append('Médio')
    if re.search(r'(tecnico|nivel tecnico)', n): out.append('Técnico')
    if re.search(r'superior', n): out.append('Superior')
    return out


def money(s):
    vals = []
    for m in re.finditer(r'R\$\s?([\d.]+(?:,\d{1,2})?)', s):
        try:
            vals.append(float(m.group(1).replace('.', '').replace(',', '.')))
        except ValueError:
            pass
    return max(vals) if vals else 0


def extract_uf(t):
    m = re.search(r'\s[-–]\s([A-Z]{2})\b', t)
    if m and m.group(1) in UFS:
        return m.group(1)
    m = re.search(r'[/(]([A-Z]{2})(?=[)\s,.:;]|$)', t) or re.search(r'\b[A-Z]{2,6}-([A-Z]{2})\b', t)
    if m and m.group(1) in UFS:
        return m.group(1)
    # "Cidade-UF" grudado, sem espaços (ex.: "Aparecida-SP", "Sesa-AP")
    m = re.search(r'\b[^\s-]{2,}-([A-Z]{2})\b', t)
    if m and m.group(1) in UFS:
        return m.group(1)
    tnorm = norm(t)
    for uf, name_norm in NAME_LIST:
        if name_norm in tnorm:
            return uf
    # sigla de UF solta no meio do título (ex.: "Concurso SEPLAG MG 2026")
    for m in re.finditer(r'\b([A-Z]{2})\b', t):
        if m.group(1) in UFS:
            return m.group(1)
    return ''


def extract_orgao(t):
    m = re.match(r'^(.+?)\s[-–]\s([A-Z]{2})\b', t)
    if m and m.group(2) in UFS and len(m.group(1)) <= 90:
        return m.group(1).strip()
    m = re.match(
        r'^(.+?)\s+(abre|abrem|reabre|retifica|publica|divulga|divulgam|autoriza|prorroga|altera|'
        r'convoca|lança|anuncia|suspende|cancela|homologa|oferece|seleciona|contrata|tem|terá|'
        r'divulgou|abriu|libera|define|recebe|prevê|solicita)\b', t, re.IGNORECASE)
    if m and len(m.group(1)) <= 80:
        return m.group(1).strip()
    return ''


def extract_cargos(t):
    m = re.search(r'\bpara\s+(.+?)(?:\s+com\s+(?:sal|vaga)|\s+e\s+cadastro|$)', t, re.IGNORECASE)
    return m.group(1).strip()[:110] if m else ''


MUNICIPAL_KW = ['prefeitura', 'camara municipal', 'camara de', 'guarda municipal',
                'autarquia municipal', 'fundacao municipal', 'iprem']
ESTADUAL_KW = ['governo do estado', 'secretaria de estado', 'secretaria estadual',
               'assembleia legislativa', 'policia militar', 'corpo de bombeiros militar',
               'tribunal de justica', 'defensoria publica do estado',
               'ministerio publico do estado', 'detran', 'sefaz']


def guess_scope(titulo, orgao):
    tl, ol = norm(titulo), norm(orgao or '')
    if any(k in tl or k in ol for k in MUNICIPAL_KW):
        m = re.match(r'(?:prefeitura|c[aâ]mara(?:\s+municipal)?)\s+(?:de|municipal\s+de)\s+([^-–]+)',
                      orgao or titulo, re.IGNORECASE)
        municipio = m.group(1).strip() if m else ''
        return 'municipal', municipio
    if any(k in tl or k in ol for k in ESTADUAL_KW):
        return 'estadual', ''
    return 'nacional', ''


def build_item(raw_title, link, pub_date, source_name, source_url):
    title = (raw_title or '').strip()
    source_name = (source_name or '').strip()
    if source_name:
        suf = ' - ' + source_name
        if title.endswith(suf):
            title = title[:-len(suf)].strip()
    else:
        m = re.match(r'^(.*\S)\s[-–]\s([^-–]{2,40})$', title)
        if m and not re.match(r'^[A-Z]{2}\b', m.group(2)) and len(m.group(1)) > 15:
            title, source_name = m.group(1), m.group(2).strip()
    if not title:
        return None
    n = norm(title)
    vm = re.search(r'(\d[\d.]*)\s+vagas?', title, re.IGNORECASE)
    vagas = int(vm.group(1).replace('.', '')) if vm else 0
    orgao = extract_orgao(title)
    uf = extract_uf(title)
    sc, municipio = guess_scope(title, orgao)
    try:
        ts = parsedate_to_datetime(pub_date)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_iso = ts.astimezone(timezone.utc).isoformat()
    except Exception:
        ts_iso = ''
    fonte = source_name or (urlparse(source_url or link or '').hostname or '')
    return {
        'titulo': title, 'orgao': orgao, 'uf': uf, 'scope': sc, 'municipio': municipio,
        'tipo': classify(n), 'modalidade': modalidade(n), 'escolaridade': escolaridade(n),
        'vagas': vagas, 'cr': bool(re.search(r'cadastro[\s-]*(de\s+)?reserva|\bCR\b', title, re.IGNORECASE)),
        'salario': money(title), 'cargos': extract_cargos(title), 'fonte': fonte,
        'link': link or '', 'ts': ts_iso,
    }


def feed_url(q):
    return 'https://news.google.com/rss/search?q=' + quote(q) + '&hl=pt-BR&gl=BR&ceid=BR:pt-419'


def buscar(session, query):
    url = feed_url(query + ' when:' + JANELA_BUSCA)
    try:
        res = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
        root = ET.fromstring(res.content)
        itens = []
        for item in root.findall('./channel/item'):
            titulo = (item.findtext('title') or '')
            link = (item.findtext('link') or '')
            pub_date = (item.findtext('pubDate') or '')
            source_el = item.find('source')
            source_name = source_el.text if source_el is not None else ''
            source_url = source_el.get('url') if source_el is not None else ''
            built = build_item(titulo, link, pub_date, source_name, source_url)
            if built:
                itens.append(built)
        print(f'  ok  "{query}" -> {len(itens)} itens')
        return itens
    except Exception as e:
        print(f'  falhou "{query}": {e}', file=sys.stderr)
        return []


def montar_consultas():
    consultas = [
        'concurso público federal edital',
        'concurso público inscrições abertas',
        'concurso público vagas nível superior',
        'concurso público vagas nível médio',
        'concurso público prefeitura edital',
        'processo seletivo público edital inscrições',
    ]
    for uf, nome in UFNAMES.items():
        consultas.append(f'concurso público {nome} edital inscrições')
    return consultas


def carregar_existentes():
    if not OUT_PATH.exists():
        return []
    try:
        data = json.loads(OUT_PATH.read_text(encoding='utf-8'))
        return data.get('itens', []) if isinstance(data, dict) else []
    except Exception as e:
        print(f'Aviso: não consegui ler {OUT_PATH.name} existente ({e}); começando do zero.', file=sys.stderr)
        return []


# ---------- avisos (notificações push via Firebase Cloud Messaging) ----------

def iniciar_firebase():
    """Retorna um cliente Firestore, ou None se as credenciais não estiverem
    configuradas (ex.: rodando localmente sem a service account) — nesse caso
    a coleta segue normalmente, só sem enviar avisos."""
    cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not cred_path or not Path(cred_path).exists():
        print('Aviso: GOOGLE_APPLICATION_CREDENTIALS não configurado; avisos desativados nesta execução.')
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
        return firestore.client()
    except Exception as e:
        print(f'Aviso: não consegui iniciar o Firebase ({e}); avisos desativados nesta execução.', file=sys.stderr)
        return None


def carregar_notificados():
    if not NOTIF_PATH.exists():
        return set()
    try:
        return set(json.loads(NOTIF_PATH.read_text(encoding='utf-8')))
    except Exception:
        return set()


def salvar_notificados(chaves):
    lista = list(chaves)[-MAX_NOTIFICADOS:]
    NOTIF_PATH.write_text(json.dumps(lista, ensure_ascii=False), encoding='utf-8')


def carregar_alertas(db):
    try:
        docs = db.collection('alertas').where('ativo', '==', True).stream()
        alertas = []
        for d in docs:
            a = d.to_dict() or {}
            a['id'] = d.id
            alertas.append(a)
        return alertas
    except Exception as e:
        print(f'Aviso: não consegui carregar os alertas ({e}); pulando avisos nesta execução.', file=sys.stderr)
        return []


def bate_alerta(alerta, item):
    if alerta.get('ambito') != item.get('scope'):
        return False
    uf = (alerta.get('uf') or '').strip()
    if uf and uf != item.get('uf'):
        return False
    municipio = norm(alerta.get('municipio') or '')
    if municipio and municipio not in norm(item.get('titulo', '') + ' ' + item.get('municipio', '')):
        return False
    termo = norm(alerta.get('termo') or '')
    if termo and termo not in norm(item.get('titulo', '') + ' ' + item.get('orgao', '') + ' ' + item.get('cargos', '')):
        return False
    return True


def enviar_notificacao(item, alerta):
    from firebase_admin import messaging
    msg = messaging.Message(
        token=alerta['token'],
        notification=messaging.Notification(
            title='📢 ' + item['titulo'][:120],
            body=(item.get('orgao') or item.get('fonte') or 'Novo concurso encontrado'),
        ),
        webpush=messaging.WebpushConfig(
            fcm_options=messaging.WebpushFCMOptions(link=item.get('link') or SITE_URL),
        ),
    )
    messaging.send(msg)


def processar_avisos(db, coletados, existentes):
    novos_keys = [k for k in coletados if k not in existentes]
    notificados = carregar_notificados()
    a_notificar = [k for k in novos_keys if k not in notificados]
    if not a_notificar:
        return
    alertas = carregar_alertas(db)
    if not alertas:
        # ainda marca como "vistos" para não reprocessar depois que um alerta for criado
        salvar_notificados(notificados | set(a_notificar))
        return

    from firebase_admin import messaging as fb_messaging
    enviados, falhas_token = 0, set()
    for k in a_notificar:
        item = coletados[k]
        for alerta in alertas:
            if alerta['id'] in falhas_token or not bate_alerta(alerta, item):
                continue
            try:
                enviar_notificacao(item, alerta)
                enviados += 1
            except fb_messaging.UnregisteredError:
                # token não é mais válido (app desinstalado, permissão revogada etc.)
                falhas_token.add(alerta['id'])
                try:
                    db.collection('alertas').doc(alerta['id']).update({'ativo': False})
                except Exception:
                    pass
            except Exception as e:
                print(f'  falha ao enviar aviso ({alerta["id"]}): {e}', file=sys.stderr)

    salvar_notificados(notificados | set(a_notificar))
    print(f'Avisos: {enviados} notificações enviadas para {len(alertas)} alerta(s) ativo(s).')


def main():
    session = requests.Session()
    consultas = montar_consultas()
    print(f'Rodando {len(consultas)} consultas no Google Notícias...')

    coletados = {}
    for q in consultas:
        for it in buscar(session, q):
            chave = norm(it['titulo'])
            if chave:
                coletados[chave] = it
        time.sleep(PAUSA_ENTRE_BUSCAS)

    existentes = {norm(it.get('titulo', '')): it for it in carregar_existentes() if it.get('titulo')}

    db = iniciar_firebase()
    if db is not None:
        processar_avisos(db, coletados, existentes)

    # novo resultado tem prioridade; itens antigos não recapturados nesta rodada são mantidos até expirar
    combinados = {**existentes, **coletados}

    limite = datetime.now(timezone.utc) - timedelta(days=TTL_DIAS)
    finais = []
    for it in combinados.values():
        ts = it.get('ts') or ''
        if ts:
            try:
                if datetime.fromisoformat(ts.replace('Z', '+00:00')) < limite:
                    continue
            except ValueError:
                pass
        finais.append(it)

    finais.sort(key=lambda it: it.get('ts') or '', reverse=True)
    finais = finais[:MAX_ITENS]

    saida = {
        'atualizadoEm': datetime.now(timezone.utc).isoformat(),
        'fonte': 'Google Notícias (agregação automática via GitHub Actions)',
        'janelaDias': TTL_DIAS,
        'itens': finais,
    }
    OUT_PATH.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Concluído: {len(finais)} itens gravados em {OUT_PATH.name} '
          f'({len(coletados)} novos/atualizados nesta rodada).')


if __name__ == '__main__':
    main()
