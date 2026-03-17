"""Import remaining chapters (6-22) for 刘洪波雅思真经."""
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import VocabBook, Word, WordBookMembership

POS_RE = re.compile(r'(n\.|v\.|adj\.|adv\.|prep\.|int\.|num\.|det\.|ord\.|pron\.|conj\.)')

def parse_definition(raw):
    raw = raw.strip()
    if not raw:
        return [], ''
    matches = list(POS_RE.finditer(raw))
    if not matches:
        return [{'pos': '', 'meaning': raw}], ''
    defs, gparts = [], []
    for i, m in enumerate(matches):
        pos = m.group(1)
        gparts.append(pos)
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(raw)
        meaning = raw[start:end].strip().rstrip(';').strip()
        if meaning:
            defs.append({'pos': pos, 'meaning': meaning})
    return defs, ' '.join(gparts)

RAW = r"""
education	n. 教育; 教育学
primary	adj. 主要的; 小学教育的
secondary	adj. 中等教育的; 次要的
university	n. 大学
college	n. 学院
institute	n. 研究所, 学院
academy	n. 专科院校; 研究院
learn	v. 学习; 得知
study	v. n. 学习; 研究
acquire	v. 获得; 购得
knowledge	n. 知识, 学识
expertise	n. 专门知识, 专门技术
novice	n. 新手; 初学者
recruit	v. 吸收新成员
literate	adj. 有读写能力的
illiteracy	n. 文盲
numerate	adj. 识数的, 有计算能力的
problem	n. 问题, 习题
issue	n. 重要问题 v. 公布, 发出
affair	n. 事务; 事件
controversial	adj. 有争议的
puzzle	n. 难题; 谜 v. 迷惑
riddle	n. 谜语; 谜
obscure	adj. 难以理解的
instil	v. 逐步灌输
cram	v. 塞进; 临时死记硬背
emphasise	v. 强调, 着重
enhance	v. 提高, 增强
enable	v. 使能够
inspire	v. 鼓舞; 启发
motive	n. 动机, 缘由
motivate	v. 激发, 驱使
stimulate	v. 刺激; 激励
spur	n. 马刺; 鞭策 v. 鼓动
impetus	n. 推动, 促进; 动量
indulge	v. 迁就, 放任; 纵容
spoil	v. 宠坏; 弄糟
abuse	v. n. 虐待; 滥用
intelligent	adj. 聪明的; 智能的
clever	adj. 聪明的; 精明的
smart	adj. 聪明的; 敏捷的
all-round	adj. 全面的; 多才多艺的
genius	n. 天才人物; 天赋
elite	n. 精英人物
idiot	n. 白痴, 傻瓜
wisdom	n. 智慧; 学问
wit	n. 机智; 智慧
aptitude	n. 天赋; 才能
capable	adj. 有能力的
excellent	adj. 优秀的, 极好的
outstanding	adj. 优秀的; 杰出的
brilliant	adj. 聪颖的; 非常好的
prestige	n. 威望, 声望
reputation	n. 名誉, 声誉
eminent	adj. 著名的; 杰出的
notorious	adj. 臭名昭著的
esteem	v. n. 尊重, 敬重
respect	n. v. 尊敬, 敬重
diligent	adj. 勤奋的; 勤勉的
painstaking	adj. 辛苦的, 劳苦的
skill	n. 技能, 技巧
approach	v. 接近 n. 方法
scheme	n. 计划, 方案; 阴谋
headmaster	n. 男校长
principal	n. 校长 adj. 首要的
dean	n. 学院院长, 系主任
faculty	n. 系, 院; 全体成员
professor	n. 教授
scholar	n. 学者
scientist	n. 科学家
mentor	n. 导师; 顾问
tutor	n. 家庭教师; 导师
lecturer	n. 讲师
assistant	n. 助理, 助手
candidate	n. 候选人; 考生
degree	n. 学位; 程度
qualify	v. 具备资格
certify	v. 证明; 颁发证书
license	n. 执照, 许可证
permit	n. 许可证 v. 允许
diploma	n. 毕业文凭
diplomat	n. 外交官
ambassador	n. 大使
pupil	n. 小学生; 瞳孔
graduate	n. 毕业生 v. 毕业
ceremony	n. 典礼; 礼节
bachelor	n. 单身汉; 学士
master	n. 大师; 硕士 v. 精通
doctor	n. 博士; 医生
fresher	n. 一年级新生
sophomore	n. 二年级学生
junior	n. 三年级学生 adj. 级别较低的
senior	n. 毕业班学生 adj. 级别高的
alumni	n. 毕业生, 校友
campus	n. 校园, 校区
orientation	n. 情况介绍; 方向
platform	n. 平台; 讲台
coed	adj. 男女同校的
register	v. 登记, 注册
roster	n. 花名册; 执勤表
enrol	v. 登记; 注册; 招收
matriculation	n. 录取入学
accommodation	n. 住处; 食宿
dorm	n. 宿舍
dining hall	n. 食堂
canteen	n. 食堂; 水壶
laboratory	n. 实验室
experiment	n. 实验; 试验
data	n. 数据
quantity	n. 数量
quality	n. 质量
library	n. 图书馆
literature	n. 文学; 文献
article	n. 文章; 论文
author	n. 作者, 作家
tale	n. 故事, 传说
fiction	n. 小说; 虚构
story	n. 故事, 小说
diary	n. 日记
poetry	n. 诗歌; 诗集
magazine	n. 杂志, 期刊
journal	n. 日报; 杂志; 日志
coverage	n. 新闻报道; 覆盖范围
bibliography	n. 参考书目
encyclopedia	n. 百科全书
biography	n. 传记
documentary	n. 纪录片 adj. 纪录的
series	n. 一系列; 连续
record	n. 记录; 履历
file	n. 档案; 文件 v. 归档
profile	n. 概述; 人物简介
draft	n. 草稿 v. 起草
sketch	n. 概略; 草图 v. 速写
brochure	n. 小册子
manual	n. 使用手册 adj. 手工的
frame	n. 框架; 眼镜框
index	n. 指数; 索引
catalogue	n. 目录
category	n. 种类, 类别
inventory	n. 库存; 详细目录
content	n. 内容; 含量 adj. 满足的
context	n. 上下文; 背景
list	n. 列表, 目录 v. 列举
chapter	n. 章; 重要时期
volume	n. 体积; 一卷
reel	n. 卷轴
subject	n. 科目; 主题
object	n. 物体; 目标 v. 反对
major	n. 主修科目 v. 主修 adj. 主要的
minor	n. 辅修科目 adj. 不严重的
sociology	n. 社会学
politics	n. 政治学
economics	n. 经济学
marketing	n. 市场营销
accounting	n. 会计
audit	n. 审计 v. 审核; 旁听
statistics	n. 统计学
psychology	n. 心理学
philosophy	n. 哲学
logic	n. 逻辑; 逻辑学
biology	n. 生物学
physics	n. 物理学
chemistry	n. 化学
agriculture	n. 农业
logistics	n. 物流; 后勤
geography	n. 地理学
history	n. 历史
engineering	n. 工程学
mechanics	n. 力学; 机械学
electronics	n. 电子学
maths	n. 数学
arithmetic	n. 算数
geometry	n. 几何学
algebra	n. 代数学
calculus	n. 微积分
plus	prep. 加上 adj. 正数的
sum	n. 总数; 金额
total	adj. 总的 n. 总数
merge	v. 合并
equation	n. 方程式; 平衡
identical	adj. 同一的
minus	adj. 负的 prep. 减去
subtract	v. 减去; 扣除
multiply	v. 乘; 成倍增加
divide	v. 除以
dividend	n. 被除数; 股息
remainder	n. 余数; 剩余部分
rational	adj. 理性的; 有理的
parameter	n. 参数
variable	n. 变量 adj. 易变的
even	adj. 偶数的; 均匀的 adv. 甚至
odd	adj. 奇数的; 古怪的
mean	n. 平均数 v. 意思是
double	adj. 两倍的 v. 加倍
triple	adj. 三倍的 v. 增至三倍
quadruple	adj. 四倍的 v. 成四倍
multiple	n. 倍数 adj. 多样的
maximum	n. 最大值
minimum	n. 最小值
approximately	adv. 大约
chart	n. 图表
graph	n. 图表
diagram	n. 图表
table	n. 表格; 桌子
matrix	n. 矩阵; 模型
rectangle	n. 长方形, 矩形
cube	n. 立方体; 三次幂
angle	n. 角度; 角
triangle	n. 三角形
diagonal	adj. 对角线的 n. 对角线
straight	adj. 直的
circle	n. 圆
round	adj. 圆的 n. 一轮
dot	n. 点, 圆点
sphere	n. 球体; 范围, 领域
cone	n. 圆锥体
extent	n. 广度; 程度
width	n. 宽度
length	n. 长度
decimal	adj. 小数的 n. 小数
per cent	n. 百分比
proportion	n. 比例
rate	n. 比率, 速度
ratio	n. 比率
fraction	n. 分数; 小部分
scale	n. 规模; 比例尺 v. 攀登
ounce	n. 盎司; 少量
density	n. 密度; 浓度
Fahrenheit	adj. 华氏的
mercury	n. 水银; 水星
battery	n. 电池
volt	n. 伏特
radiate	v. 辐射, 发散
emit	v. 散发; 发出
transparent	adj. 透明的
hollow	adj. 空心的 v. 挖空
ozone	n. 臭氧
gravity	n. 重力; 引力
friction	n. 摩擦; 不和
eccentric	adj. 古怪的
displace	v. 替换; 移动
boil	v. 煮沸, 沸腾
melt	v. 融化; 熔化
dissolve	v. 溶解; 解散
rust	n. 锈 v. 生锈
ferment	n. 发酵 v. 发酵
dilute	v. 稀释 adj. 稀释的
acid	n. 酸 adj. 尖酸的
noxious	adj. 有害的, 有毒的
static	adj. 静态的
inert	adj. 迟钝的; 惰性的
inherent	adj. 内在的, 固有的
formula	n. 公式; 配方
component	n. 组成部分
compose	v. 构成; 创作
mixture	n. 混合物
blend	v. 混合 n. 混合物
theory	n. 理论; 学说
empirical	adj. 经验主义的
practical	adj. 实际的; 有用的
doctrine	n. 学说; 教义
principle	n. 原则; 原理
discipline	n. 纪律; 训练
term	n. 学期; 术语
semester	n. 学期
timetable	n. 时间表; 课程表
schedule	n. 日程安排; 时刻表
deadline	n. 截止日期
course	n. 课程
lesson	n. 一堂课; 教训
curriculum	n. 全部课程
seminar	n. 研讨会
forum	n. 论坛, 讨论会
syllabus	n. 教学大纲
system	n. 系统; 制度
rudimentary	adj. 基本的, 粗浅的
basic	adj. 基本的, 基础的
fundamental	adj. 基础的; 根本的
elementary	adj. 基本的; 初级的
profound	adj. 深刻的
compulsory	adj. 强制的; 义务的
prerequisite	n. 必备条件 adj. 必备的
selective	adj. 选择性的
elective	adj. 选修的 n. 选修科目
assignment	n. 作业, 任务
submit	v. 提交; 服从
preview	n. 预习 v. 预先观看
review	n. v. 复习
revise	v. 修订, 修改
inspect	v. 检查; 检阅
consult	v. 咨询; 查阅
skim	v. 略读; 浏览
scan	v. 浏览; 扫描
scrutinise	v. 详细检查
recite	v. 背诵, 朗诵
dictate	v. 口述; 命令
examination	n. 考试; 细查
test	n. v. 试验, 检验
quiz	n. 小测验
presentation	n. 陈述; 演出
plagiarise	v. 抄袭, 剽窃
copy	v. 复制 n. 复制品
print	v. 打印
thesis	n. 论文
essay	n. 短文; 论说文
paper	n. 纸; 论文
dissertation	n. 学位论文
project	n. 项目; 工程
heading	n. 标题
outset	n. 开端
outline	n. 概要; 大纲
point	n. 要点; 观点
gist	n. 要点; 主旨
opinion	n. 看法; 意见
introduce	v. 介绍; 引进
reference	n. 参考; 推荐函
cite	v. 引用
elicit	v. 引出; 探出
quote	v. 引用; 报价
extract	n. 摘录 v. 提取
abstract	n. 摘要 adj. 抽象的
summary	n. 摘要, 概要
assume	v. 假设; 料想
presume	v. 假定, 设想
suppose	v. 假定, 认为
hypothesis	n. 假设, 假说
postulate	v. n. 假定
speculate	v. 推测
predict	v. 预言; 预测
perceive	v. 感知, 察觉
detect	v. 察觉; 侦察出
discern	v. 察觉出; 分辨出
recognize	v. 认识, 辨认出
conscious	adj. 意识到的; 有知觉的
reckon	v. 估计; 认为
deem	v. 认为, 相信
imply	v. 暗指, 意味着
deliberate	v. 深思熟虑 adj. 审慎的
represent	v. 代表; 象征
insist	v. 坚持
persist	v. 坚持; 持续存在
understand	v. 理解
comprehend	v. 理解, 领悟
analyse	v. 分析
diagnose	v. 诊断
infer	v. 推断, 推理
deduce	v. 推断; 演绎
conclude	v. 得出结论; 结束
analogy	n. 类比
compare	v. 比较
contrast	n. 对比; 差异
overlap	v. 重叠; 部分相同
contradiction	n. 矛盾; 反驳
disagree	v. 不同意
differ	v. 不同, 相异
diverse	adj. 多种多样的
nuance	n. 细微差别
inductive	adj. 归纳的
detail	n. 细节
thorough	adj. 彻底的, 详尽的
example	n. 例子; 榜样
instance	n. 实例; 情况
confirm	v. 证实; 确认
demonstrate	v. 证明, 示范
illustrate	v. 说明; 加插图
manifest	v. 显示, 表明
prove	v. 证明
determine	v. 决定; 查明
decide	v. 决定
resolve	v. 决心; 解决
survey	n. 调查 v. 调查
research	n. 调查; 探索
observe	v. 观察, 注意到
inquire	v. 询问; 调查
query	n. 疑问 v. 询问
questionnaire	n. 调查问卷
achieve	v. 实现, 达到
accomplish	v. 完成
attain	v. 获得; 达到
credit	n. 学分; 信任
score	n. 得分, 成绩
mark	n. 分数 v. 给…打分
grade	v. 给…分等级 n. 等级
rank	n. 等级 v. 评级
row	n. 一排, 一行
queue	n. 队伍 v. 排队
grant	v. 授予; 承认
praise	n. 赞美 v. 赞扬
appreciate	v. 赏识; 感激
feedback	n. 反馈
underestimate	v. 低估
overestimate	v. 高估
apply	v. 申请; 应用
fellowship	n. 研究生奖学金
scholarship	n. 奖学金; 学问
reward	n. 报答 v. 报答
award	n. 奖; 奖品
prize	n. 奖赏 v. 珍视
fee	n. 费用
technology	n. 技术
technique	n. 技术, 技巧
polytechnic	n. 理工学院
engineer	n. 工程师
mechanic	n. 技工
advance	n. v. 发展; 前进
innovate	v. 创新, 改革
breakthrough	n. 突破
gizmo	n. 小发明; 小装置
patent	n. 专利 v. 得到专利
devise	v. 设计, 发明
invent	v. 发明, 创造
discover	v. 发现
disclose	v. 揭露, 透露
reveal	v. 揭示; 透露
uncover	v. 揭露, 发现
expose	v. 揭发; 使暴露
domain	n. 领域; 领土
realm	n. 领域
foundation	n. 基础; 基金会
specialise	v. 专门从事
concentrate	v. 集中; 使浓缩
focus	v. 集中 n. 焦点
utilise	v. 利用
usage	n. 使用; 用法
tester	n. 测试仪
device	n. 装置, 设备
appliance	n. 器具
facility	n. 设备; 便利
equipment	n. 设备
instrument	n. 仪器; 工具; 乐器
tool	n. 工具
gauge	n. 测量仪器 v. 测量; 判断
measure	v. 测量 n. 措施
calculate	v. 计算
compute	v. 计算
count	v. 计算; 数数
estimate	v. 估计
assess	v. 评估
evaluate	v. 评价, 评估
accessory	n. 附件; 配件
byproduct	n. 副产品
auxiliary	adj. 辅助的; 备用的
versatile	adj. 多功能的
add	v. 添加; 附加
accumulate	v. 积累
assemble	v. 聚集; 组装
gather	v. 聚集; 采集
attach	v. 附加; 缚, 系
belong	v. 属于; 应在某处
optics	n. 光学
microscope	n. 显微镜
lens	n. 镜头; 透镜
radar	n. 雷达
echo	n. 回声 v. 发回声
sensor	n. 传感器
multimedia	n. 多媒体
network	n. 网络
browser	n. 浏览器
dial	v. 拨号
microcomputer	n. 微型计算机
laptop	n. 笔记本电脑
software	n. 软件
keyboard	n. 键盘
screen	n. 屏幕 v. 遮蔽
loudspeaker	n. 扬声器
microphone	n. 话筒, 麦克风
cassette	n. 盒式磁带
tape	n. 胶带; 磁带
binary	adj. 二进制的
digital	adj. 数字的
wireless	adj. 无线的
high-definition	adj. 高分辨率的
audio	adj. 声音的, 音频的
vision	n. 视觉
fantasy	n. 幻想
science fiction	n. 科幻小说
pump	n. 泵 v. 抽
generator	n. 发电机
gear	n. 齿轮
pivot	n. 枢轴, 支点
hydraulic	adj. 水力的, 液压的
drainage	n. 排水系统
sewage	n. 污水
ventilation	n. 通风
compress	v. 压缩
condense	v. 压缩; 凝结
refine	v. 提炼, 提纯
simplify	v. 简化
purify	v. 净化
filter	v. 过滤 n. 过滤器
distil	v. 蒸馏
mode	n. 模式; 方式
prototype	n. 原型
framework	n. 框架, 结构
aspect	n. 方面
phase	n. 阶段, 时期
operate	v. 操作; 运营
facilitate	v. 促进; 使便利
transform	v. 改变形态
convert	v. 转变 n. 皈依者
alter	v. 变更, 改变
shift	v. 转移 n. 转移; 轮班
turn	v. 翻; 转 n. 机会
adapt	v. 适应; 改编
adjust	v. 调节; 改变
pinpoint	v. 精确地指出
accurate	adj. 准确的
precise	adj. 精确的
correct	adj. 正确的
error	n. 错误
mistake	n. 错误 v. 误解
flaw	n. 缺陷; 错误
wrong	adj. 错误的
fault	n. 缺点; 故障
stumble	v. 犯错误; 绊脚
contingency	n. 意外事件
circumstance	n. 情况; 环境
culture	n. 文化, 文明
civilisation	n. 文明
renaissance	n. 文艺复兴
epic	n. 史诗 adj. 宏大的
ideology	n. 意识形态
tradition	n. 传统
convention	n. 惯例; 大型会议
custom	n. 习惯; 风俗
feudalism	n. 封建主义
slavery	n. 奴隶制
ethical	adj. 伦理的, 道德的
moral	adj. 道德上的
tribe	n. 部落
aboriginal	n. 土著居民 adj. 原始的
inhabitant	n. 居民
native	adj. 本土的 n. 本地人
local	adj. 当地的 n. 当地人
exotic	adj. 外来的; 异国情调的
foreigner	n. 外国人
alien	n. 外侨; 外星人 adj. 外国的
anthropologist	n. 人类学家
humanitarian	adj. 人道主义的
heritage	n. 遗产
inherit	v. 继承; 遗传获得
antique	n. 古董 adj. 古董的
archaeology	n. 考古学
excavate	v. 挖掘, 发掘
museum	n. 博物馆
pottery	n. 陶器
engrave	v. 雕刻
decorate	v. 装饰
religion	n. 宗教
ritual	n. 仪式
etiquette	n. 礼仪, 礼节
belief	n. 信念; 信仰
soul	n. 灵魂; 心灵
spirit	n. 精神, 心灵
sacred	adj. 神圣的; 宗教的
hallowed	adj. 神圣的
holy	adj. 神圣的; 虔诚的
Pope	n. 教皇
bishop	n. 主教
missionary	n. 传教士
priest	n. 牧师; 神父
Bible	n. 圣经
church	n. 教堂
cathedral	n. 大教堂
choir	n. 唱诗班
monk	n. 修道士, 僧侣
temple	n. 寺院, 庙宇
pagoda	n. 佛塔
empire	n. 帝国
imperial	adj. 帝国的
royal	adj. 皇家的
dynasty	n. 朝代
chronology	n. 年表; 年代学
emperor	n. 皇帝
king	n. 国王
queen	n. 女王; 王后
prince	n. 王子; 亲王
princess	n. 公主; 王妃
majesty	n. 威严; 陛下
nobility	n. 贵族; 高尚的品质
lord	n. 贵族; 领主
knight	n. 骑士 v. 封爵士
guardian	n. 保护者; 监护人
nostalgia	n. 思乡之情; 怀旧
homesick	adj. 思乡的
celebrity	n. 名人
status	n. 地位, 身份
background	n. 背景; 经历
experience	n. 经验; 经历
anecdote	n. 轶事, 趣闻
accident	n. 事故; 意外
incident	n. 事件; 冲突
thrive	v. 繁荣; 茁壮成长
prosperity	n. 繁荣; 兴旺
setback	n. 挫折, 阻碍
adversity	n. 逆境
language	n. 语言
symbol	n. 象征; 符号
sign	n. 符号; 征兆 v. 签名
gesture	n. 手势, 姿势
handwriting	n. 手写; 书法
pictograph	n. 象形文字
wedge	n. 楔子; 楔形文字
knot	n. 结; 节子
linguistics	n. 语言学
semantic	adj. 语义的
syntax	n. 句法
grammar	n. 语法
phonetics	n. 语音学
pronounce	v. 发音; 宣布
intonation	n. 语调, 声调
inflection	n. 变音; 语调变化
dialect	n. 方言, 地方话
accent	n. 重音; 口音
utterance	n. 话语
oral	adj. 口头的
verbal	adj. 言语的; 口头的
syllable	n. 音节
phoneme	n. 音位
vowel	n. 元音
consonant	n. 辅音
alphabet	n. 字母表
logogram	n. 词符
vocabulary	n. 词汇; 词典
dictionary	n. 词典
idiom	n. 习语; 方言
phrase	n. 短语
clause	n. 从句; 条款
expression	n. 词语; 表达; 表情
tense	n. 时态 adj. 紧张的
prefix	n. 前缀
suffix	n. 后缀
abbreviation	n. 缩写形式
synonym	n. 同义词
antonym	n. 反义词
noun	n. 名词
singular	n. 单数 adj. 非凡的
plural	n. 复数 adj. 多元的
pronoun	n. 代词
verb	n. 动词
adjective	n. 形容词
adverb	n. 副词
preposition	n. 介词
conjunction	n. 连词; 结合
consistent	adj. 一致的; 连贯的
complicated	adj. 复杂的
complex	adj. 复杂的
compile	v. 编写, 编纂
version	n. 译本; 版本
translate	v. 翻译
paraphrase	v. n. 意译, 改述
interpret	v. 口译; 解释
narrate	v. 叙述
illuminate	v. 阐释; 照亮
decipher	v. 译解; 辨认
eloquence	n. 雄辩; 口才
communicate	v. 沟通, 交流
discussion	n. 讨论
brainstorm	n. 头脑风暴 v. 集思广益
debate	v. n. 辩论
commentary	n. 评论; 实况报道
negotiate	v. 谈判, 协商
contention	n. 争论; 观点
"""


