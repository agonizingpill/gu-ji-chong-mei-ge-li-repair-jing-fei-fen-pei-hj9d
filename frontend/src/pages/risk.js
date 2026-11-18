import {store} from '../stores/workspace.js';import {folioOptions,folioName} from '../components/folio-index.js';import {ledger,field,input,select,badge} from '../components/ledger.js';import {esc} from '../utils/format.js';import {bindForm,num,request} from '../utils/forms.js';import {levels} from '../constants/enums.js';
const runStatus={running:'试跑中',completed:'整批核完',activated:'已切换',discarded:'已放弃'};
const itemStatus={queued:'排队',running:'运算中',done:'已核',failed:'失败待续'};
const verStatus={active:'现役',candidate:'候选',archived:'已归档'};
// 试跑数据单独拉取，避免每 3 秒轮询都重建整卷快照。
export const trialStore={data:null,loaded:false,async load(){this.data=await request('/model-versions');this.loaded=true;}};
function verOf(d,id){return d.model_versions.find(v=>v.id===id);}
function verLabel(d,id){const v=verOf(d,id);return v?`${esc(v.code)}`:'—';}
function missMark(item,predKey){
  if(item.status!=='done')return '—';
  const missed=item.librarian_level==='high'&&item[predKey]!=='high';
  return badge(levels[item[predKey]]||'待运算',item[predKey]||'')+(missed?' <em class="miss-flag">漏判</em>':'');
}
export function render(){
  const d=store.data;const latest=d.risk_assessments.at(-1);const t=trialStore.data;
  const isSup=store.session.role==='supervisor';
  return `<h2>虫霉风险分级</h2><p class="intro">按当前病害观测预测隔离等级，再由主管复核。每张分级单在受理瞬间锁定当时的现役模型版本，后续换版不影响在途与已结单据；追加复测后旧复核不再用于开工与交接。</p>
<div class="forms-two"><form id="assess"><h3>提交当前病害分级</h3>${field('在柜卷册',select('accession_id',folioOptions(d)))}<button>送交分级</button><p class="hint">提交后点“刷新卷宗”查看结果。</p></form>
<form id="review"><h3>主管复核签</h3>${field('已完成分级',select('id',d.risk_assessments.filter(v=>v.status==='done').map(v=>`<option value="${v.id}">#${v.id} ${folioName(d,v.accession_id)} / ${levels[v.predicted]}</option>`).join('')))}${field('复核等级',select('level',Object.entries(levels).map(([v,tx])=>`<option value="${v}">${tx}</option>`).join('')))}${field('现场依据',input('note','text','纸张干燥，霉斑已清除'))}<button>签署复核</button></form></div>
<h3>风险记录与实际所用模型版本</h3>${ledger(['卷册','观测编号','模型版本','预测 / 复核','进度','主管意见'],d.risk_assessments.slice().reverse().map(a=>[folioName(d,a.accession_id),'#'+a.observation_id,verLabel(d,a.model_version_id),badge(levels[a.predicted]||'待运算',a.predicted||'')+' / '+(levels[a.approved]||'—'),esc(({queued:'排队',running:'分级中',done:'待复核',reviewed:'已复核',failed:'失败'})[a.status]),esc(a.review_note||a.error)]))}
${t?trialPanel(d,t,isSup):'<p class="hint">模型试跑数据加载中…</p>'}
<section class="model-sheet"><div><span class="eyebrow">分层留出验证</span><h3>病害阈值的可复现检查</h3><p>训练样本由专家规则合成；留出结果仅用于内部验证，实际业务以主管现场复核为准。</p><p>${esc(latest?.metrics?.data_source||'等待分级结果')}</p></div><div><b>Macro F1 ${latest?.metrics?.macro_f1?.toFixed(4)||'—'}</b><p>训练 ${latest?.metrics?.train_count||0} / 留出 ${latest?.metrics?.test_count||0} / seed ${latest?.metrics?.seed||'—'}</p>${latest?.metrics?.confusion_matrix?ledger(['实际\\预测','低','中','高'],latest.metrics.confusion_matrix.map((r,i)=>[levels[latest.metrics.labels[i]],...r])):''}</div></section>`;
}
function trialPanel(d,t,isSup){
  const versions=t.versions.map(v=>`<div class="ver-row"><b>${esc(v.code)}</b><span>${esc(v.label)}</span>${badge(verStatus[v.status]||v.status,v.status)}<small>Macro F1 ${(v.metrics?.macro_f1??0).toFixed(4)} · 深度 ${v.params?.max_depth} · 叶 ${v.params?.min_samples_leaf}</small></div>`).join('');
  const candidateOptions=t.versions.filter(v=>v.status==='candidate').map(v=>`<option value="${v.id}">${esc(v.code)} · ${esc(v.label)}</option>`).join('');
  const runs=t.trials.map(tr=>runBlock(d,tr,isSup)).join('')||'<p class="hint">尚无试跑批次。</p>';
  return `<section class="trial-bench"><div class="trial-head"><span class="eyebrow">模型试跑 / SHADOW RUN</span><h3>候选模型试跑与切换闸门</h3><p class="hint">发起时锁定样本卷册、馆员定级与新旧版本；逐册比对高风险漏判。整批核完且候选版漏判未变多，主管才可一次性切换为现役版本。试跑走独立队列，不影响日常分级接单。</p></div>
<h4>模型版本台账</h4><div class="ver-list">${versions}</div>
${isSup?`<form id="new-version" class="inline-form"><h4>登记候选版本</h4>${field('预设参数',select('preset',['v1','v2-draft','v3-refined'].map(p=>`<option value="${p}">${p}</option>`).join('')))}${field('版本编号',input('code','text','v4-2026q4'))}${field('版本名称',input('label','text','候选模型名称'))}<button class="muted">登记候选</button></form>
<form id="start-trial" class="inline-form"><h4>发起试跑</h4>${field('候选版本',candidateOptions?select('candidate_version_id',candidateOptions):select('candidate_version_id','<option value="">无可用候选</option>'))}${field('批次说明',input('note','text','含高风险件复核卷册比对'))}<button>锁定样本并发起</button></form>`:''}
<div class="trial-runs">${runs}</div></section>`;
}
function runBlock(d,tr,isSup){
  const r=tr.run,p=tr.progress||{};
  const cand=verOf(d,r.candidate_version_id),base=verOf(d,r.baseline_version_id);
  const pct=p.total?Math.round((p.done||0)/p.total*100):0;
  const gateFail=r.status==='completed'&&(p.candidate_high_miss??0)>(p.baseline_high_miss??0);
  const actions=isSup?`<div class="trial-actions">
    ${r.status==='running'?`<button class="muted" data-action="resume" data-id="${r.id}">续跑（重排未核册）</button> <button class="muted" data-action="discard" data-id="${r.id}">放弃批次</button>`:''}
    ${r.status==='completed'?`<button data-action="activate" data-id="${r.id}" ${gateFail?'disabled title="候选版高风险漏判变多，禁止切换"':''}>一次性切换为现役</button>`:''}
    ${r.status==='activated'?badge('已成为现役版本','good'):''}
    ${r.status==='discarded'?badge('批次已放弃',''):''}
  </div>`:'';
  return `<article class="trial-run ${r.status}">
  <header><b>试跑 #${r.id}</b> <span>${esc(base?.code||'')} → ${esc(cand?.code||'')}</span> ${badge(runStatus[r.status]||r.status,r.status)}
  ${gateFail?'<em class="miss-flag">漏判变多 · 闸门拦截</em>':r.status==='completed'?'<em class="ok-flag">满足切换条件</em>':''}</header>
  <div class="progress"><div class="bar" style="width:${pct}%"></div><small>${p.done||0}/${p.total||0} 册已核（${pct}%）· 高风险漏判：现役 ${p.baseline_high_miss??'—'} 册 / 候选 ${p.candidate_high_miss??'—'} 册${p.miss_delta?` · 差值 ${p.miss_delta>0?'+':''}${p.miss_delta}`:''}</small></div>
  ${ledger(['卷册','锁定观测','馆员定级(锁定)','现役版预测','候选版预测','册状态','错误'],tr.items.map(it=>[folioName(d,it.accession_id),'#'+it.observation_id,badge(levels[it.librarian_level],it.librarian_level),it.baseline_prediction?badge(levels[it.baseline_prediction],it.baseline_prediction):'—',missMark(it,'candidate_prediction'),esc(itemStatus[it.status]||it.status)+(it.attempts>1?` ×${it.attempts}`:''),esc(it.error||'')]))}
  ${actions}</article>`;
}
export function bind(r){
  bindForm('assess',x=>request('/risks',num(x,'accession_id')),r);
  bindForm('review',x=>{const id=x.id;delete x.id;return request('/risks/'+id+'/review',x);},r);
  bindForm('new-version',x=>request('/model-versions',x),async msg=>{await trialStore.load();r(msg);});
  bindForm('start-trial',x=>request('/trials',num(x,'candidate_version_id')),async msg=>{await trialStore.load();r(msg);});
  document.querySelectorAll('.trial-actions button[data-action]').forEach(btn=>{
    btn.onclick=async()=>{btn.disabled=true;try{await request('/trials/'+btn.dataset.id+'/'+btn.dataset.action,undefined);await trialStore.load();r('试跑批次已更新');}catch(e){document.getElementById('notice').textContent=e.message;btn.disabled=false;}};
  });
}
