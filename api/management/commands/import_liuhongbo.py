"""
One-shot script to create the 刘洪波雅思真经 vocab book and import all words.

Usage:
    cd backend
    python manage.py shell < api/management/commands/import_liuhongbo.py
  OR
    python manage.py import_liuhongbo
"""
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import VocabBook, Word, WordBookMembership

POS_RE = re.compile(r'(n\.|v\.|adj\.|adv\.|prep\.|int\.|num\.|det\.|ord\.|pron\.|conj\.)')

SKIP_RE = [
    re.compile(r'^Chapter', re.IGNORECASE),
    re.compile(r'^单词\s'),
    re.compile(r'^\s*$'),
]


def parse_definition(raw: str):
    raw = raw.strip()
    if not raw:
        return [], ''
    matches = list(POS_RE.finditer(raw))
    if not matches:
        return [{'pos': '', 'meaning': raw}], ''
    defs = []
    grammar_parts = []
    for i, m in enumerate(matches):
        pos = m.group(1)
        grammar_parts.append(pos)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        meaning = raw[start:end].strip().rstrip(';').strip()
        if meaning:
            defs.append({'pos': pos, 'meaning': meaning})
    return defs, ' '.join(grammar_parts)


# ── Raw word data ──────────────────────────────────────────────────────────
# Format: word<TAB>definition  (one per line)
# Lines starting with # or empty lines are skipped.
RAW = r"""
atmosphere	n. 大气层, 大气圈; 气氛
hydrosphere	n. 水圈; 大气中的水气
lithosphere	n. 岩石圈
oxygen	n. 氧气
oxide	n. 氧化物
carbon dioxide	n. 二氧化碳
hydrogen	n. 氢气
core	n. 中心, 核心; 地核
crust	n. 地壳; 外壳
mantle	n. 地幔; 斗篷, 披风 v. 覆盖
longitude	n. 经度
latitude	n. 纬度
horizon	n. 地平线; 眼界, 见识
altitude	n. 高度, 海拔
disaster	n. 灾难
mishap	n. 小灾难
catastrophic	adj. 灾难性的
calamity	n. 灾难, 不幸的事
endanger	v. 使遭受危险, 危及
jeopardise	v. 危害, 危及
destructive	adj. 破坏性的, 有害的
El Nino	n. 厄尔尼诺现象
greenhouse	n. 温室, 暖房
phenomenon	n. 现象
pebble	n. 鹅卵石
magnet	n. 磁铁, 吸铁石
ore	n. 矿石; 矿
mineral	n. 矿物, 矿物质; 矿产
marble	n. 大理石; 弹球
quartz	n. 石英
granite	n. 花岗岩
gust	n. 一阵狂风; 迸发
breeze	n. 微风, 和风
monsoon	n. 季风; 雨季
gale	n. 大风
hurricane	n. 飓风; 暴风
tornado	n. 龙卷风
typhoon	n. 台风
volcano	n. 火山
erupt	v. 爆发, 喷发; 突然出现
magma	n. 岩浆
thermodynamic	adj. 热力的; 热力学的
smog	n. 烟雾, 雾霾
fume	n. 烟, 气体 v. 冒烟, 发怒
mist	n. 薄雾; 水汽
tsunami	n. 海啸
drought	n. 干旱, 旱灾
flooding	n. 洪水泛滥
torrent	n. 激流, 洪流
earthquake	n. 地震
seismic	adj. 地震的, 地震引起的
avalanche	n. 雪崩
terrain	n. 地形
landscape	n. 风景, 地貌 v. 对…进行景观美化
continent	n. 大陆; 洲
cave	n. 洞穴, 山洞
cliff	n. 悬崖, 峭壁
glacier	n. 冰川, 冰河
swamp	n. 沼泽, 湿地
delta	n. 三角洲
plain	n. 平原 adj. 简朴的, 明白的
plateau	n. 高原
oasis	n. 绿洲; 宜人之地
globe	n. 球体; 地球仪; 地球
hemisphere	n. 半球
equator	n. 赤道
arctic	adj. 极冷的; 北极的 n. 北极地区
Antarctic	adj. 南极的 n. 南极地区, 南极洲
pole	n. 极; 截然相反的两极之一
polar	adj. 极地的; 对立的
axis	n. 轴, 轴线
deteriorate	v. 变坏, 恶化
aggravate	v. 加重, 加剧, 使恶化
degrade	v. 降解; 使恶化, 使退化
upgrade	v. 使升级; 提高, 改善
erode	v. 侵蚀, 腐蚀
Mediterranean	adj. 地中海的 n. 地中海
Atlantic	adj. 大西洋的 n. 大西洋
pacific	adj. 平静的, 和平的; 太平洋的 n. 太平洋
ocean	n. 海洋; 洋
marine	adj. 海生的, 海洋的; 海事的 n. 水兵
navigation	n. 航行; 航海
gulf	n. 海湾
beach	n. 海滩, 河滩
coast	n. 海岸, 海滨
shore	n. 岸, 滨
tide	n. 趋势, 潮流; 潮汐
current	adj. 当前的; 流通的 n. 水流; 电流; 趋向
brook	n. 小河, 溪
stream	n. 小河, 溪; 流 v. 流动
source	n. 河的源头; 根源
shallow	adj. 浅的; 肤浅的
superficial	adj. 表皮的, 表层的
flat	adj. 平坦的; 扁平的; 单调的
smooth	adj. 光滑的; 平稳的; 流畅的
rough	adj. 粗糙的; 粗略的
sandy	adj. 铺满沙的; 含沙的
stony	adj. 多石的; 石头的
vertical	adj. 垂直的, 直立的
steep	adj. 陡峭的, 垂直的
parallel	n. 平行线; 相似之物 adj. 平行的 v. 与…相似
narrow	adj. 狭窄的; 有局限的 n. 海峡 v. 变窄
Oceania	n. 大洋洲
mainland	n. 大陆, 本土
peninsula	n. 半岛
climate	n. 气候; 风气, 思潮
weather	n. 天气, 气象
meteorology	n. 气象学
mild	adj. 温和的; 不严重的
heating	n. 供暖; 暖气装置
moderate	adj. 适度的; 温和的; 中等的 v. 缓和
warm	adj. 温暖的 v. 变暖
thermal	adj. 热量的
tropics	n. 热带地区
arid	adj. 干燥的, 干旱的; 枯燥的
moist	adj. 潮湿的, 湿润的
damp	adj. 潮湿的, 湿气重的
humid	adj. 潮湿的, 湿热的
snowy	adj. 下雪多的, 被雪覆盖的
frost	n. 霜; 霜冻; 严寒
hail	n. 雹, 冰雹 v. 赞扬; 下雹
thaw	v. 解冻, 融解 n. 解冻时期
chill	n. 寒冷; 害怕 v. 变冷; 使恐惧
freeze	v. 结冰 n. 霜冻; 严寒期
frigid	adj. 寒冷的
tremble	v. n. 战栗, 颤抖
shiver	v. 颤抖, 哆嗦
thunder	n. 雷; 雷声 v. 打雷
lightning	n. 闪电 adj. 闪电般的
stormy	adj. 有暴风雨的; 争吵激烈的
downpour	n. 倾盆大雨
rainfall	n. 降雨量
sprinkle	v. 撒, 洒; 下小雨 n. 少量
rainbow	n. 彩虹
shower	n. 阵雨; 淋浴
Celsius	adj. 摄氏的 n. 摄氏温度
temperature	n. 气温; 体温; 温度
forecast	n. 预测, 预报 v. 预测
peak	n. 山峰; 顶点 v. 达到最大值
mount	v. 爬上, 登上; 渐渐增加 n. 山
mountain	n. 山, 山岳, 高山
range	n. 山脉; 范围
ridge	n. 山脊, 山脉 v. 使隆起
slope	n. 山坡; 斜坡 v. 倾斜
valley	n. 山谷, 溪谷
hillside	n. 山腰, 山坡
overlook	v. 俯瞰; 未注意到
southern	adj. 南部的; 南方的
southeast	n. 东南方 adj. 东南方的
southwest	n. 西南方 adj. 西南方的
northeast	n. 东北 adj. 东北方的
northwest	n. 西北方 adj. 西北方的
eastern	adj. 东部的; 东方的
oriental	adj. 东方的
inevitable	adj. 必然的, 不可避免的
irreversible	adj. 不可逆转的; 不可挽回的
irregularly	adv. 不规则地; 不合常规地
inappropriate	adj. 不合适的
abnormal	adj. 不正常的, 反常的
sediment	n. 沉淀物; 沉积物
silt	n. 淤泥, 泥沙 v. 淤塞
muddy	adj. 泥泞的; 浑浊的
clay	n. 黏土, 陶土
dirt	n. 污垢, 灰尘; 泥土
rural	adj. 农村的, 乡村的
suburb	n. 郊区, 郊外
outskirts	n. 郊区, 市郊
remote	adj. 遥远的; 偏僻的; 疏远的
desolate	adj. 荒凉的
distant	adj. 疏远的; 遥远的
adjacent	adj. 邻近的, 毗连的
toxic	adj. 有毒的
pollution	n. 污染
pollutant	n. 污染物质
contaminate	v. 污染, 弄脏
geology	n. 地质学; 地质状况
border	n. 边界; 镶边 v. 毗邻
margin	n. 边缘; 页面空白; 余地
fringe	n. 边缘; 刘海 adj. 次要的
plate	n. 盘子; 板块
debris	n. 碎片, 残骸
crack	v. 破裂 n. 裂缝
gap	n. 缺口, 裂缝; 差距; 空白
splendid	adj. 极好的; 壮观的
grand	adj. 宏大的; 豪华的; 宏伟的
magnificent	adj. 壮丽的, 宏伟的
super	adj. 超级的, 极好的
interesting	adj. 有趣的; 引人入胜的
dramatic	adj. 戏剧的; 引人注目的
wilderness	n. 荒野
desert	n. 沙漠
deforest	v. 毁掉森林
barren	adj. 贫瘠的, 荒芜的; 不结果实的
fertile	adj. 肥沃的, 富饶的
fertilise	v. 施肥于
solar	adj. 太阳的, 日光的
lunar	adj. 月亮的, 月球的
calendar	n. 日历; 历法
sunrise	n. 日出
sunset	n. 日落
eclipse	n. 日食; 月食
dusk	n. 黄昏, 傍晚
heaven	n. 天堂; 天空
paradise	n. 天堂; 乐园
sunshine	n. 阳光, 日光
shade	n. 阴影; 背阴处 v. 遮挡光线
shadow	n. 影子, 阴影
vapour	n. 蒸汽; 水汽
evaporate	v. 蒸发; 消失
circulate	v. 循环, 流通; 传播
precipitate	v. 凝结; 沉淀
reservoir	n. 水库, 蓄水池
waterfall	n. 瀑布
fountain	n. 喷泉; 源泉
spring	n. 春天; 泉水; 弹簧
dew	n. 露水
pour	v. 倾泻; 倒; 倾盆而下
drain	v. 排空; 流出 n. 耗竭
drip	v. 滴出 n. 水滴
drown	v. 淹死; 浸泡
blow	v. 吹; 吹动 n. 打击
puff	v. 喷出; 喘息 n. 一股
gush	v. n. 涌出
dense	adj. 密集的; 稠密的
intensity	n. 强度; 强烈
intensive	adj. 加强的, 集中的, 密集的
emerge	v. 浮现, 露出; 暴露
flash	v. 闪光; 闪现 n. 闪光
float	v. 飘浮; 漂浮
environment	n. 自然环境; 周围状况
surrounding	adj. 周围的, 附近的
condition	n. 条件; 情况, 状态
situation	n. 情况, 处境, 形势
nature	n. 大自然; 本性; 性质
natural	adj. 自然的; 天然的
artificial	adj. 人造的
synthetic	adj. 人造的, 合成的 n. 合成物
petrol	n. 汽油
gas	n. 气体; 汽油
gasoline	n. 汽油
petroleum	n. 石油
photosynthesis	n. 光合作用
respire	v. 呼吸
dioxide	n. 二氧化物
vegetation	n. 植物, 草木
herb	n. 药草; 香草
perennial	n. 多年生植物 adj. 长期的, 持久的
botany	n. 植物学
ecology	n. 生态学; 生态
ecosystem	n. 生态系统
eco-friendly	adj. 对生态环境友好的
horticulture	n. 园艺学; 园艺
organism	n. 有机体, 生物
genetics	n. 遗传学
mutation	n. 变异, 突变
variation	n. 变种; 变异
diversity	n. 多样性, 多元性
hybridisation	n. 杂交
classify	v. 分类
reproduce	v. 繁殖
evolve	v. 进化; 逐渐形成; 发展
fluctuate	v. 波动, 起伏
reclaim	v. 开垦, 利用
cultivate	v. 耕作, 种植; 培养
sow	v. 播种
harvest	v. 收割 n. 收获; 收成
pluck	v. 摘
pick	v. 摘
yield	n. 产量 v. 出产; 屈服
rear	v. 培养, 饲养 n. 后部
arable	adj. 适于耕种的
plough	n. 犁 v. 耕地
spade	n. 铁锹, 铲子
rake	n. 耙子 v. 耙; 搜索
stack	n. 堆, 垛 v. 堆积
heap	n. 堆
bundle	n. 捆, 包, 束
bunch	n. 一束, 一串
vase	n. 花瓶
sunlight	n. 阳光
short-day	adj. 短日照的
shade-tolerant	adj. 耐阴的
fungus	n. 真菌
mould	n. 霉菌 v. 发霉
pollen	n. 花粉 v. 授粉
germinate	v. 发芽; 开始生长
seed	n. 种子; 萌芽
burgeon	n. 嫩枝, 新芽 v. 急速增长; 发芽
bud	n. 芽, 苞
flower	n. 花朵 v. 开花
blossom	n. 花朵 v. 开花
bloom	n. 花朵 v. 开花
scent	n. 气味; 香味 v. 使具有香味
aromatic	adj. 芳香的
ripen	v. 成熟
fruit	v. 结果实 n. 水果; 果实
wither	v. 枯萎
decompose	v. 分解; 腐烂
rot	v. 腐烂 n. 腐烂
decay	v. 腐烂
stale	adj. 不新鲜的; 陈腐的
rainforest	n. 雨林
jungle	n. 丛林, 密林
plantation	n. 种植园; 栽植
field	n. 原野; 场地; 田地
terrace	n. 梯田; 台阶; 阳台
timber	n. 木材, 木料; 林木
charcoal	n. 木炭
log	n. 原木; 日志
logo	n. 标识, 标志
forestry	n. 林学; 林业
branch	n. 树枝; 分支机构
trunk	n. 树干; 躯干; 大箱子
bough	n. 大树枝
root	n. 根 v. 生根
hay	n. 干草
straw	n. 稻草, 麦秆; 吸管
reed	n. 芦苇
thorn	n. 刺; 棘刺; 带刺的植物
weed	n. 杂草 v. 除杂草
grass	n. 草; 草地
meadow	n. 草地; 牧场
lawn	n. 草地, 草坪
olive	n. 橄榄; 橄榄树
pine	n. 松树; 松木
vine	n. 葡萄藤
violet	n. 紫罗兰
tulip	n. 郁金香
mint	n. 薄荷; 铸币厂 v. 铸造
reef	n. 礁, 暗礁
alga	n. 海藻; 水藻
enzyme	n. 酶
catalyst	n. 催化剂; 促进因素
release	v. n. 释放; 发布
emission	n. 排放, 散发; 排放物
absorb	v. 吸收; 吸引注意力
circulation	n. 流通; 循环
exceed	v. 超过; 超越
uptake	v. 摄入; 领会
nutrient	n. 营养物质
energy	n. 精力; 能量; 能源
surroundings	n. 周围环境
mechanism	n. 构造; 机制
counterbalance	n. 平衡作用的事物 v. 抵消
protect	v. 保护
preserve	v. 保护; 保存
conservation	n. 保护; 保存
bush fire	n. 林区大火
extinguish	v. 熄灭, 扑灭
destruct	v. 自毁; 破坏
ruin	v. 毁坏 n. 废墟
perish	v. 毁灭, 消亡; 腐烂
demolish	v. 拆除; 毁坏
infringe	v. 侵犯; 违反
undermine	v. 破坏; 逐渐削弱
extinction	n. 灭绝, 消亡
pattern	n. 模式; 式样; 图案
outcome	n. 结果
impact	n. 影响 v. 有影响
seasonal	adj. 季节性的
experimental	adj. 实验的
favourable	adj. 有利的; 赞成的
productive	adj. 多产的; 富有成效的
effective	adj. 有效的
efficient	adj. 效率高的
considerable	adj. 相当多的
massive	adj. 巨大的, 大规模的
immense	adj. 巨大的; 极大的
maximal	adj. 最大的
minimal	adj. 最小的; 极小的
optimal	adj. 最优的; 最佳的
biologist	n. 生物学家
zoologist	n. 动物学家
ecologist	n. 生态学家
botanist	n. 植物学家
mammal	n. 哺乳动物
primate	n. 灵长目动物
vertebrate	n. 脊椎动物
reptile	n. 爬行动物
amphibian	n. 两栖动物 adj. 两栖的
carnivore	n. 食肉动物
herbivore	n. 食草动物
creature	n. 生物, 动物
wildlife	n. 野生动物
fauna	n. 动物群
flora	n. 植物群
species	n. 物种
flock	n. 鸟群; 兽群 v. 群聚
herd	n. 兽群; 畜群
swarm	n. 蜂群, 一大群
throng	n. 人群 v. 群集
crowd	n. 人群; 观众
beast	n. 野兽
brute	n. 畜生; 残暴的人
cruel	adj. 残酷的; 残忍的
originate	v. 发源; 创始
derive	v. 起源于; 获得
stem	v. 起源于 n. 茎, 梗
ancestor	n. 祖先
descendant	n. 后代, 后裔
offspring	n. 后代; 产物
subgroup	n. 子群, 小群
feed	v. 供养; 喂, 饲养
breed	v. 饲养; 繁殖 n. 品种
interbreed	v. 异种交配
hybridise	v. 杂交
proliferate	v. 迅速增殖; 剧增
sterility	n. 不生育; 不孕
mate	v. 交配 n. 配偶
courtship	n. 求偶
lay	v. 产卵; 放置; 铺设
hatch	v. n. 孵出; 孵化
brood	n. 一窝幼鸟 v. 孵蛋
spawn	n. 卵 v. 产卵; 引起
mature	adj. 成熟的 v. 成熟
skin	n. 皮肤; 外皮
claw	n. 爪; 钳
paw	n. 脚掌, 爪子
beak	n. 鸟喙
fin	n. 鳍
wing	n. 翅膀, 翼
plume	n. 羽毛
feather	n. 羽毛
fur	n. 皮毛; 毛皮
bristle	n. 鬃毛
curl	n. 卷发 v. 卷曲
insect	n. 昆虫
worm	n. 蠕虫
pest	n. 害虫
parasite	n. 寄生虫
spider	n. 蜘蛛
butterfly	n. 蝴蝶
mosquito	n. 蚊子
cricket	n. 蟋蟀
penguin	n. 企鹅
seal	n. 海豹; 图章 v. 密封
tortoise	n. 陆龟
turtle	n. 海龟
whale	n. 鲸鱼 v. 捕鲸
kangaroo	n. 袋鼠
camel	n. 骆驼
panda	n. 熊猫
elephant	n. 象
ivory	n. 象牙
horn	n. 角; 号
bear	n. 熊
wolf	n. 狼
dragon	n. 龙
fox	n. 狐狸
cub	n. 幼兽
calf	n. 幼牛; 幼兽
pup	n. 幼小动物
lamb	n. 小羊, 羔羊
cattle	n. 牛
ox	n. 公牛
bull	n. 公牛
buffalo	n. 水牛; 野牛
horse	n. 马
zebra	n. 斑马
donkey	n. 驴
saddle	n. 马鞍
harness	n. 马具, 挽具
falcon	n. 猎鹰
hawk	n. 鹰
eagle	n. 雕
owl	n. 猫头鹰
swallow	n. 燕子
sparrow	n. 麻雀
pigeon	n. 鸽子
crow	n. 乌鸦
swan	n. 天鹅
goose	n. 鹅; 鹅肉
cock	n. 公鸡; 雄禽
mouse	n. 老鼠
rat	n. 老鼠
squirrel	n. 松鼠
hare	n. 野兔
frog	n. 蛙
behaviour	n. 行为; 态度
bite	v. n. 咬; 叮
sting	v. 刺, 叮 n. 毒刺
bark	n. 狗叫声; 树皮 v. 狗叫
roar	n. v. 吼叫, 咆哮
rub	v. 擦, 摩擦
creep	v. 缓慢行进
crawl	v. 爬, 爬行
habitat	n. 栖息地
nest	n. 巢, 窝, 穴
hive	n. 蜂巢; 蜂箱
cell	n. 细胞; 蜂房; 牢房
cage	n. 笼子
stable	n. 马厩 adj. 稳定的
barn	n. 谷仓; 牲口棚
hedge	n. 树篱; 障碍物
barrier	n. 障碍; 屏障
bar	n. 栅栏; 条; 酒吧
anatomy	n. 解剖学; 剖析
epidemic	n. 流行病 adj. 流行性的
gene	n. 基因
germ	n. 细菌, 微生物
bacteria	n. 细菌
virus	n. 病毒
microbe	n. 微生物
metabolism	n. 新陈代谢
protein	n. 蛋白质
vitamin	n. 维生素
secrete	v. 分泌
excrete	v. 排泄; 分泌
devour	v. 吞食; 吞噬
instinct	n. 本能, 天性; 直觉
intuitive	adj. 直觉的
potential	n. 潜力 adj. 潜在的
intelligence	n. 智慧, 智力; 情报
functional	adj. 功能的; 起作用的
sensitive	adj. 灵敏的; 敏感的
flexible	adj. 可弯曲的; 灵活的
acoustic	adj. 听觉的; 声音的
optical	adj. 光学的; 视觉的
nocturnal	adj. 夜间活动的
dormant	adj. 休眠的; 冬眠的
hibernation	n. 冬眠
track	v. 追踪 n. 足迹; 轨道
trace	v. 追踪; 追溯 n. 痕迹
alternate	v. 交替, 轮流
prey	n. 猎物 v. 捕食
predator	n. 捕食者
victim	n. 受害者; 牺牲者
captive	n. 俘虏 adj. 被监禁的
defensive	adj. 防御性的
undergo	v. 经历; 承受
suffer	v. 受苦; 忍受
vulnerable	adj. 脆弱的; 易受伤的
subsistence	n. 勉强维持生活; 生计
exist	v. 存在; 生存
exterminate	v. 消灭, 根除
tame	v. 驯服 adj. 驯服的
keeper	n. 看守人; 饲养员
shepherd	n. 牧羊人
galaxy	n. 星系; 银河系
cosmos	n. 宇宙
universe	n. 宇宙; 万物
interstellar	adj. 星际的
terrestrial	adj. 陆地的; 地球的
celestial	adj. 天上的
astronomy	n. 天文学
astrology	n. 占星术
astronaut	n. 宇航员
comet	n. 彗星
meteorite	n. 陨石
crater	n. 坑
dust	n. 尘土, 灰尘
ash	n. 灰烬
envelope	n. 外层; 信封
chunk	n. 厚块
spacecraft	n. 宇宙飞船
spaceship	n. 宇宙飞船
probe	n. 太空探测器; 调查
module	n. 模块; 组件; 舱
propulsion	n. 推进力
pressure	n. 压力
dynamics	n. 动力学; 动态
motion	n. 动作; 移动
vent	n. 排气口 v. 排放; 发泄
tail	n. 尾部
curve	n. 曲线, 弧线
exploration	n. 探索
expedition	n. 探险, 远征
flyby	n. 飞掠
observatory	n. 天文台
telescope	n. 望远镜
spectacle	n. 奇观, 壮观景象
orbit	n. 轨道
ecliptic	n. 黄道
diameter	n. 直径
radius	n. 半径
substance	n. 物质; 实质
composition	n. 成分, 构成; 作品
compound	n. 混合物; 化合物 adj. 复合的 v. 混合
fossil	n. 化石
sample	n. 样品, 样本
specimen	n. 样本, 样品
particle	n. 颗粒, 微粒
molecule	n. 分子
atom	n. 原子
ion	n. 离子
electron	n. 电子
quantum	n. 量子
liquid	n. 液体 adj. 液态的
fluid	n. 液体, 流体 adj. 流动的
solid	n. 固体
synthesise	v. 合成; 综合
formation	n. 形成
method	n. 方法
spectrum	n. 光谱; 范围
dimension	n. 范围; 维度
frequency	n. 频率
signal	n. 信号
antenna	n. 天线
circuit	n. 线路, 电路
refraction	n. 折射
ultraviolet	n. 紫外辐射 adj. 紫外线的
radioactive	adj. 放射性的
distinct	adj. 明显的; 截然不同的
discernible	adj. 可辨别的
invisible	adj. 看不见的
collision	n. 碰撞; 冲突
squash	v. 压扁 n. 壁球
fragment	n. 碎片 v. 碎裂
cataclysmic	adj. 剧变的; 灾难性的
overwhelming	adj. 压倒性的
despair	v. n. 绝望
desperate	adj. 绝望的; 极需要的
hopeless	adj. 无望的; 极差的
"""


