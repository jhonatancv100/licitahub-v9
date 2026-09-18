let csrf="",user=null,page="dashboard",searchPage=1,currentRows=[],tracking=[],statsData=null,deps=[];
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
async function api(url,opt={}){
  opt.headers={...(opt.headers||{}),"Content-Type":"application/json"};
  if(csrf && opt.method && opt.method!=="GET") opt.headers["X-CSRF-Token"]=csrf;
  const r=await fetch(url,opt); let j={}; try{j=await r.json()}catch{}
  if(!r.ok) throw new Error(j.error||("HTTP "+r.status)); return j;
}
function setAuthMode(mode){
  const reg=mode==="register"; $("tabLogin").classList.toggle("active",!reg); $("tabRegister").classList.toggle("active",reg);
  $("nameField").classList.toggle("hidden",!reg); $("authSubmit").textContent=reg?"Crear cuenta":"Ingresar"; $("authSubmit").dataset.mode=mode;
}
async function submitAuth(){
  $("authError").classList.add("hidden");
  try{
    const mode=$("authSubmit").dataset.mode||"login";
    const payload={email:$("authEmail").value.trim(),password:$("authPass").value,name:$("authName").value.trim()};
    await api("/api/auth/"+mode,{method:"POST",body:JSON.stringify(payload)}); await boot();
  }catch(e){$("authError").textContent=e.message;$("authError").classList.remove("hidden")}
}
async function boot(){
  const me=await api("/api/auth/me"); 
  if(!me.authenticated){$("auth").classList.remove("hidden");$("app").classList.add("hidden");return}
  user=me.user;csrf=me.csrf;$("auth").classList.add("hidden");$("app").classList.remove("hidden");
  $("userName").textContent=user.name||"Usuario";$("userEmail").textContent=user.email;
  try{const st=await api("/api/state");tracking=Array.isArray(st.state.tracking)?st.state.tracking:[]}catch{}
  await loadStats(); render();
}
async function persistTracking(){await api("/api/state",{method:"POST",body:JSON.stringify({state:{tracking}})})}
async function loadStats(){try{statsData=await api("/api/stats");const d=await api("/api/departments");deps=d.departments||[];$("statusText").textContent="Datos reales almacenados en PostgreSQL · "+(statsData.summary?.total||0)+" procesos";}catch(e){$("statusText").textContent="Error de datos: "+e.message}}
async function logout(){try{await api("/api/auth/logout",{method:"POST",body:"{}"})}catch{} location.reload()}
function nav(p){page=p;document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b.dataset.page===p));$("pageTitle").textContent={dashboard:"Dashboard",search:"SEACE / OECE",minors:"Contratos Menores",tracking:"Seguimiento",calendar:"Calendario",stats:"Estadísticas"}[p];render()}
function money(r){if(r.amount==null)return "—";try{return new Intl.NumberFormat("es-PE",{style:"currency",currency:r.currency||"PEN",maximumFractionDigits:2}).format(r.amount)}catch{return "S/ "+r.amount}}
function dashboard(){
 const s=statsData?.summary||{};return `
 <div class="grid4">
  <div class="card kpi"><div class="label">PROCESOS CARGADOS</div><div class="value">${s.total||0}</div><div class="muted small">OECE / SEACE</div></div>
  <div class="card kpi"><div class="label">ABIERTOS</div><div class="value">${s.open||0}</div><div class="muted small">Según estado publicado</div></div>
  <div class="card kpi"><div class="label">PUBLICADOS HOY</div><div class="value">${s.today||0}</div><div class="muted small">${new Date().toLocaleDateString("es-PE")}</div></div>
  <div class="card kpi"><div class="label">ENTIDADES</div><div class="value">${s.entities||0}</div><div class="muted small">Entidades únicas</div></div>
 </div>
 <div class="grid2" style="margin-top:14px">
  <div class="card"><h3 class="section-title">Buscar oportunidades</h3><p class="muted">Busca simultáneamente por código, entidad, descripción y ubicación.</p>
   <div class="field"><input id="dashQ" placeholder="Ej.: residuos sólidos, compactador, volquete"></div>
   <button class="primary" id="dashSearch">Buscar en SEACE</button>
  </div>
  <div class="card"><h3 class="section-title">Seguimiento</h3><div class="grid2">
   <div class="kpi"><div class="label">EN CALENDARIO</div><div class="value">${tracking.length}</div></div>
   <div class="kpi"><div class="label">COTIZACIÓN ENVIADA</div><div class="value">${tracking.filter(x=>x.stage==="Cotización enviada").length}</div></div>
  </div></div>
 </div>
 <div class="grid2" style="margin-top:14px"><div class="card"><h3 class="section-title">Por tipo</h3>${bars(statsData?.types||[],"contract_type")}</div><div class="card"><h3 class="section-title">Departamentos con más procesos</h3>${bars(statsData?.departments||[],"department")}</div></div>`;
}
function bars(rows,key){const max=Math.max(1,...rows.map(x=>Number(x.n)||0));return rows.length?rows.map(x=>`<div class="barrow"><span>${esc(x[key]||"Sin dato")}</span><div class="bar"><span style="width:${Math.round((x.n/max)*100)}%"></span></div><b>${x.n}</b></div>`).join(""):'<div class="muted">Sin datos todavía.</div>'}
function searchView(){
 const depOptions=['<option value="">Todos los departamentos</option>',...deps.map(x=>`<option>${esc(x)}</option>`)].join("");
 return `<div class="card">
 <div class="filterbar">
  <div><label class="small muted">Palabras clave</label><input id="q" placeholder="residuos sólidos, compactador, volquete"></div>
  <div><label class="small muted">Coincidencia</label><select id="mode"><option value="all">Todas las palabras</option><option value="any">Cualquiera</option><option value="exact">Frase exacta</option></select></div>
  <div><label class="small muted">Departamento</label><select id="department">${depOptions}</select></div>
  <div><label class="small muted">Tipo</label><select id="type"><option value="">Todos</option><option>Servicios</option><option>Bienes</option><option>Consultoría</option><option>Obras</option></select></div>
  <div><label class="small muted">Estado</label><select id="searchStatus"><option value="">Todos</option><option>Abierto</option><option>Cerrado</option></select></div>
  <button class="primary" id="searchBtn">Buscar</button>
 </div>
 <div class="result-meta"><div><b id="resultCount">Escribe una búsqueda</b><div class="muted small">Fuente: Contrataciones Abiertas OECE / SEACE</div></div>
 <select id="sort"><option value="recent">Publicación reciente</option><option value="deadline">Cierre más próximo</option><option value="entity">Entidad A-Z</option><option value="amount_desc">Mayor monto</option></select></div>
 <div id="results" class="list"><div class="empty muted">Puedes buscar varias palabras juntas. Ejemplo: <b>residuos sólidos transporte</b>.</div></div><div id="pager" class="pager"></div>
 </div>`;
}
async function runSearch(pg=1){
 searchPage=pg;const q=$("q")?.value.trim()||"";const mode=$("mode")?.value||"all",department=$("department")?.value||"",type=$("type")?.value||"",status=$("searchStatus")?.value||"",sort=$("sort")?.value||"recent";
 $("resultCount").textContent="Buscando…";$("results").innerHTML='<div class="empty muted">Consultando la base de procesos…</div>';
 try{
  const qs=new URLSearchParams({q,mode,department,type,status,sort,page:String(pg),per_page:"20"});
  const j=await api("/api/search?"+qs);currentRows=j.rows||[];$("resultCount").textContent=j.total+" resultados";
  $("results").innerHTML=currentRows.length?currentRows.map(resultCard).join(""):'<div class="empty muted">No se encontraron procesos con esos criterios.</div>';
  renderPager(j.total,j.page,j.per_page);
 }catch(e){$("resultCount").textContent="Error";$("results").innerHTML='<div class="error">'+esc(e.message)+'</div>'}
}
function resultCard(r){
 const saved=tracking.some(x=>x.source===r.source&&x.source_id===r.source_id);
 return `<article class="result">
  <div><h3>${esc(r.description)}</h3><div class="entity">${esc(r.entity)}</div><div class="small muted">${esc(r.code||"Sin código")}</div>
   <div class="chips"><span class="chip">${esc(r.contract_type||"—")}</span>${r.department?`<span class="chip">${esc(r.department)}</span>`:''}<span class="chip ${r.status==="Abierto"?"open":"closed"}">${esc(r.status)}</span>${r.deadline_at?`<span class="chip deadline">Cierre: ${esc(r.deadline_at)}</span>`:''}<span class="chip">${money(r)}</span></div>
  </div>
  <div class="result-actions"><button class="ghost detailBtn" data-id="${esc(r.source_id)}">Ver detalle</button><button class="${saved?"ghost":"primary"} saveBtn" data-id="${esc(r.source_id)}">${saved?"En seguimiento":"＋ Seguir"}</button></div>
 </article>`;
}
function renderPager(total,pg,per){const pages=Math.max(1,Math.ceil(total/per));let h="";for(let p=Math.max(1,pg-2);p<=Math.min(pages,pg+2);p++)h+=`<button class="${p===pg?"active":""}" data-p="${p}">${p}</button>`;$("pager").innerHTML=h}
async function detail(id){
 try{
  const j=await api("/api/opportunity?source=SEACE&id="+encodeURIComponent(id));const r=j.row;
  $("modalBody").innerHTML=`<h2>${esc(r.description)}</h2><p><b>${esc(r.entity)}</b></p><div class="detail-grid">
   ${detailItem("Código",r.code)}${detailItem("Tipo",r.contract_type)}${detailItem("Estado",r.status)}${detailItem("Monto",money(r))}
   ${detailItem("Publicación",r.published_at||"—")}${detailItem("Cierre",r.deadline_at||"—")}${detailItem("Departamento",r.department||"—")}${detailItem("Provincia / localidad",r.province||"—")}
  </div><div style="margin-top:16px"><a class="primary linkbtn" target="_blank" rel="noopener" href="${esc(r.source_url)}">Abrir fuente oficial</a></div>`;
  $("modal").classList.remove("hidden");
 }catch(e){alert(e.message)}
}
function detailItem(k,v){return `<div class="detail-item"><b>${esc(k)}</b>${esc(v??"—")}</div>`}
async function follow(id){
 const r=currentRows.find(x=>x.source_id===id);if(!r)return;
 const i=tracking.findIndex(x=>x.source===r.source&&x.source_id===r.source_id);
 if(i>=0)tracking.splice(i,1);else tracking.unshift({...r,stage:"Revisada",notes:"",saved_at:new Date().toISOString()});
 await persistTracking();runSearch(searchPage);
}
function trackingView(){
 const stages=["Revisada","Por cotizar","Cotización enviada","Ganada / Perdida"];
 return `<div class="tracking-grid">${stages.map(stage=>`<div class="column"><h3>${stage} · ${tracking.filter(x=>x.stage===stage).length}</h3>${tracking.filter(x=>x.stage===stage).map(trackCard).join("")||'<div class="muted small">Sin procesos</div>'}</div>`).join("")}</div>`;
}
function trackCard(x){return `<div class="track-card"><b>${esc(x.code||"Proceso")}</b><div class="small">${esc(x.entity)}</div><div class="muted small" style="margin-top:4px">${esc(x.description)}</div><select class="stageSel" data-id="${esc(x.source_id)}"><option ${x.stage==="Revisada"?"selected":""}>Revisada</option><option ${x.stage==="Por cotizar"?"selected":""}>Por cotizar</option><option ${x.stage==="Cotización enviada"?"selected":""}>Cotización enviada</option><option ${x.stage==="Ganada / Perdida"?"selected":""}>Ganada / Perdida</option></select><button class="ghost removeTrack" data-id="${esc(x.source_id)}" style="margin-top:7px;width:100%">Quitar</button></div>`}
function calendarView(){
 const sorted=[...tracking].filter(x=>x.deadline_at).sort((a,b)=>String(a.deadline_at).localeCompare(String(b.deadline_at)));
 return `<div class="card"><h3 class="section-title">Próximos cierres</h3>${sorted.length?`<table class="table"><thead><tr><th>Cierre</th><th>Código</th><th>Entidad</th><th>Etapa</th></tr></thead><tbody>${sorted.map(x=>`<tr><td><b>${esc(x.deadline_at)}</b></td><td>${esc(x.code)}</td><td>${esc(x.entity)}</td><td>${esc(x.stage)}</td></tr>`).join("")}</tbody></table>`:'<div class="muted">Agrega procesos con fecha de cierre a seguimiento.</div>'}</div>`;
}
function statsView(){return `<div class="grid2"><div class="card"><h3 class="section-title">Distribución por tipo</h3>${bars(statsData?.types||[],"contract_type")}</div><div class="card"><h3 class="section-title">Top departamentos</h3>${bars(statsData?.departments||[],"department")}</div></div><div class="card" style="margin-top:14px"><h3 class="section-title">Resumen de la base</h3><p>Los indicadores se calculan sobre procesos obtenidos de la fuente oficial de Contrataciones Abiertas del OECE y almacenados en PostgreSQL. No son cifras de demostración.</p></div>`}
function minorsView(){return `<div class="card"><h2>Contratos Menores ≤ 8 UIT</h2><div class="notice">El buscador oficial de Contratos Menores está operativo. Estoy validando el servicio estructurado público antes de incorporarlo directamente; esta pantalla no inventa resultados.</div><p>Mientras se termina esa conexión, puedes consultar la fuente oficial directamente:</p><a class="primary linkbtn" target="_blank" rel="noopener" href="https://prod6.seace.gob.pe/buscador-publico/contrataciones">Abrir buscador oficial de Contratos Menores</a></div>`}
function render(){
 let html=page==="dashboard"?dashboard():page==="search"?searchView():page==="minors"?minorsView():page==="tracking"?trackingView():page==="calendar"?calendarView():statsView();$("content").innerHTML=html;
 if(page==="dashboard")$("dashSearch")?.addEventListener("click",()=>{nav("search");setTimeout(()=>{$("q").value=$("dashQ")?.value||"";runSearch(1)},0)});
 if(page==="search"){
  $("searchBtn").addEventListener("click",()=>runSearch(1));$("q").addEventListener("keydown",e=>{if(e.key==="Enter")runSearch(1)});$("sort").addEventListener("change",()=>runSearch(1));
  $("content").addEventListener("click",e=>{const d=e.target.closest(".detailBtn"),s=e.target.closest(".saveBtn"),p=e.target.closest("[data-p]");if(d)detail(d.dataset.id);if(s)follow(s.dataset.id);if(p)runSearch(Number(p.dataset.p))});
 }
 if(page==="tracking"){
  $("content").addEventListener("change",async e=>{if(e.target.classList.contains("stageSel")){const x=tracking.find(t=>t.source_id===e.target.dataset.id);if(x){x.stage=e.target.value;await persistTracking();render()}}});
  $("content").addEventListener("click",async e=>{const b=e.target.closest(".removeTrack");if(b){tracking=tracking.filter(x=>x.source_id!==b.dataset.id);await persistTracking();render()}});
 }
}
async function syncNow(){const b=$("syncBtn");b.disabled=true;b.textContent="Actualizando…";try{const j=await api("/api/sync",{method:"POST",body:"{}"});await loadStats();render();b.textContent=j.busy?"Sincronización en curso":"↻ Actualizar datos"}catch(e){b.textContent="Error: "+e.message}finally{setTimeout(()=>{b.disabled=false;b.textContent="↻ Actualizar datos"},2000)}}
$("tabLogin").addEventListener("click",()=>setAuthMode("login"));$("tabRegister").addEventListener("click",()=>setAuthMode("register"));$("authSubmit").addEventListener("click",submitAuth);$("authPass").addEventListener("keydown",e=>{if(e.key==="Enter")submitAuth()});$("logoutBtn").addEventListener("click",logout);$("syncBtn").addEventListener("click",syncNow);document.querySelectorAll(".nav").forEach(b=>b.addEventListener("click",()=>nav(b.dataset.page)));$("modalClose").addEventListener("click",()=>$("modal").classList.add("hidden"));$("modal").addEventListener("click",e=>{if(e.target===$("modal"))$("modal").classList.add("hidden")});setAuthMode("login");boot().catch(e=>{$("authError").textContent=e.message;$("authError").classList.remove("hidden")});
