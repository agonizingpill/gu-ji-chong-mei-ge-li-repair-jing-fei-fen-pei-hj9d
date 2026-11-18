from sqlalchemy import select
from .database import Session
from .models import *
from .auth import password_hash
from .algorithm import classify,train,PRESETS
from .constants import Role
def seed():
    with Session() as db:
        for item in Role:
            role=item.value
            if not db.scalar(select(User).where(User.username==role)):db.add(User(username=role,password=password_hash('Folio@2026'),role=role))
        for code,capacity in [('Q1',3),('Q2',2),('Q3',2)]:
            if not db.scalar(select(Cabinet).where(Cabinet.code==code)):db.add(Cabinet(code=code,capacity=capacity))
        if not db.scalar(select(Grant).where(Grant.code=='GF-2026')):db.add(Grant(code='GF-2026',name='古籍虫霉修复专项',budget_cents=1200000,reserved_cents=0,spent_cents=0))
        # 模型版本：v1 现役，两个候选用于试跑切换演示；参数与指标落库，版本行不可变。
        versions={}
        for code,label,status in [('v1','现役决策树 v1（深度5/叶4）','active'),
                                  ('v2-draft','候选 v2 草案（标注扰动，高风险偏松）','candidate'),
                                  ('v3-refined','候选 v3 精调（重采样，阈值更稳）','candidate')]:
            row=db.scalar(select(ModelVersion).where(ModelVersion.code==code))
            if not row:
                _,metrics=train({'id':code,'params':PRESETS[code]})
                row=ModelVersion(code=code,label=label,status=status,params=PRESETS[code],metrics=metrics)
                if status=='active':row.activated_at=now()
                db.add(row);db.flush()
            versions[code]=row
        db.flush()
        for code,title,humidity,holes,mold in [('GB-A031','嘉庆县志',74,8,12),('GB-A032','乾隆诗稿',55,3,0),('GB-A033','水经注校本',68,14,6),
                                               ('GB-A034','道光盐政册',73,3,2),('GB-A035','同治医方抄',72.5,6,4)]:
            if db.scalar(select(Accession).where(Accession.code==code)):continue
            folio=Accession(code=code,title=title,era='清代',paper='竹纸',status='isolated');db.add(folio);db.flush()
            obs=Observation(accession_id=folio.id,humidity=humidity,holes=holes,mold=mold,note='入藏病害普查');db.add(obs);db.flush()
            cabinet=db.scalar(select(Cabinet).where(Cabinet.code=='Q1' if code not in ('GB-A033','GB-A035') else Cabinet.code=='Q2'))
            db.add(Isolation(accession_id=folio.id,cabinet_id=cabinet.id))
            predicted,metrics=classify(humidity,holes,mold,{'id':'v1','params':PRESETS['v1']})
            # A034/A035 是主管现场定为高风险的已复核卷册，构成试跑样本池；
            # 其中 A034(73,3,2) 恰是 v2 草案会漏判为中风险的边界册。
            approved='low' if code=='GB-A032' else 'high' if code in ('GB-A031','GB-A034','GB-A035') else predicted
            db.add(RiskAssessment(accession_id=folio.id,observation_id=obs.id,status='reviewed',predicted=predicted,
                                  approved=approved,review_note='主管现场复核',metrics=metrics,model_version_id=versions['v1'].id))
            if code in ('GB-A034','GB-A035'):continue
            plan=Treatment(accession_id=folio.id,name='缺资大修方案' if code=='GB-A031' else '待验收方案' if code=='GB-A032' else '虫孔修补方案',estimated_cents=1500000 if code=='GB-A031' else 180000,status='completed' if code=='GB-A032' else 'draft');db.add(plan);db.flush()
            parent=None
            for i,n in enumerate(['干燥除霉','虫孔补纸','平整验收'],1):
                step=Step(treatment_id=plan.id,name=n,position=i,depends_on=parent,done=code=='GB-A032',evidence='修复员签证' if code=='GB-A032' else '');db.add(step);db.flush();parent=step.id
            if code=='GB-A032':
                grant=db.scalar(select(Grant).where(Grant.code=='GF-2026'));grant.spent_cents+=160000
                db.add(Encumbrance(treatment_id=plan.id,grant_id=grant.id,amount_cents=180000,actual_cents=160000,status='settled'))
        db.commit()
if __name__=='__main__':seed()