class Command(BaseCommand):
    help = 'Import 刘洪波雅思真经 vocabulary book'

    def handle(self, *args, **options):
        entries = []
        for line in RAW.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t', 1)
            if len(parts) < 2:
                continue
            word_text = parts[0].strip()
            definition = parts[1].strip()
            if word_text and definition:
                entries.append((word_text, definition))

        self.stdout.write(f'Parsed {len(entries)} word entries')

        with transaction.atomic():
            book, created = VocabBook.objects.get_or_create(
                name='刘洪波雅思真经',
                defaults={'description': '刘洪波雅思真经词汇'},
            )
            action = 'Created' if created else 'Found existing'
            self.stdout.write(f'{action} book: {book.name}')

            new_words = 0
            new_memberships = 0

            for order, (word_text, raw_def) in enumerate(entries, 1):
                definitions, grammar = parse_definition(raw_def)

                word_obj, w_created = Word.objects.get_or_create(
                    word=word_text,
                    defaults={
                        'grammar': grammar,
                        'definitions': definitions,
                    },
                )
                if w_created:
                    new_words += 1

                _, m_created = WordBookMembership.objects.get_or_create(
                    word=word_obj,
                    book=book,
                    defaults={'order': order},
                )
                if m_created:
                    new_memberships += 1

            book.word_count = book.memberships.count()
            book.save(update_fields=['word_count'])

        self.stdout.write(self.style.SUCCESS(
            f'Done! new_words={new_words} new_memberships={new_memberships} '
            f'book_total={book.word_count}'
        ))
