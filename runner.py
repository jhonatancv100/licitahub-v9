#!/usr/bin/env python3
import base64, pathlib, runpy

ROOT=pathlib.Path(__file__).resolve().parent

def materialize(prefix,out):
    parts=sorted((ROOT/'bundle').glob(prefix+'.*'))
    if not parts:
        raise RuntimeError('No se encontraron partes para '+prefix)
    raw=''.join(p.read_text(encoding='utf-8').strip() for p in parts)
    (ROOT/out).write_bytes(base64.b64decode(raw))

materialize('server.b64','server_runtime.py')
materialize('index.b64','index.html')

# Externaliza el JavaScript principal. Esto evita que navegadores/CSP bloqueen
# el script inline de la pantalla de acceso.
index_path=ROOT/'index.html'
html=index_path.read_text(encoding='utf-8')
start=html.rfind('<script>')
end=html.rfind('</script>')
if start >= 0 and end > start:
    js=html[start+8:end]
    # Corrige un error de sintaxis introducido en el bundle original que anulaba todo el JS.
    js=js.replace("})ecatch(e){console.error(e)}}", "})}catch(e){console.error(e)}}")
    # Los controles de autenticación se conectan también por addEventListener
    # para no depender de onclick inline.
    js += """
document.addEventListener('DOMContentLoaded',()=>{
  const login=document.getElementById('tabLogin');
  const reg=document.getElementById('tabReg');
  const btn=document.getElementById('aBtn');
  if(login){
    login.removeAttribute('onclick');
    login.addEventListener('click',()=>mode('login'));
  }
  if(reg){
    reg.removeAttribute('onclick');
    reg.addEventListener('click',()=>mode('register'));
  }
  if(btn){
    btn.removeAttribute('onclick');
    btn.addEventListener('click',()=>submitAuth());
  }
});
"""
    (ROOT/'app.js').write_text(js,encoding='utf-8')
    html=html[:start]+'<script src="/app.js"></script>'+html[end+9:]
    index_path.write_text(html,encoding='utf-8')

# El backend original solo servía index.html. Añadimos app.js y explicitamos
# la política CSP para scripts externos y atributos onclick que aún usa la app.
server_path=ROOT/'server_runtime.py'
srv=server_path.read_text(encoding='utf-8')
srv=srv.replace(
    "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'",
    "script-src 'self'; script-src-attr 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
)
needle='        if path in ("/", "/index.html"):\n'
asset_block='''        if path == "/app.js":
            body = (ROOT / "app.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_security()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
'''
if needle in srv and 'if path == "/app.js":' not in srv:
    srv=srv.replace(needle,asset_block+needle,1)

# Render y algunos monitores realizan HEAD /. Respondemos 200 en vez de 501.
head_needle='    def do_GET(self):\n'
head_method='''    def do_HEAD(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/", "/index.html", "/app.js", "/api/health"):
            self.send_response(200)
            if path == "/app.js":
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
            elif path == "/api/health":
                self.send_header("Content-Type", "application/json; charset=utf-8")
            else:
                self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_security()
            self.end_headers()
            return
        self.send_response(404)
        self.send_security()
        self.end_headers()

'''
if head_needle in srv and '    def do_HEAD(self):' not in srv:
    srv=srv.replace(head_needle,head_method+head_needle,1)

server_path.write_text(srv,encoding='utf-8')
runpy.run_path(str(server_path),run_name='__main__')
