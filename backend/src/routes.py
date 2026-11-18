import hmac
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .database import session
from .models import *
from .schemas import *
from .auth import current,editor,supervisor,issue,password_hash
from .common import dump
from . import catalog_service as catalog,isolation_service as isolation,risk_service as risk,treatment_service as treatment,grant_service as grant,handover_service as handovers,trial_service as trials
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,db=Depends(session)):
    user=db.scalar(select(User).where(User.username==data.username))
    if not user or not hmac.compare_digest(user.password,password_hash(data.password)):raise HTTPException(401,'账号或密码错误')
    return {'token':issue(user),'username':user.username,'role':user.role}
@router.get('/workspace')
def workspace(db=Depends(session),user=Depends(current)):
    models=[Accession,Observation,Cabinet,Isolation,RiskAssessment,Treatment,Step,Grant,Encumbrance,Handover,ModelVersion,TrialRun,TrialItem]
    return {m.__tablename__:[dump(v) for v in db.scalars(select(m).order_by(m.id))] for m in models}
@router.get('/audit')
def audits(db=Depends(session),user=Depends(supervisor)):return [dump(v) for v in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100))]
@router.post('/accessions')
def register(data:FolioInput,db=Depends(session),user=Depends(editor)):return catalog.register(db,data,user)
@router.post('/observations')
def observe(data:ObservationInput,db=Depends(session),user=Depends(editor)):return catalog.observe(db,data,user)
@router.post('/cabinets')
def cabinet(data:CabinetInput,db=Depends(session),user=Depends(supervisor)):return isolation.cabinet(db,data,user)
@router.post('/isolations')
def admit(data:AdmitInput,db=Depends(session),user=Depends(editor)):return isolation.admit(db,data,user)
@router.post('/risks')
def assess(data:RiskInput,db=Depends(session),user=Depends(editor)):return risk.request_risk(db,data,user)
@router.post('/risks/{id}/review')
def review(id:int,data:ReviewInput,db=Depends(session),user=Depends(supervisor)):return risk.review(db,id,data,user)
@router.get('/model-versions')
def model_versions(db=Depends(session),user=Depends(current)):
    return {'versions':[dump(v) for v in trials.list_versions(db)],
            'trials':[{'run':dump(t['run']),'progress':t['progress'],'items':[dump(i) for i in t['items']]} for t in trials.list_trials(db)]}
@router.post('/model-versions')
def create_model_version(data:ModelVersionInput,db=Depends(session),user=Depends(supervisor)):return trials.create_version(db,data,user)
@router.post('/trials')
def start_trial(data:TrialStartInput,db=Depends(session),user=Depends(supervisor)):return trials.start_trial(db,data,user,risk.queue)
@router.post('/trials/{id}/resume')
def resume_trial(id:int,db=Depends(session),user=Depends(supervisor)):return trials.resume_trial(db,id,user,risk.queue)
@router.post('/trials/{id}/discard')
def discard_trial(id:int,db=Depends(session),user=Depends(supervisor)):return trials.discard_trial(db,id,user)
@router.post('/trials/{id}/activate')
def activate_trial(id:int,db=Depends(session),user=Depends(supervisor)):return trials.activate(db,id,user)
@router.post('/treatments')
def propose(data:TreatmentInput,db=Depends(session),user=Depends(supervisor)):return treatment.propose(db,data,user)
@router.patch('/treatments/{id}')
def revise(id:int,data:RevisionInput,db=Depends(session),user=Depends(supervisor)):return treatment.revise(db,id,data,user)
@router.post('/treatments/{id}/cancel')
def cancel(id:int,db=Depends(session),user=Depends(supervisor)):return treatment.cancel(db,id,user)
@router.post('/steps/{id}/complete')
def step(id:int,data:EvidenceInput,db=Depends(session),user=Depends(editor)):return treatment.complete_step(db,id,data,user)
@router.post('/grants')
def create_grant(data:GrantInput,db=Depends(session),user=Depends(supervisor)):return grant.create_grant(db,data,user)
@router.post('/treatments/{id}/fund')
def fund(id:int,data:FundInput,db=Depends(session),user=Depends(supervisor)):return grant.fund(db,id,data,user)
@router.post('/treatments/{id}/settle')
def settle(id:int,data:SettleInput,db=Depends(session),user=Depends(supervisor)):return grant.settle(db,id,data,user)
@router.post('/handovers')
def handover(data:HandoverInput,db=Depends(session),user=Depends(supervisor)):return handovers.handover(db,data,user)
