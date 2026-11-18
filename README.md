# 古籍虫霉隔离与修复经费分配

澄文古籍所的纸本文献保护卷宗：病害登记、柜位隔离、风险复核、工序签证、专项占款和出柜借展形成一条可追溯业务链。

澄文古籍所有 12 名修复员、三处隔离柜。过去用纸质病害签和共享经费表工作，常出现满柜后重复安排、未除霉先移交、多个方案同时承诺同一笔预算。上游是入藏普查，系统承接从隔离到修复验收的环节，下游是库房保管员和借展接收单位。

## 模块和规则

1. 入藏册件：唯一馆藏号、书名、年代、纸张；追加病害观测保留历史。已出柜卷册需重新入柜才能录入病害。
2. 隔离柜：同册只允许一个在柜位置，柜位满时拒绝入柜。出柜释放位置并保存出柜时间。
3. 风险分级：Redis 排队、Python worker 执行决策树、主管复核；开工和交接只接受最新观测的复核。每张分级单受理瞬间锁定当时的现役模型版本，换版后在途与已结单据仍按受理时版本运算和展示。
4. 模型试跑与切换：主管从含高风险馆员定级的已复核卷册发起试跑，发起即锁定样本卷册、观测、馆员定级与新旧版本；候选模型在独立 Redis 队列逐册影子运算，逐册比对高风险漏判。试跑中断可续跑（running/failed 滞留册重排，已核册不重复入队、不重复计数），试跑不阻塞日常分级接单。整批核完且候选版高风险漏判未变多，主管才可一次性切换为现役；漏判变多则闸门拒绝。
5. 修复工序：方案依序建立工序依赖，资金未占用不得施工；前置工序未完成不可跳步；未施工方案撤销后可修订恢复。
6. 专项经费：预算、占用、实付分别记录；行锁保障并发不超支；撤销返还占款，核销不得超过已占金额。
7. 出柜借展：霉面积为 0、含水≤60%、最新低风险复核、工序及经费完成才准出柜；先交库房才准借展。

