"""Editable Graphviz execution diagrams; these depict software flows, not private model reasoning."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'diagrams';OUT.mkdir(exist_ok=True)
COMMON='''graph [fontname="Noto Sans CJK SC",bgcolor="#ffffff",pad="0.35",nodesep="0.35",ranksep="0.45",splines=polyline];
node [shape=box,style="rounded,filled",fontname="Noto Sans CJK SC",fontsize=12,color="#c6d8ce",fillcolor="#edf5f0",fontcolor="#173c2e",margin="0.18,0.13"];
edge [fontname="Noto Sans CJK SC",fontsize=10,color="#659182",fontcolor="#4b6b5d",arrowsize=.7];
'''
CHARTS={
'01_architecture':('金枢｜金融产品中后台工作流', '''rankdir=TB;
a [label="业务人员：理财运营 / 发行报表 / 风控产品 / 客服"];
b [label="任务入口 + 登录身份 + 部门范围"];
c [label="Harness 固定流程\nIntent → Rewrite → Retrieval → Answer → Verify",fillcolor="#176c59",fontcolor=white];
t [label="Python Skill\n对标 · 排期 · 清洗 · Word材料"];
r [label="可信RAG\nBM25 + 向量候选 + RRF + 重排\n回查来源 / 版本 / 权限"];
m [label="Memory\n五类状态，证据与上下文分开"];
x [label="交付：结果表 / 原文依据 / 草稿 / 待确认事项"];
l [label="Loop\n反馈 → 候选 → 回放 → 灰度 → 回滚",fillcolor="#fbf0d6",color="#dbba72"];
a->b->c;c->t;c->r;c->m;t->x;r->x;m->x;x->l;l->c [label="受限执行参数，不改业务事实"];
'''),
'02_document':('PDF上传、敏感审核与可信建库','''rankdir=TB;
a [label="上传原生PDF\n上传者选择：部门 / 类型 / 主题版本 / 初始敏感级别"];
b [label="本地解析 + 规则提示\n段落识别、表格提取；扫描件待人工"];
c [label="隔离切片\n表格重复表头；保留页码、年度、单位与来源"];
d [label="独立审核人\n确认敏感级别、可访问部门、模型外发许可",fillcolor="#fbf0d6",color="#dbba72"];
e [label="退回补充\n不进入普通检索"];
f [label="BM25索引 + 获准向量化"];
g [label="向量化失败或不准外发\n仅本地BM25，标明重建状态"];
h [label="发布有效版本\n新版本就绪后切换，旧版退出默认检索"];
i [label="检索候选 → 回填权威正文 → 引用校验"];
a->b->c->d;d->e [label="退回"];d->f [label="通过"];f->g [label="降级"];f->h;g->h;h->i;
'''),
'03_loop':('反馈自进化与回滚控制失败','''rankdir=TB;
a [label="Execute / Observe\n执行Trace + 点踩 / 纠错 / 校验结果"];
b [label="Reflect / Adapt\n归因 + 受限Skill候选\n查询扩展 / top-k / 回答模板"];
c [label="配对Replay\n同一历史问题重跑基线与候选"];
d [label="审核 → 5%灰度 → 20% / 50% / 100%\n稳定哈希分组，监控处理组与对照组"];
e [label="指标劣化或人工停用\n先持久化本实例冻结标记",fillcolor="#fbf0d6",color="#dbba72"];
f [label="请求控制侧回滚"];
g [label="接口成功：远端已确认"];
h [label="接口失败：远端未确认\n本实例只用base稳定策略",fillcolor="#fbf0d6"];
i [label="重试确认 + 人工解除冻结\n不自动恢复候选流量"];
a->b->c->d;d->a [label="继续观察"];d->e->f;f->g [label="成功"];f->h [label="失败"];g->i;h->i [label="恢复后核对"];
'''),
'04_wealth':('理财产品Python Skill：复用而非重写','''rankdir=TB;
a [label="选择任务 + 传入参数\n产品 / 观察期 / 期限 / 发行频率"];
b [label="Skill注册与Schema校验\n绑定已登记Python函数"];
c [label="产品对标\n筛可比池 → 对齐净值区间\n收益、回撤、样本中位数"];
d [label="发行排期\n读取模拟日历 → 顺延检查\n保留原日期与日历版本"];
e [label="周报清洗\n数字格式 / 主键 / 缺失\n异常单独输出"];
f [label="材料生成\n复用排期函数 → 字段映射\nWord草稿 + 幂等文件名"];
g [label="资料检索补充口径\n计算不交给大模型"];
h [label="结果表 + 源文件哈希 + 待复核事项"];
a->b;b->c;b->d;b->e;d->f;c->g;e->g;f->g;g->h;
'''),
'05_service':('客服支持：依据查询与人工接续','''rankdir=TB;
a [label="问题进入服务工作流"];
b [label="身份与部门范围\n不使用未确认的账户身份"];
c [label="检索当前有效FAQ / SOP\n必要时补充问题，不猜测个案"];
d [label="有依据：原文 / 获准模型草稿"];
e [label="无依据或高风险个案\n提示人工处理，不编造业务结果",fillcolor="#fbf0d6"];
f [label="保存工单摘要与幂等键"];
g [label="工单接口确认编号 → submitted"];
h [label="无接口或超时 → pending_submission\n本地保留待办，可用同一键重试"];
i [label="用户反馈 → Loop\n知识缺项进补文档待办"];
a->b->c;c->d;c->e;d->i;e->f;f->g [label="确认"];f->h [label="未确认"];h->f [label="重试"];g->i;
'''),
'06_memory':('一个权威事实平面 + 五类记忆','''rankdir=TB;
a [label="权威事实：有效审核文档 / 原文片段 / 版本\n答案证据最终回查此处",fillcolor="#176c59",fontcolor=white];
b [label="工作记忆\n当前会话、已确认实体\n短时TTL"];
c [label="情景记忆\n原始交互事件、摘要\n原话与改写分开"];
d [label="用户语义记忆\n明确同意的低敏偏好\n可查可删除"];
e [label="组织知识记忆\n审核FAQ / 协调结论\n绑定来源与版本"];
f [label="程序性记忆\nSkill / Hook / Rule\n实验、执行参数"];
g [label="MemoryContextBuilder\n范围 → 时效 → 权威等级 → 上下文预算"];
h [label="辅助理解和改写，不把摘要或推断当官方事实"];
a->e [label="必须回查"];b->g;c->g;d->g;e->g;f->h [label="控制执行，不作事实"];g->h;
''')}
for name,(title,body) in CHARTS.items():
    source='digraph G {\n'+COMMON+f'label="{title}"; labelloc=t; fontsize=18;\n'+body+'\n}'
    p=OUT/(name+'.dot');p.write_text(source,encoding='utf-8')
    for fmt in ('svg','png'):
        subprocess.run(['dot','-T'+fmt,'-Gdpi=130',str(p),'-o',str(OUT/(name+'.'+fmt))],check=True)
print('Generated 6 editable DOT + SVG + PNG diagrams')
