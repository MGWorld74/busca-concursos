#!/usr/bin/env python3
"""Coleta notícias de concursos no Google Notícias (RSS) e grava concursos.json.
O site (index.html) faz a classificação por âmbito; o robô só coleta e guarda 30 dias."""
import json, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

DIAS = 30
SAIDA = Path(__file__).resolve().parent.parent / "concursos.json"
UFS = {"AC":"Acre","AL":"Alagoas","AP":"Amapá","AM":"Amazonas","BA":"Bahia","CE":"Ceará","DF":"Distrito Federal","ES":"Espírito Santo","GO":"Goiás","MA":"Maranhão","MT":"Mato Grosso","MS":"Mato Grosso do Sul","MG":"Minas Gerais","PA":"Pará","PB":"Paraíba","PR":"Paraná","PE":"Pernambuco","PI":"Piauí","RJ":"Rio de Janeiro","RN":"Rio Grande do Norte","RS":"Rio Grande do Sul","RO":"Rondônia","RR":"Roraima","SC":"Santa Catarina","SP":"São Paulo","SE":"Sergipe","TO":"Tocantins"}

def consultas():
    q = [("concurso público federal edital", ""), ("concurso público nacional inscrições abertas", ""),
         ("concurso público governo do estado edital", "")]
    for uf, nome in UFS.items():
        q.append((f"concurso público governo do estado {nome}", uf))
        q.append((f"concurso público {nome} edital inscrições", uf))
        q.append((f"concurso público prefeituras {nome} edital", uf))
    return [(f"{t} when:{DIAS}d", uf) for t, uf in q]

def buscar(q):
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (RadarConcursos)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    for it in root.iter("item"):
        fonte = (it.findtext("source") or "").strip()
        titulo = (it.findtext("title") or "").strip()
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        except Exception:
            continue
        yield {"titulo": titulo, "fonte": fonte, "link": (it.findtext("link") or "").strip(),
               "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ")}

def main():
    corte = datetime.now(timezone.utc) - timedelta(days=DIAS)
    itens = {}
    if SAIDA.exists():
        try:
            for o in json.loads(SAIDA.read_text(encoding="utf-8")).get("itens", []):
                itens[o["titulo"]] = o
        except Exception:
            pass
    ok = 0
    for q, uf in consultas():
        try:
            for o in buscar(q):
                o["uf"] = uf
                antigo = itens.get(o["titulo"])
                if antigo and antigo.get("uf") and not uf:
                    o["uf"] = antigo["uf"]
                itens[o["titulo"]] = o
            ok += 1
        except Exception as e:
            print("falha:", q, e)
        time.sleep(1.2)
    if ok == 0:
        raise SystemExit("Nenhuma consulta funcionou; mantendo arquivo anterior.")
    vivos = [o for o in itens.values() if datetime.strptime(o["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) >= corte]
    vivos.sort(key=lambda o: o["ts"], reverse=True)
    SAIDA.write_text(json.dumps({"atualizado": datetime.now(timezone.utc).isoformat(), "itens": vivos},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(vivos)} itens gravados ({ok} consultas ok)")

if __name__ == "__main__":
    main()