## 快速启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec backend python -m src.seed
```

前端 http://localhost:18230 ，后端 http://localhost:19230 ，接口文档 http://localhost:19230/docs 。数据库映射 17730，Redis 仅在内部网络开放。恰好 frontend/backend/worker/db/redis 五个服务，各有真实健康检查。初始配置 subnet 为 10.221.31.0/24，可通过环境变量调整。

| 角色 / 账号 | 密码 | 业务权限 |
|---|---|---|
| operator 修复员 | Folio@2026 | 入藏、病害复测、隔离入柜、风险排队、施工签证 |
| supervisor 修复主管 | Folio@2026 | 所有修复员动作，以及风险复核、方案、专项经费、交接和审计 |
| viewer 只读研究员 | Folio@2026 | 阅读卷宗，所有写入接口拒绝 |

演示凭据仅用于本地。JWT 有效 8 小时，使用服务端当前用户角色校验权限。

## 一天的演示剧本

1. 09:00 登录主管，打开 GB-A031《嘉庆县志》，入藏签记含水 74%、虫孔 8、霉面积 12%。
2. 09:10 查看 Q1 容量 3、现有两册，专项预算 12000 元；原缺资大修估价 15000 元。
3. 09:20 在“专项经费”批准原方案，余额不足被拒绝；去“修复工序”改为 2800 元分期方案，再占款开工。
4. 09:30 跳过“干燥除霉”签“虫孔补纸”被拒绝。按干燥除霉、虫孔补纸、平整验收依序登记施工证据。
5. 11:00 主管以不高于占款的实际费用核销；霉斑仍有记录时，出柜操作继续被拒绝。
6. 14:00 修复员追加病害复测：含水 52%、虫孔 0、霉面积 0；将最新观测提交风险分级。
7. 14:10 刷新后主管复核为低风险，进入“出柜借展”，签署移交库房，释放 Q1 一位。
8. 15:00 主管再签借展交接给澄文书展；同册重复出柜或重复借展均会拒绝。另有 GB-A032《乾隆诗稿》已核销待验收，可直接演示出柜。

### 模型试跑切换演示

1. 在“风险复核”页底部“候选模型试跑与切换”查看版本台账：`v1` 现役，`v2-draft`、`v3-refined` 候选。
2. 主管对 `v2-draft` 发起试跑：系统锁定 GB-A031、GB-A034、GB-A035 三册馆员定级为高风险的已复核卷册，worker 在独立队列逐册影子运算，页面每 3 秒刷新进度。
3. 整批核完后，`v2-draft` 在 GB-A034、GB-A035 上把高风险漏判为中风险（候选漏判 2 册，现役 0 册），“一次性切换”按钮禁用并显示闸门拦截。
4. 对 `v3-refined` 再发起一轮，漏判与现役持平（0 对 0），满足切换条件；点击切换后 `v1` 归档、`v3-refined` 成为现役，审计留痕。
5. 切换后修复员照常提交分级，新单“模型版本”列显示 `v3-refined`；切换前已在途或已结的单据仍显示并沿用其受理时版本。worker 中断后在试跑批次上点“续跑”，只重排未核册，已核册不重复计数。

## 算法与数据口径

`backend/src/algorithm.py` 以纸张含水、虫孔数、霉面积三个输入特征运行 `DecisionTreeClassifier`。固定 seed 生成 600 条专家规则合成样本，按标签分层分出 450 训练 / 150 留出；worker 实算宏 F1、混淆矩阵（行实际 / 列预测，低中高顺序）与数据 SHA256，并写入数据库和共享 artifacts 卷。worker 不在 HTTP 请求内运行，Redis 队列和心跳文件均实际存在。

模型版本通过 `PRESETS` 命名参数化：`v1` 为现役（max_depth=5/min_samples_leaf=4/random_state=31，与历史口径完全一致），`v2-draft`、`v3-refined` 是更换采样种子、标注扰动比例和树复杂度的候选。版本参数与留出指标在 `ModelVersion` 行落库且不可变；`ModelCache` 按版本 id 进程内缓存训练好的树，试跑逐册预测不重复训练。分级单 `RiskAssessment.model_version_id` 在受理时写入，worker 按该版本而非“当前现役”取模型，实现版本锁定。试跑结果只写 `TrialItem`，不产生正式分级单，也不改变任何卷册状态。

合成样本用于内部可复现检查，不代表真实文保预测效果。现场主管保留最终复核权。观测不存在、未隔离、旧观测复核、预算不足、工序不完及病害未清均是独立业务拒绝条件。后台运行失败记录 `failed` 和原因，修复输入后重新提交分级。

## 技术结构

| 层 | 实现 |
|---|---|
| 前端 | 原生 HTML / CSS / ES modules，Nginx 反代，六张业务页面 |
| 后端 | Python 3.12 / FastAPI，SQLAlchemy，Pydantic 参数与数据库双重约束 |
| 数据 | PostgreSQL 16，Redis 7 队列，独立命名卷 |
| 认证与追踪 | JWT 三角色、动作审计、请求追踪与突发请求限制中间件 |
| ML | NumPy / scikit-learn 决策树、分层留出评估 |

`backend/src/models.py` 是关系模型，`schemas.py` 是输入契约；`catalog_service.py`、`isolation_service.py`、`risk_service.py`、`trial_service.py`、`treatment_service.py`、`grant_service.py`、`handover_service.py` 分别维护各模块约束，`routes.py` 只映射权限和业务调用。建表在首次启动创建，适合独立演示库。`trial_service.py` 负责模型版本台账、试跑发起锁定、续跑重排、漏判汇总与切换闸门；`worker.py` 同时消费日常队列 `folio:risk` 与试跑队列 `folio:risk-trial`，两条队列互不阻塞。

`frontend/src/pages/` 对应六模块；`components/folio-index.js` 复用卷册索引和选择器，`ledger.js` 复用表格与表单字段，`steps.js` 绘制真实工序依赖。`api/client.js` 统一请求，`stores/workspace.js` 持有会话与卷宗，`utils/format.js` 和 `utils/forms.js` 分别处理展示和可恢复表单状态。双字体是 Noto Serif SC 与 Noto Sans SC；网络不通时浏览器使用 serif / sans-serif 回退。

共享枚举：后端 `backend/src/constants.py` 的 Role/FolioState/PlanState，分别在 seed 和模型默认值引用；前端 `frontend/src/constants/enums.js` 的 roles/folioStates/planStates 由外壳和页面引用。状态值逐一对应：operator/supervisor/viewer；registered/isolated/repair/released；draft/funded/completed/cancelled。风险值 low/medium/high 在算法与前端等级标签中一致。

## 配置与开发

`.env.example` 列出 COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、COMPOSE_SUBNET、JWT_SECRET、SEED_DEMO。`.env` 不纳入版本控制。`SEED_DEMO=true` 时启动自动导入；重复 seed 仅插入缺失自然键，不覆盖既有卷宗或重算经费。

开发后端可在 Python 3.12 虚拟环境安装 `backend/requirements.txt`，设置 DATABASE_URL、REDIS_URL、JWT_SECRET，在 backend 目录执行 `uvicorn src.app:app --reload`。原生前端无需 Node 构建，使用 Nginx `/api/` 代理后端，或重建 frontend 容器。

```sh
docker compose logs -f backend worker
docker compose down -v --remove-orphans
```

最后一条会删除本项目的演示数据卷。API、并发锁等待、seed 幂等和 Chrome 操作证据位于工作区 `test-artifacts/gb-1031/`，不放入源码。运行验收与业务独立性结论分别记录。

## 已知范围

当前单所业务，工序为有序依赖链；已开始施工的方案不能撤销，追加费用需要另行方案。借展提供放行与一次交接记录，尚未涵盖展期运输、归还登记、真实财务支付与硬件湿度采集。没有真实馆藏训练集、外部效度验证或临床式保证。初始化采用 create_all，无历史版本迁移链。

License: MIT，见 LICENSE。
