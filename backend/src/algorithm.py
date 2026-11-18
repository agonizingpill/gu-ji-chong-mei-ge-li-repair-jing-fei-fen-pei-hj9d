import hashlib,threading
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score,confusion_matrix
LEVELS=['low','medium','high']
# 现役模型 v1 与试跑候选的完整参数。候选通过更换随机样本、标注扰动和树复杂度形成不同版本，
# 均在同一条专家规则合成数据线上训练，参数随 ModelVersion 行落库，试跑发起时即锁定。
PRESETS={
 'v1':{'max_depth':5,'min_samples_leaf':4,'random_state':31,'sample_seed':31,'label_noise':0.0,'high_relabel':0.0},
 'v2-draft':{'max_depth':4,'min_samples_leaf':6,'random_state':57,'sample_seed':57,'label_noise':0.05,'high_relabel':0.25},
 'v3-refined':{'max_depth':5,'min_samples_leaf':5,'random_state':71,'sample_seed':71,'label_noise':0.02,'high_relabel':0.08},
}
def _dataset(sample_seed,label_noise,high_relabel):
    rng=np.random.default_rng(sample_seed)
    x=np.column_stack([rng.uniform(30,90,600),rng.integers(0,31,600),rng.uniform(0,25,600)])
    # 专家规则构造的合成训练样本，不能替代真实馆藏外部验证。
    y=np.where((x[:,0]>=72)|(x[:,2]>=10),'high',np.where((x[:,0]>=60)|(x[:,1]>=10)|(x[:,2]>=2),'medium','low'))
    if high_relabel:
        highs=np.where(y=='high')[0]
        picked=rng.choice(highs,int(len(highs)*high_relabel),replace=False)
        y[picked]='medium'
    if label_noise:
        picked=rng.choice(np.arange(len(y)),int(len(y)*label_noise),replace=False)
        flip={'low':'medium','medium':'low','high':'medium'}
        y[picked]=np.array([flip[v] for v in y[picked]])
    return x,y
def train(version):
    """按版本参数训练并返回 (模型, 留出指标)。结果只依赖版本参数，天然可复现。"""
    p=version['params'] if 'params' in version else version
    x,y=_dataset(p['sample_seed'],p.get('label_noise',0.0),p.get('high_relabel',0.0))
    train,test=train_test_split(np.arange(len(x)),test_size=.25,random_state=p['random_state'],stratify=y)
    model=DecisionTreeClassifier(max_depth=p['max_depth'],min_samples_leaf=p['min_samples_leaf'],random_state=p['random_state']).fit(x[train],y[train])
    prediction=model.predict(x[test])
    metrics={'macro_f1':float(f1_score(y[test],prediction,average='macro')),
             'confusion_matrix':confusion_matrix(y[test],prediction,labels=LEVELS).tolist(),
             'labels':LEVELS,'train_count':len(train),'test_count':len(test),
             'seed':p['random_state'],'dataset_sha256':hashlib.sha256(x.tobytes()+y.tobytes()).hexdigest(),
             'data_source':'专家规则合成样本；留出指标仅证明内部可复现性',
             'model_params':p}
    return model,metrics
class ModelCache:
    """进程内按模型版本 id 缓存已训练树与留出指标，避免每册重复训练；版本行不可变，缓存可安全复用。"""
    def __init__(self):self._lock=threading.Lock();self._models={}
    def pair(self,version):
        key=version['id']
        with self._lock:
            if key not in self._models:self._models[key]=train(version)
            return self._models[key]
    def get(self,version):
        return self.pair(version)[0]
cache=ModelCache()
def classify(humidity,holes,mold,version=None):
    """现役分级入口：version 为 None 时沿用 v1 参数，保持与历史口径完全一致。"""
    if version is None:version={'id':'v1','params':PRESETS['v1']}
    model,metrics=cache.pair(version)
    return str(model.predict([[humidity,holes,mold]])[0]),metrics
def predict_for(version,humidity,holes,mold):
    return str(cache.get(version).predict([[humidity,holes,mold]])[0])
