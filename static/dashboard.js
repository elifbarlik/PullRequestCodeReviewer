const $=id=>document.getElementById(id);

function adminHeaders(){
  const token=window.localStorage.getItem("secpr_admin_token")||"";
  return token ? {"X-Admin-Token":token} : {};
}

async function api(path){
  const res=await fetch(path,{headers:adminHeaders()});
  if(res.status===401){
    const token=window.prompt("Dashboard admin token:");
    if(token){
      window.localStorage.setItem("secpr_admin_token",token);
      return api(path);
    }
  }
  if(!res.ok) throw new Error(String(res.status));
  return res.json();
}

function set(id,value){$(id).textContent=Number(value||0).toLocaleString("tr-TR");}

async function load(){
  $("error").textContent="";
  try{
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
    $("auth-state").textContent="Authenticated dashboard";
    $("reviews").innerHTML=recent.reviews.length ? recent.reviews.map(r=>`
      <tr><td>${escapeHtml(r.repository)}</td><td>#${r.pr_number}</td>
      <td><span class="badge ${escapeHtml(r.status)}">${escapeHtml(r.status)}</span></td>
      <td>${Number(r.files_scanned||0)}</td><td>${Number(r.findings_count||0)}</td></tr>`).join("") :
      '<tr><td colspan="5">Henüz review yok.</td></tr>';
  }catch(e){
    $("error").textContent="Dashboard verisi alınamadı. Admin token geçerli ve API erişilebilir olmalı.";
  }
}

function escapeHtml(value){
  return String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
$("refresh").addEventListener("click",load);
load();