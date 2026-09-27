const $=id=>document.getElementById(id);
async function load(){
  $("error").textContent="";
  try{
    const [statsRes,healthRes]=await Promise.all([fetch("/stats"),fetch("/health")]);
    if(!statsRes.ok) throw new Error("stats");
    const stats=await statsRes.json();
    const p=stats.parser||{};
    const attempts=Number(p.total_attempts||0), success=Number(p.successful||0);
    const rate=attempts ? Math.round(success/attempts*1000)/10 : 0;
    $("attempts").textContent=attempts.toLocaleString("tr-TR");
    $("success").textContent=success.toLocaleString("tr-TR");
    $("rate").textContent=rate+"%"; $("rate2").textContent=rate+"%";
    $("bar").style.width=Math.min(rate,100)+"%";
    $("db").textContent=stats.usage ? "Aktif" : "Devre dışı";
    if(!healthRes.ok) throw new Error("health");
  }catch(e){
    $("error").textContent="Dashboard verisi alınamadı. API erişimini kontrol edin.";
  }
}
$("refresh").addEventListener("click",load); load();
