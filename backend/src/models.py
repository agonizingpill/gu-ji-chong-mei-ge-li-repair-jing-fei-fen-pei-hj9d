from datetime import datetime,timezone
from sqlalchemy import Integer,String,Float,ForeignKey,UniqueConstraint,CheckConstraint,JSON,DateTime,Boolean,Index,text
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
from .constants import FolioState,PlanState
def now():return datetime.now(timezone.utc)
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True)
    username:Mapped[str]=mapped_column(String(40),unique=True)
    password:Mapped[str]=mapped_column(String(128))
    role:Mapped[str]=mapped_column(String(20))
class Accession(Base):
    __tablename__='accessions'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(40),unique=True)
    title:Mapped[str]=mapped_column(String(100))
    era:Mapped[str]=mapped_column(String(40))
    paper:Mapped[str]=mapped_column(String(40))
    status:Mapped[str]=mapped_column(String(20),default=FolioState.registered.value)
class Observation(Base):
    __tablename__='observations'
    __table_args__=(CheckConstraint('humidity >= 0 AND humidity <= 100'),CheckConstraint('holes >= 0'),CheckConstraint('mold >= 0 AND mold <= 100'))
    id:Mapped[int]=mapped_column(primary_key=True)
    accession_id:Mapped[int]=mapped_column(ForeignKey('accessions.id'))
    humidity:Mapped[float]=mapped_column(Float)
    holes:Mapped[int]=mapped_column(Integer)
    mold:Mapped[float]=mapped_column(Float)
    note:Mapped[str]=mapped_column(String(300),default='')
    at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Cabinet(Base):
    __tablename__='cabinets'
    __table_args__=(CheckConstraint('capacity > 0'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(30),unique=True)
    capacity:Mapped[int]=mapped_column(Integer)
class Isolation(Base):
    __tablename__='isolations'
    id:Mapped[int]=mapped_column(primary_key=True)
    accession_id:Mapped[int]=mapped_column(ForeignKey('accessions.id'))
    cabinet_id:Mapped[int]=mapped_column(ForeignKey('cabinets.id'))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    entered:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    exited:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class RiskAssessment(Base):
    __tablename__='risk_assessments'
    id:Mapped[int]=mapped_column(primary_key=True)
    accession_id:Mapped[int]=mapped_column(ForeignKey('accessions.id'))
    observation_id:Mapped[int]=mapped_column(ForeignKey('observations.id'))
    status:Mapped[str]=mapped_column(String(20),default='queued')
    predicted:Mapped[str|None]=mapped_column(String(20),nullable=True)
    approved:Mapped[str|None]=mapped_column(String(20),nullable=True)
    review_note:Mapped[str]=mapped_column(String(200),default='')
    metrics:Mapped[dict]=mapped_column(JSON,default=dict)
    error:Mapped[str]=mapped_column(String(200),default='')
    # 受理时锁定的模型版本：排队瞬间写入，后续主管切换现役版本不影响在途与已结单据。
    model_version_id:Mapped[int|None]=mapped_column(ForeignKey('model_versions.id'),nullable=True)
class ModelVersion(Base):
    __tablename__='model_versions'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(40),unique=True)
    label:Mapped[str]=mapped_column(String(100))
    # active 现役版本；candidate 仅可试跑；archived 已被替换，不再接单
    status:Mapped[str]=mapped_column(String(20),default='candidate')
    params:Mapped[dict]=mapped_column(JSON)
    metrics:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    activated_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class TrialRun(Base):
    __tablename__='trial_runs'
    # 数据库层兜底：同一时刻只允许一个 running 试跑（双方言部分唯一索引）。
    __table_args__=(Index('ux_trial_running','status',unique=True,
                          postgresql_where=text("status='running'"),
                          sqlite_where=text("status='running'")),)
    id:Mapped[int]=mapped_column(primary_key=True)
    candidate_version_id:Mapped[int]=mapped_column(ForeignKey('model_versions.id'))
    baseline_version_id:Mapped[int]=mapped_column(ForeignKey('model_versions.id'))
    # running 可续跑；completed 整批核完；activated 候选已一次性切换为现役；discarded 主管放弃
    status:Mapped[str]=mapped_column(String(20),default='running')
    note:Mapped[str]=mapped_column(String(300),default='')
    started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    activated_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    # 整批完成时的高风险漏判汇总，作为主管切换闸门的留痕
    summary:Mapped[dict]=mapped_column(JSON,default=dict)