class Command(BaseCommand):
    help = 'Import chapters 5-8 for 刘洪波雅思真经'

    def handle(self, *args, **options):
        entries = []
        for line in RAW.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t', 1)
            if len(parts) < 2:
                continue
            w, d = parts[0].strip(), parts[1].strip()
            if w and d:
                entries.append((w, d))

        self.stdout.write(f'Parsed {len(entries)} words')

        with transaction.atomic():
            book = VocabBook.objects.get(name='刘洪波雅思真经')
            existing_max = book.memberships.count()
            new_words = 0
            new_memberships = 0

            for i, (word_text, raw_def) in enumerate(entries):
                definitions, grammar_str = parse_definition(raw_def)
                word_obj, w_created = Word.objects.get_or_create(
                    word=word_text,
                    defaults={'grammar': grammar_str, 'definitions': definitions},
                )
                if w_created:
                    new_words += 1
                _, m_created = WordBookMembership.objects.get_or_create(
                    word=word_obj, book=book,
                    defaults={'order': existing_max + i + 1},
                )
                if m_created:
                    new_memberships += 1

            book.word_count = book.memberships.count()
            book.save(update_fields=['word_count'])

        self.stdout.write(self.style.SUCCESS(
            f'Done! new_words={new_words} new_memberships={new_memberships} total={book.word_count}'
        ))
