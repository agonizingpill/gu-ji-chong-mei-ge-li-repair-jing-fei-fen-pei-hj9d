import time,json,logging,os
from pathlib import Path
from .database import Session
from .models import RiskAssessment,Observation,ModelVersion,TrialItem,TrialRun,now
from .risk_service import queue
from .trial_service import TRIAL_QUEUE,maybe_complete
from .algorithm import classify,predict_for
logging.basicConfig(level=logging.INFO)
ARTIFACT_DIR=os.getenv('ARTIFACT_DIR','/artifacts')
def run_daily(db,assessment_id):
    row=db.get(RiskAssessment,assessment_id)
    if not row or row.status!='queued':return
    row.status='running';db.commit()
    try:
        obs=db.get(Observation,row.observation_id)
        version=db.get(ModelVersion,row.model_version_id) if row.model_version_id else None
        version_dict={'id':version.code,'params':version.params} if version else None
        row.predicted,row.metrics=classify(obs.humidity,obs.holes,obs.mold,version_dict)
        row.status='done';row.error=''
        try:
            Path(ARTIFACT_DIR).mkdir(exist_ok=True)
            Path(f'{ARTIFACT_DIR}/risk-{row.id}.json').write_text(json.dumps(row.metrics,ensure_ascii=False))
        except OSError:
            # 共享卷不可写不应作废分级结果；指标已随单据入库，仅记录告警。
            logging.exception('artifact write failed for assessment %s',row.id)
    except Exception as exc:
        row.status='failed';row.error=str(exc)[:200]
def run_trial(db,item_id):
    row=db.get(TrialItem,item_id)
    # 幂等闸门：只有 queued 项可执行；重复消息或已完成册直接跳过，不重复计数。
    if not row or row.status!='queued':return
    run=db.get(TrialRun,row.trial_run_id)
    if not run or run.status!='running':return
    row.status='running';row.attempts+=1;db.commit()
    try:
        candidate=db.get(ModelVersion,run.candidate_version_id)
        obs=db.get(Observation,row.observation_id)
        row.candidate_prediction=predict_for({'id':candidate.code,'params':candidate.params},obs.humidity,obs.holes,obs.mold)
        row.status='done';row.error='';row.updated_at=now()
        maybe_complete(db,run)
    except Exception as exc:
        # 失败保留册次并回到 failed，等待续跑重新排队
        row.status='failed';row.error=str(exc)[:200];row.updated_at=now()
def main():
    while True:
        Path('/tmp/worker-heartbeat').touch()
        try:
            # 两条队列各自独立：试跑积压不阻塞日常分级接单。
            item=queue.blpop([TRIAL_QUEUE,'folio:risk'],timeout=2)
            if not item:continue
            with Session() as db:
                try:
                    if item[0]==TRIAL_QUEUE:run_trial(db,int(item[1]))
                    else:run_daily(db,int(item[1]))
                    db.commit()
                except Exception:
                    db.rollback();logging.exception('job failed id=%s',item[1])
        except Exception:
            logging.exception('worker iteration');time.sleep(1)
if __name__=='__main__':main()