class TrialItem(Base):
    __tablename__='trial_items'
    __table_args__=(UniqueConstraint('trial_run_id','accession_id'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    trial_run_id:Mapped[int]=mapped_column(ForeignKey('trial_runs.id'))
    accession_id:Mapped[int]=mapped_column(ForeignKey('accessions.id'))
    # 发起时锁定的观测与馆员定级，试跑全程不随后续复测漂移
    observation_id:Mapped[int]=mapped_column(ForeignKey('observations.id'))
    librarian_level:Mapped[str]=mapped_column(String(20))
    baseline_prediction:Mapped[str|None]=mapped_column(String(20),nullable=True)
    candidate_prediction:Mapped[str|None]=mapped_column(String(20),nullable=True)
    # queued/running/done/failed；唯一键保证续跑重试不会为同一册重复入队或重复计数
    status:Mapped[str]=mapped_column(String(20),default='queued')
    error:Mapped[str]=mapped_column(String(200),default='')
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Treatment(Base):
    __tablename__='treatments'
    __table_args__=(CheckConstraint('estimated_cents > 0'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    accession_id:Mapped[int]=mapped_column(ForeignKey('accessions.id'))
    name:Mapped[str]=mapped_column(String(100))
    estimated_cents:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(20),default=PlanState.draft.value)
class Step(Base):
    __tablename__='steps'
    __table_args__=(UniqueConstraint('treatment_id','position'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    treatment_id:Mapped[int]=mapped_column(ForeignKey('treatments.id'))
    name:Mapped[str]=mapped_column(String(80))
    position:Mapped[int]=mapped_column(Integer)
    depends_on:Mapped[int|None]=mapped_column(ForeignKey('steps.id'),nullable=True)
    done:Mapped[bool]=mapped_column(Boolean,default=False)
    evidence:Mapped[str]=mapped_column(String(200),default='')
class Grant(Base):
    __tablename__='grants'
    __table_args__=(CheckConstraint('budget_cents >= 0 AND reserved_cents >= 0 AND spent_cents >= 0'),CheckConstraint('reserved_cents + spent_cents <= budget_cents'))
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(40),unique=True)
    name:Mapped[str]=mapped_column(String(100))
    budget_cents:Mapped[int]=mapped_column(Integer)
    reserved_cents:Mapped[int]=mapped_column(Integer,default=0)
    spent_cents:Mapped[int]=mapped_column(Integer,default=0)
class Encumbrance(Base):
    __tablename__='encumbrances'
    id:Mapped[int]=mapped_column(primary_key=True)
    treatment_id:Mapped[int]=mapped_column(ForeignKey('treatments.id'))
    grant_id:Mapped[int]=mapped_column(ForeignKey('grants.id'))
    amount_cents:Mapped[int]=mapped_column(Integer)
    actual_cents:Mapped[int|None]=mapped_column(Integer,nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='held')
class Handover(Base):
    __tablename__='handovers'
    id:Mapped[int]=mapped_column(primary_key=True)
    accession_id:Mapped[int]=mapped_column(ForeignKey('accessions.id'))
    kind:Mapped[str]=mapped_column(String(20))
    recipient:Mapped[str]=mapped_column(String(100))
    note:Mapped[str]=mapped_column(String(200))
    at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Audit(Base):
    __tablename__='audit'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(40))
    action:Mapped[str]=mapped_column(String(100))
    detail:Mapped[str]=mapped_column(String(300))
    at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
