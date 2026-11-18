from sqlalchemy import select,func
from .models import ModelVersion,TrialRun,TrialItem,RiskAssessment,Observation,now
from .common import get,reject,finish,audit
from .algorithm import PRESETS,train
TRIAL_QUEUE='folio:risk-trial'
LEVEL_RANK={'low':0,'medium':1,'high':2}
def active_version(db):
    # 显式字符串比较，避免不同数据库对布尔上下文的处理差异；全局仅一个 active 版本。
    rows=db.scalars(select(ModelVersion).where(ModelVersion.status=='active').order_by(ModelVersion.id.desc())).all()
    return rows[0] if rows else None
def list_versions(db):
    return db.scalars(select(ModelVersion).order_by(ModelVersion.id)).all()
def create_version(db,data,user):
    reject(db.scalar(select(ModelVersion).where(ModelVersion.code==data.code)) is not None,'模型版本编号已存在')
    reject(data.preset not in PRESETS,'未知模型预设，仅允许 '+','.join(PRESETS))
    params=PRESETS[data.preset]
    _,metrics=train({'id':data.code,'params':params})
    row=ModelVersion(code=data.code,label=data.label,status='candidate',params=params,metrics=metrics)
    db.add(row);db.flush();return finish(db,user,'登记候选模型版本',row)
def _high_risk_sample(db):
    """含高风险件的已复核卷册：取每册最新观测上、馆员定级为 high 的已复核单。"""
    latest=select(Observation.accession_id,func.max(Observation.id).label('oid')).group_by(Observation.accession_id).subquery()
    stmt=select(RiskAssessment).join(latest,RiskAssessment.observation_id==latest.c.oid).where(RiskAssessment.status=='reviewed',RiskAssessment.approved=='high')
    return list(db.scalars(stmt))
def start_trial(db,data,user,queue):
    candidate=get(db,ModelVersion,data.candidate_version_id,True)
    reject(candidate.status!='candidate','仅候选版本可发起试跑')
    running=db.scalar(select(TrialRun).where(TrialRun.status=='running'))
    reject(running is not None,'已有进行中的试跑，请先完成或放弃该批次')
    baseline=active_version(db)
    reject(baseline is None,'系统缺少现役模型版本')
    reject(baseline.id==candidate.id,'候选版本不能与现役版本相同')
    reviews=_high_risk_sample(db)
    reject(not reviews,'没有含高风险馆员定级的已复核卷册，无法发起试跑')
    run=TrialRun(candidate_version_id=candidate.id,baseline_version_id=baseline.id,note=data.note or '')
    db.add(run);db.flush()
    queued=0
    for review in reviews:
        # 唯一约束 (trial_run_id, accession_id) 兜底；发起时每册只入一条样本
        item=TrialItem(trial_run_id=run.id,accession_id=review.accession_id,observation_id=review.observation_id,
                       librarian_level=review.approved,baseline_prediction=review.predicted)
        db.add(item);db.flush();queue.rpush(TRIAL_QUEUE,item.id);queued+=1
    audit(db,user,'发起模型试跑',f'#{run.id} 候选 {candidate.code} 样本 {queued} 册')
    db.commit();return {'trial_run_id':run.id,'locked_items':queued,'baseline':baseline.code,'candidate':candidate.code}
def resume_trial(db,run_id,user,queue):
    run=get(db,TrialRun,run_id,True)
    reject(run.status!='running','试跑已结束，不能续跑')
    # 中断恢复：worker 被强杀时 running 项会滞留；连同 failed 项一起重新排队。
    # 已 done 的册不再入队，重试不会重复计入同一册。
    stale=list(db.scalars(select(TrialItem).where(TrialItem.trial_run_id==run.id,TrialItem.status.in_(['queued','running','failed']))))
    requeued=0
    for item in stale:
        if item.status in ('running','failed'):
            item.status='queued';item.error='';item.updated_at=now()
        queue.rpush(TRIAL_QUEUE,item.id);requeued+=1
    audit(db,user,'续跑模型试跑',f'#{run.id} 重排 {requeued} 册')
    db.commit();return {'trial_run_id':run.id,'requeued':requeued,'finished':requeued==0}
def discard_trial(db,run_id,user):
    run=get(db,TrialRun,run_id,True)
    reject(run.status!='running','仅进行中的试跑可放弃')
    run.status='discarded'
    return finish(db,user,'放弃模型试跑',run)
def _missed(item,prediction):
    return item.librarian_level=='high' and LEVEL_RANK.get(prediction,0)<LEVEL_RANK['high']
def summarize(db,run):
    items=list(db.scalars(select(TrialItem).where(TrialItem.trial_run_id==run.id)))
    done=[i for i in items if i.status=='done']
    baseline_miss=sum(1 for i in done if _missed(i,i.baseline_prediction))
    candidate_miss=sum(1 for i in done if _missed(i,i.candidate_prediction))
    return {'total':len(items),'done':len(done),
            'baseline_high_miss':baseline_miss,'candidate_high_miss':candidate_miss,
            'miss_delta':candidate_miss-baseline_miss}
def maybe_complete(db,run):
    pending=db.scalar(select(TrialItem).where(TrialItem.trial_run_id==run.id,TrialItem.status!='done'))
    if pending is None and run.status=='running':
        run.status='completed';run.summary=summarize(db,run)
        run.finished_at=now()
    return run
def list_trials(db):
    return [{'run':run,'items':db.scalars(select(TrialItem).where(TrialItem.trial_run_id==run.id).order_by(TrialItem.id)).all(),
             'progress':summarize(db,run) if run.status=='running' else run.summary}
            for run in db.scalars(select(TrialRun).order_by(TrialRun.id.desc())).all()]
def activate(db,run_id,user):
    run=get(db,TrialRun,run_id,True)
    reject(run.status=='activated','该试跑候选已切换为现役版本')
    reject(run.status=='discarded','试跑已放弃，不能切换')
    reject(run.status!='completed','整批未核完，不能切换')
    summary=run.summary
    # 主管一次性切换闸门：候选版高风险漏判不得变多
    reject(summary.get('candidate_high_miss',0)>summary.get('baseline_high_miss',0),
           f"候选版高风险漏判 {summary.get('candidate_high_miss')} 册，多于现役 {summary.get('baseline_high_miss')} 册，禁止切换")
    candidate=get(db,ModelVersion,run.candidate_version_id,True)
    baseline=get(db,ModelVersion,run.baseline_version_id,True)
    # 按固定顺序加锁，避免两个并发切换事务交叉加锁；全局仍只保留一个 active 版本。
    first,second=sorted((candidate,baseline),key=lambda v:v.id)
    get(db,ModelVersion,first.id,True);get(db,ModelVersion,second.id,True)
    reject(candidate.status!='candidate','候选版本状态已变化，请刷新重试')
    baseline.status='archived';candidate.status='active'
    candidate.activated_at=now();run.status='activated';run.activated_at=now()
    audit(db,user,'切换现役风险模型',f'试跑 #{run.id}：{baseline.code} → {candidate.code}；漏判 {summary.get("baseline_high_miss")}→{summary.get("candidate_high_miss")}')
    db.commit()
    return {'activated':candidate.code,'archived':baseline.code,'summary':summary}
