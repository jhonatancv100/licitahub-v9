#!/usr/bin/env python3
from __future__ import annotations
import os, json, time, re, secrets, hashlib, hmac, threading, urllib.request, urllib.parse, unicodedata
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parent
HOST=os.getenv("HOST","0.0.0.0"); PORT=int(os.getenv("PORT","8765"))
DB_URL=os.getenv("DATABASE_URL","").strip(); SECURE=os.getenv("SESSION_SECURE","1")!="0"
VERSION="10.1"
OECE="https://contratacionesabiertas.oece.gob.pe/api/v1/releasesAfter?format=json&order=desc"
SEACE_PUBLIC="https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
MINOR_PUBLIC="https://prod6.seace.gob.pe/buscador-publico/contrataciones"
MINOR_BASE="https://prod6.seace.gob.pe/v1/s8uit-services"
UA="PortalSeguimiento/10.1"; SYNC_LOCK=threading.Lock()

def db(): return psycopg.connect(DB_URL,row_factory=dict_row)
def norm(v):
    s=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"\s+"," ",s).strip()
def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,name TEXT NOT NULL DEFAULT '',created_at BIGINT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf TEXT NOT NULL,expires_at BIGINT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_state(user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,key TEXT NOT NULL,value_json TEXT NOT NULL,updated_at BIGINT NOT NULL,PRIMARY KEY(user_id,key))""")
        c.execute("""CREATE TABLE IF NOT EXISTS opportunities(source TEXT NOT NULL,source_id TEXT NOT NULL,code TEXT,entity TEXT,description TEXT,contract_type TEXT,department TEXT,province TEXT,district TEXT,amount DOUBLE PRECISION,currency TEXT,published_at TEXT,deadline_at TEXT,status TEXT,source_url TEXT,search_text TEXT NOT NULL,raw_json TEXT NOT NULL,first_seen BIGINT NOT NULL,last_seen BIGINT NOT NULL,PRIMARY KEY(source,source_id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_opp_pub ON opportunities(published_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_opp_deadline ON opportunities(deadline_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_opp_source ON opportunities(source)")
        c.execute("DELETE FROM sessions WHERE expires_at < %s",(int(time.time()),)); c.commit()
def pw_hash(p):
    salt=secrets.token_bytes(16); rounds=260000
    dig=hashlib.pbkdf2_hmac("sha256",p.encode(),salt,rounds)
    return "pbkdf2_sha256$"+str(rounds)+"$"+salt.hex()+"$"+dig.hex()
def pw_ok(p,s):
    try:
        _,r,sa,d=s.split("$"); got=hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(sa),int(r)).hex()
        return hmac.compare_digest(got,d)
    except: return False
def sha(v): return hashlib.sha256(v.encode()).hexdigest()
def get_json(url,timeout=25):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,*/*"})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read(8_000_000).decode("utf-8","ignore"))
def get_text(url,timeout=20,max_bytes=4_000_000):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,*/*"})
    with urllib.request.urlopen(req,timeout=timeout) as r: return r.read(max_bytes).decode("utf-8","ignore")
def first(*vals):
    for v in vals:
        if v not in (None,"",[],{}): return v
    return ""
def date10(v):
    m=re.search(r"(20\d\d-\d\d-\d\d)",str(v or "")); return m.group(1) if m else ""
def classify(t,title):
    x=norm(" ".join([str(t.get("mainProcurementCategory") or ""),str(t.get("procurementMethodDetails") or ""),str(title or "")]))
    if "consultoria" in x: return "Consultoría"
    if "goods" in x or "bien" in x: return "Bienes"
    if "works" in x or "obra" in x: return "Obras"
    return "Servicios"
def buyer_location(rel,buyer):
    bname=str(buyer.get("name") or ""); bid=str(buyer.get("id") or "")
    for p in rel.get("parties") or []:
        if not isinstance(p,dict): continue
        if (bid and str(p.get("id") or "")==bid) or (bname and str(p.get("name") or "")==bname):
            a=p.get("address") or {}
            return str(a.get("region") or ""),str(a.get("locality") or ""),str(a.get("streetAddress") or "")
    return "","",""
def normalize_release(rel):
    t=rel.get("tender") if isinstance(rel.get("tender"),dict) else {}; buyer=rel.get("buyer") if isinstance(rel.get("buyer"),dict) else {}
    val=t.get("value") if isinstance(t.get("value"),dict) else {}; per=t.get("tenderPeriod") if isinstance(t.get("tenderPeriod"),dict) else {}
    title=first(t.get("title"),t.get("description"),rel.get("ocid"),"Proceso sin descripción")
    sid=str(first(t.get("id"),rel.get("id"),rel.get("ocid"),secrets.token_hex(8))); code=str(first(t.get("id"),rel.get("ocid"),rel.get("id")))
    dept,prov,dist=buyer_location(rel,buyer); docs=t.get("documents") or []; url=""
    for d in docs:
        if isinstance(d,dict) and str(d.get("url") or "").startswith("http"): url=str(d["url"]); break
    if not url: url=SEACE_PUBLIC
    raw_status=norm(t.get("status")); status="Cerrado" if any(x in raw_status for x in ["complete","closed","cancel","unsuccess"]) else "Abierto"
    entity=str(buyer.get("name") or "Entidad no informada"); desc=str(title); ctype=classify(t,title)
    pub=date10(first(rel.get("date"),t.get("datePublished"))); deadline=date10(per.get("endDate"))
    amount=val.get("amount") if isinstance(val.get("amount"),(int,float)) else None; currency=str(val.get("currency") or "PEN")
    st=norm(" ".join([code,entity,desc,ctype,dept,prov,dist]))
    return {"source":"SEACE","source_id":sid,"code":code,"entity":entity,"description":desc,"contract_type":ctype,"department":dept,"province":prov,"district":dist,"amount":amount,"currency":currency,"published_at":pub,"deadline_at":deadline,"status":status,"source_url":url,"search_text":st,"raw_json":json.dumps(rel,ensure_ascii=False)}
def extract_releases(data):
    if not isinstance(data,dict): return []
    if isinstance(data.get("releases"),list): return [x for x in data["releases"] if isinstance(x,dict)]
    for k in ("data","results","items","content"):
        v=data.get(k)
        if isinstance(v,list) and any(isinstance(x,dict) and ("tender" in x or "ocid" in x) for x in v): return [x for x in v if isinstance(x,dict)]
    return []
def next_url(data,current):
    links=data.get("links") if isinstance(data,dict) else {}; n=links.get("next") if isinstance(links,dict) else None
    return urllib.parse.urljoin(current,n) if isinstance(n,str) and n else None
def upsert(rows):
    if not rows:return
    now=int(time.time())
    with db() as c:
        for r in rows:
            c.execute("""INSERT INTO opportunities(source,source_id,code,entity,description,contract_type,department,province,district,amount,currency,published_at,deadline_at,status,source_url,search_text,raw_json,first_seen,last_seen)
            VALUES(%(source)s,%(source_id)s,%(code)s,%(entity)s,%(description)s,%(contract_type)s,%(department)s,%(province)s,%(district)s,%(amount)s,%(currency)s,%(published_at)s,%(deadline_at)s,%(status)s,%(source_url)s,%(search_text)s,%(raw_json)s,%(now)s,%(now)s)
            ON CONFLICT(source,source_id) DO UPDATE SET code=excluded.code,entity=excluded.entity,description=excluded.description,contract_type=excluded.contract_type,department=excluded.department,province=excluded.province,district=excluded.district,amount=excluded.amount,currency=excluded.currency,published_at=excluded.published_at,deadline_at=excluded.deadline_at,status=excluded.status,source_url=excluded.source_url,search_text=excluded.search_text,raw_json=excluded.raw_json,last_seen=excluded.last_seen""",{**r,"now":now})
        c.commit()
def sync_oece(max_pages=30):
    if not SYNC_LOCK.acquire(blocking=False): return {"ok":True,"busy":True}
    try:
        url=OECE; pages=0; total=0; seen=set()
        while url and pages<max_pages and url not in seen:
            seen.add(url); data=get_json(url,30); rels=extract_releases(data); rows=[]
            for rel in rels:
                try: rows.append(normalize_release(rel))
                except Exception: pass
            upsert(rows); total+=len(rows); pages+=1; url=next_url(data,url)
            if not rels: break
        return {"ok":True,"pages":pages,"rows":total}
    except Exception as e:return {"ok":False,"error":str(e)}
    finally: SYNC_LOCK.release()
def ensure_data():
    with db() as c:n=c.execute("SELECT COUNT(*) n FROM opportunities WHERE source='SEACE'").fetchone()["n"]
    if n<100: sync_oece(8)
def build_search(params):
    q=norm((params.get("q") or [""])[0]); mode=(params.get("mode") or ["all"])[0]; source=(params.get("source") or ["SEACE"])[0]
    dept=(params.get("department") or [""])[0]; typ=(params.get("type") or [""])[0]; status=(params.get("status") or [""])[0]; sort=(params.get("sort") or ["recent"])[0]
    try: page=max(1,int((params.get("page") or ["1"])[0])); per=min(100,max(10,int((params.get("per_page") or ["20"])[0])))
    except: page,per=1,20
    where=["source=%s"]; args=[source]; terms=[x for x in re.split(r"[,;\s]+",q) if x]
    if q:
        if mode=="exact": where.append("search_text ILIKE %s"); args.append("%"+q+"%")
        elif mode=="any": where.append("("+" OR ".join(["search_text ILIKE %s"]*len(terms))+")"); args += ["%"+t+"%" for t in terms]
        else:
            for t in terms: where.append("search_text ILIKE %s"); args.append("%"+t+"%")
    if dept: where.append("department ILIKE %s"); args.append("%"+dept+"%")
    if typ: where.append("contract_type=%s"); args.append(typ)
    if status: where.append("status=%s"); args.append(status)
    order={"recent":"published_at DESC NULLS LAST","deadline":"deadline_at ASC NULLS LAST","entity":"entity ASC","amount_desc":"amount DESC NULLS LAST"}.get(sort,"published_at DESC NULLS LAST")
    return where,args,order,page,per
def do_search(params):
    ensure_data(); where,args,order,page,per=build_search(params); sqlw=" AND ".join(where)
    with db() as c:
        total=c.execute("SELECT COUNT(*) n FROM opportunities WHERE "+sqlw,args).fetchone()["n"]
        rows=c.execute("""SELECT source,source_id,code,entity,description,contract_type,department,province,district,amount,currency,published_at,deadline_at,status,source_url FROM opportunities WHERE """+sqlw+" ORDER BY "+order+" LIMIT %s OFFSET %s",args+[per,(page-1)*per]).fetchall()
    return {"ok":True,"total":total,"page":page,"per_page":per,"rows":[dict(r) for r in rows]}
def stats():
    ensure_data(); today=time.strftime("%Y-%m-%d")
    with db() as c:
        r=c.execute("""SELECT COUNT(*) total,COUNT(*) FILTER(WHERE status='Abierto') open,COUNT(*) FILTER(WHERE published_at=%s) today,COUNT(DISTINCT entity) entities FROM opportunities WHERE source='SEACE'""",(today,)).fetchone()
        types=c.execute("SELECT contract_type,COUNT(*) n FROM opportunities WHERE source='SEACE' GROUP BY contract_type ORDER BY n DESC").fetchall()
        deps=c.execute("SELECT department,COUNT(*) n FROM opportunities WHERE source='SEACE' AND department<>'' GROUP BY department ORDER BY n DESC LIMIT 10").fetchall()
    return {"ok":True,"summary":dict(r),"types":[dict(x) for x in types],"departments":[dict(x) for x in deps]}
def discover_minors():
    out={"ok":True,"base":MINOR_BASE,"public":MINOR_PUBLIC,"candidates":[],"importmap":{},"module_matches":{},"scripts":[],"html_urls":[]}
    shells=[MINOR_PUBLIC,MINOR_BASE+"/",MINOR_BASE+"/v3/api-docs"]
    html=""
    for u in shells:
        try:
            txt=get_text(u,15,5_000_000)
            out["candidates"].append({"url":u,"ok":True,"sample":txt[:500]})
            if "systemjs-importmap" in txt and not html: html=txt
        except Exception as e:
            out["candidates"].append({"url":u,"ok":False,"error":str(e)[:300]})
    if html:
        out["scripts"]=re.findall(r"<script[^>]+src=[\\\"']([^\\\"']+)",html,re.I)[:100]
        out["html_urls"]=sorted(set(re.findall(r"https?://[^\\\"'<>\\s]+",html)))[:200]
        maps=re.findall(r"<script[^>]+type=[\\\"']systemjs-importmap[\\\"'][^>]*>(.*?)</script>",html,re.I|re.S)
        imports={}
        for raw in maps:
            try:
                imp=json.loads(raw)
                vals=imp.get("imports") if isinstance(imp,dict) else {}
                if isinstance(vals,dict): imports.update(vals)
            except Exception:
                pass
        out["importmap"]=imports
        for name,url in imports.items():
            if not isinstance(url,str): continue
            if url.startswith("//"): url="https:"+url
            if not url.startswith("http"): continue
            if "s8uit" not in name.lower() and "s8uit" not in url.lower(): continue
            try:
                js=get_text(url,20,12_000_000)
                matches=set()
                for x in re.findall(r"https?://[^\\\"'\\s)]+",js,re.I):
                    if len(x)<400: matches.add(x)
                for x in re.findall(r"/[A-Za-z0-9_./?=&%-]{3,300}",js):
                    lx=x.lower()
                    if any(k in lx for k in ["s8uit","contrat","cotiza","invit","detalle","buscar","search","listar","public"]):
                        matches.add(x)
                out["module_matches"][name]=sorted(matches)[:250]
            except Exception as e:
                out["module_matches"][name]=["ERROR: "+str(e)[:250]]
    return out

def inspect_s8uit_module(name):
    modules={
      "buscador":"https://prod6.seace.gob.pe/s8uitbuscadorpublico/main.js",
      "menores":"https://prod6.seace.gob.pe/s8uitcontratacionesmenores/main.js",
      "root":"https://prod6.seace.gob.pe/s8uitContainerApp-root-config.js",
      "parametro":"https://prod6.seace.gob.pe/s8uitparametro/main.js",
      "requerimiento":"https://prod6.seace.gob.pe/s8uitrequerimiento/main.js",
      "cotizacion":"https://prod6.seace.gob.pe/s8uitcotizacion/main.js"
    }
    url=modules.get(name)
    if not url: return {"ok":False,"error":"Módulo inválido"}
    try:
        js=get_text(url,25,20_000_000)
    except Exception as e:
        return {"ok":False,"url":url,"error":str(e)}
    keys=["s8uit-services","/v1/","/api/","contrat","cotiza","invit","requer","buscar","search","listar","entidad","ubigeo","region","provincia","distrito","cubso","segmento","item","public"]
    strings=set()
    # Extrae literales JS útiles; los bundles suelen conservar rutas HTTP como strings.
    for pat in [r'"([^"\\]{1,450})"', r"'([^'\\]{1,450})'"]:
        for s in re.findall(pat,js):
            ls=s.lower()
            if any(k in ls for k in keys):
                strings.add(s)
    contexts=[]
    low=js.lower()
    for key in keys:
        pos=0
        hits=0
        while hits<20:
            i=low.find(key,pos)
            if i<0: break
            a=max(0,i-180); b=min(len(js),i+320)
            contexts.append(js[a:b])
            pos=i+len(key); hits+=1
    return {"ok":True,"name":name,"url":url,"length":len(js),"strings":sorted(strings)[:600],"contexts":contexts[:180]}

class H(BaseHTTPRequestHandler):
    server_version="PortalSeguimiento/10.1"
    def log_message(self,fmt,*args): print(fmt%args,flush=True)
    def sec(self):
        self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("X-Frame-Options","DENY"); self.send_header("Referrer-Policy","same-origin")
    def json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False,default=str).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.sec(); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def file(self,name,ctype):
        p=ROOT/name
        if not p.exists(): return self.json({"ok":False,"error":"asset missing"},404)
        b=p.read_bytes(); self.send_response(200); self.send_header("Content-Type",ctype); self.send_header("Cache-Control","no-cache"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n=min(int(self.headers.get("Content-Length","0") or 0),750000); return json.loads(self.rfile.read(n).decode() or "{}")
    def cookie(self,n):
        c=SimpleCookie(); c.load(self.headers.get("Cookie","")); return c[n].value if n in c else ""
    def session(self,csrf=False):
        tok=self.cookie("PSSESSION")
        if not tok:return None
        with db() as c:r=c.execute("""SELECT s.user_id,s.csrf,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>%s""",(sha(tok),int(time.time()))).fetchone()
        if not r:return None
        if csrf and self.headers.get("X-CSRF-Token","")!=r["csrf"]:return None
        return r
    def issue(self,uid):
        tok=secrets.token_urlsafe(32); cs=secrets.token_urlsafe(24); exp=int(time.time())+1209600
        with db() as c:c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(%s,%s,%s,%s)",(sha(tok),uid,cs,exp));c.commit()
        flags="Path=/; HttpOnly; SameSite=Strict; Max-Age=1209600"+("; Secure" if SECURE else ""); self.send_header("Set-Cookie","PSSESSION="+tok+"; "+flags); return cs
    def do_GET(self):
        u=urllib.parse.urlsplit(self.path); p=u.path; params=urllib.parse.parse_qs(u.query)
        if p in ("/","/index.html"):return self.file("index_v10_1.html","text/html; charset=utf-8")
        if p=="/app.js":return self.file("app_v10_1.js","application/javascript; charset=utf-8")
        if p=="/styles.css":return self.file("styles_v10_1.css","text/css; charset=utf-8")
        if p.startswith("/api/internal/run-reset/"):
            supplied=p.rsplit("/",1)[-1]
            expected=os.getenv("PASSWORD_RESET_TOKEN","")
            if not expected or not hmac.compare_digest(supplied,expected):
                return self.json({"ok":False,"error":"No autorizado"},403)
            import importlib
            import reset_password_once
            importlib.reload(reset_password_once)
            return self.json({"ok":True})
        if p=="/api/health":
            try:
                with db() as c:n=c.execute("SELECT COUNT(*) n FROM opportunities").fetchone()["n"]
                return self.json({"ok":True,"version":VERSION,"database":"postgres","opportunities":n})
            except Exception as e:return self.json({"ok":False,"version":VERSION,"error":str(e)},503)
        if p=="/api/auth/me":
            s=self.session(); return self.json({"ok":True,"authenticated":bool(s),"user":({"id":s["user_id"],"email":s["email"],"name":s["name"]} if s else None),"csrf":(s["csrf"] if s else "")})
        if p=="/api/search":
            if not self.session():return self.json({"ok":False,"error":"No autenticado"},401)
            return self.json(do_search(params))
        if p=="/api/stats":
            if not self.session():return self.json({"ok":False,"error":"No autenticado"},401)
            return self.json(stats())
        if p=="/api/departments":
            if not self.session():return self.json({"ok":False,"error":"No autenticado"},401)
            with db() as c:rows=c.execute("SELECT DISTINCT department FROM opportunities WHERE department<>'' ORDER BY department").fetchall()
            return self.json({"ok":True,"departments":[r["department"] for r in rows]})
        if p=="/api/opportunity":
            if not self.session():return self.json({"ok":False,"error":"No autenticado"},401)
            source=(params.get("source") or ["SEACE"])[0]; sid=(params.get("id") or [""])[0]
            with db() as c:r=c.execute("SELECT * FROM opportunities WHERE source=%s AND source_id=%s",(source,sid)).fetchone()
            return self.json({"ok":bool(r),"row":dict(r) if r else None},200 if r else 404)
        if p=="/api/state":
            s=self.session()
            if not s:return self.json({"ok":False,"error":"No autenticado"},401)
            with db() as c:rs=c.execute("SELECT key,value_json FROM user_state WHERE user_id=%s",(s["user_id"],)).fetchall()
            st={}
            for r in rs:
                try:st[r["key"]]=json.loads(r["value_json"])
                except:st[r["key"]]=None
            return self.json({"ok":True,"state":st})
        if p=="/api/diagnostics/search":return self.json(do_search(params))
        if p=="/api/diagnostics/minors":return self.json(discover_minors())
        if p=="/api/diagnostics/module":
            name=(params.get("name") or ["buscador"])[0]
            return self.json(inspect_s8uit_module(name))
        if p=="/api/diagnostics/sync":
            try:pages=min(60,max(1,int((params.get("pages") or ["10"])[0])))
            except:pages=10
            return self.json(sync_oece(pages))
        return self.json({"ok":False,"error":"No encontrado"},404)
    def do_POST(self):
        p=urllib.parse.urlsplit(self.path).path
        try:d=self.body()
        except:return self.json({"ok":False,"error":"JSON inválido"},400)
        if p=="/api/internal/password-reset":
            token=str(d.get("token",""))
            expected=os.getenv("PASSWORD_RESET_TOKEN","")
            if not expected or not hmac.compare_digest(token,expected):
                return self.json({"ok":False,"error":"No autorizado"},403)
            email=str(d.get("email","")).strip().lower()
            password_hash=str(d.get("password_hash","")).strip()
            if not email or not password_hash.startswith("pbkdf2_sha256$"):
                return self.json({"ok":False,"error":"Datos inválidos"},400)
            with db() as c:
                r=c.execute("SELECT id FROM users WHERE lower(email)=lower(%s)",(email,)).fetchone()
                if not r:return self.json({"ok":False,"error":"Usuario no encontrado"},404)
                c.execute("UPDATE users SET password_hash=%s WHERE id=%s",(password_hash,r["id"]))
                c.execute("DELETE FROM sessions WHERE user_id=%s",(r["id"],))
                c.commit()
            return self.json({"ok":True})
        if p=="/api/auth/register":
            email=str(d.get("email","")).strip().lower(); pw=str(d.get("password","")); name=str(d.get("name","")).strip()[:100]
            if "@" not in email or len(pw)<8:return self.json({"ok":False,"error":"Correo inválido o contraseña menor a 8 caracteres"},400)
            try:
                with db() as c:r=c.execute("INSERT INTO users(email,password_hash,name,created_at) VALUES(%s,%s,%s,%s) RETURNING id",(email,pw_hash(pw),name,int(time.time()))).fetchone();c.commit()
                body=json.dumps({"ok":True,"user":{"id":r["id"],"email":email,"name":name}}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); cs=self.issue(r["id"]); self.send_header("X-CSRF-Token",cs); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            except Exception:return self.json({"ok":False,"error":"Ese correo ya está registrado"},409)
            return
        if p=="/api/auth/login":
            email=str(d.get("email","")).strip().lower();pw=str(d.get("password",""))
            with db() as c:r=c.execute("SELECT id,email,name,password_hash FROM users WHERE lower(email)=lower(%s)",(email,)).fetchone()
            if not r or not pw_ok(pw,r["password_hash"]):return self.json({"ok":False,"error":"Credenciales incorrectas"},401)
            body=json.dumps({"ok":True,"user":{"id":r["id"],"email":r["email"],"name":r["name"]}}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); cs=self.issue(r["id"]); self.send_header("X-CSRF-Token",cs); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
        if p=="/api/auth/logout":
            s=self.session(True)
            if not s:return self.json({"ok":False,"error":"Sesión/CSRF inválido"},403)
            tok=self.cookie("PSSESSION")
            with db() as c:c.execute("DELETE FROM sessions WHERE token_hash=%s",(sha(tok),));c.commit()
            self.send_response(200);self.send_header("Set-Cookie","PSSESSION=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict");self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(b'{"ok":true}');return
        if p=="/api/state":
            s=self.session(True)
            if not s:return self.json({"ok":False,"error":"Sesión/CSRF inválido"},403)
            st=d.get("state") or {}
            if not isinstance(st,dict):return self.json({"ok":False,"error":"Estado inválido"},400)
            with db() as c:
                for k,v in st.items():
                    if k not in {"saved","tracking","saved_searches","ui"}:continue
                    c.execute("""INSERT INTO user_state(user_id,key,value_json,updated_at) VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",(s["user_id"],k,json.dumps(v,ensure_ascii=False),int(time.time())))
                c.commit()
            return self.json({"ok":True})
        if p=="/api/sync":
            s=self.session(True)
            if not s:return self.json({"ok":False,"error":"Sesión/CSRF inválido"},403)
            return self.json(sync_oece(20))
        return self.json({"ok":False,"error":"No encontrado"},404)
def bg():
    time.sleep(4)
    while True:
        try:print("[sync]",sync_oece(int(os.getenv("OECE_MAX_PAGES","30"))),flush=True)
        except Exception as e:print("[sync-error]",e,flush=True)
        time.sleep(max(600,int(os.getenv("BACKGROUND_SYNC_INTERVAL","900"))))
if __name__=="__main__":
    init_db(); threading.Thread(target=bg,daemon=True).start()
    print("Portal V"+VERSION+" en "+HOST+":"+str(PORT),flush=True)
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()
