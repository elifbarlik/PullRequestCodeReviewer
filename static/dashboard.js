const $=id=>document.getElementById(id);

async function api(path){
  const res=await fetch(path);
  if(!res.ok) throw new Error(String(res.status));
  return res.json();
}

function set(id,value){$(id).textContent=Number(value||0).toLocaleString("tr-TR");}
function escapeHtml(value){
  return String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

async function loadSettings(id){
  const d=await api("/installations/"+encodeURIComponent(id)+"/settings");
  $("settings-enabled").checked=!!d.enabled;
  $("settings-status").textContent=d.semgrep_configs ? "Özel ruleset: "+d.semgrep_configs.join(", ") : "Varsayılan Semgrep ruleset'i kullanılıyor.";
}
async function saveSettings(reset=false){
  const id=$("installation-select").value;
  if(!id) return;
  const body=reset ? {reset_configs:true} : {enabled:$("settings-enabled").checked};
  const res=await fetch("/installations/"+encodeURIComponent(id)+"/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(!res.ok) throw new Error(String(res.status));
  const d=await res.json();
  $("settings-enabled").checked=!!d.enabled;
  $("settings-status").textContent=d.semgrep_configs ? "Özel ruleset: "+d.semgrep_configs.join(", ") : "Varsayılan Semgrep ruleset'i kullanılıyor.";
}

async function load(){
  $("error").textContent="";
  try{
    const me=await api("/auth/me");
    $("session-status").textContent="● "+me.login;
    $("login").hidden=true; $("logout").hidden=false;
    const ids=me.installation_ids || [];
    $("installation-select").innerHTML=ids.map(id=>`<option value="${id}">${id}</option>`).join("");
    $("settings-panel").hidden=ids.length===0;
    if(ids.length) await loadSettings(ids[0]);
    const [summary,recent]=await Promise.all([
      api("/dashboard/api/summary"),
      api("/dashboard/api/reviews?limit=20")
    ]);
    set("total",summary.total_reviews);
    set("successful",summary.successful_reviews);
    set("failed",summary.failed_reviews);
    set("findings",summary.findings);
    set("critical",summary.severity.critical);
    set("high",summary.severity.high);
    set("medium",summary.severity.medium);
    set("low",summary.severity.low);
    $("auth-state").textContent="GitHub user session";
    $("reviews").innerHTML=recent.reviews.length ? recent.reviews.map(r=>`
      <tr class="review-row" data-review-id="${r.id}" tabindex="0"><td>${escapeHtml(r.repository)}</td><td>#${r.pr_number}</td>
      <td><span class="badge ${escapeHtml(r.status)}">${escapeHtml(r.status)}</span></td>
      <td>${Number(r.files_scanned||0)}</td><td>${Number(r.findings_count||0)}</td></tr>`).join("") :
      '<tr><td colspan="5">Henüz review yok.</td></tr>';
  }catch(e){
    $("login").hidden=false; $("logout").hidden=true;
    $("session-status").textContent="● Login required";
    $("reviews").innerHTML='<tr><td colspan="5">Dashboardu görmek için GitHub ile giriş yapın.</td></tr>';
    $("error").textContent="";
  }
}

$("logout").addEventListener("click",async()=>{
  await fetch("/auth/logout",{method:"POST"});
  window.location.reload();
});
$("refresh").addEventListener("click",load);
load();
async function showDetail(id){
  try{
    const d=await api("/dashboard/api/reviews/"+encodeURIComponent(id));
    $("detail").hidden=false;
    $("detail-content").innerHTML=`
      <div class="cards">
        <div class="card"><span>Repository</span><strong>${escapeHtml(d.repository)}</strong></div>
        <div class="card"><span>PR</span><strong>#${d.pr_number}</strong></div>
        <div class="card"><span>Status</span><strong>${escapeHtml(d.status)}</strong></div>
        <div class="card"><span>Findings</span><strong>${Number(d.findings_count||0)}</strong></div>
      </div>
      <p class="muted">Commit: ${escapeHtml(d.head_sha)}</p>
      <p class="muted">Files scanned: ${Number(d.files_scanned||0)}</p>
      <p class="muted">Critical ${d.severity.critical} · High ${d.severity.high} · Medium ${d.severity.medium} · Low ${d.severity.low}</p>`;
  }catch(e){ $("error").textContent="Review detayı alınamadı."; }
}
$("close-detail").addEventListener("click",()=>{$("detail").hidden=true;});

document.addEventListener("click",(event)=>{
  const row=event.target.closest(".review-row");
  if(row) showDetail(row.dataset.reviewId);
});

$("installation-select").addEventListener("change",()=>loadSettings($("installation-select").value).catch(()=>{$("settings-status").textContent="Ayarlar alınamadı.";}));
$("save-settings").addEventListener("click",()=>saveSettings(false).catch(()=>{$("settings-status").textContent="Ayarlar kaydedilemedi.";}));
$("reset-settings").addEventListener("click",()=>saveSettings(true).catch(()=>{$("settings-status").textContent="Varsayılan ayarlar uygulanamadı.";}));
