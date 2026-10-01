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

async function load(){
  $("error").textContent="";
  try{
    const me=await api("/auth/me");
    $("session-status").textContent="● "+me.login;
    $("login").hidden=true; $("logout").hidden=false;
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
      <tr><td>${escapeHtml(r.repository)}</td><td>#${r.pr_number}</td>
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