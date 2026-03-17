"""Import chapters 9-22 for 刘洪波雅思真经."""
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
medium	n. 媒体 adj. 中等的
press	n. 新闻界; 出版社
journalist	n. 记者
critic	n. 批评家
commentator	n. 评论员; 解说员
exponent	n. 阐述者, 倡导者
announcer	n. 广播员, 播音员
correspondent	n. 通讯员; 记者
messenger	n. 邮递员, 信使
editor	n. 编辑, 主编
typist	n. 打字员
handout	n. 传单; 讲义
leaflet	n. 传单 v. 散发传单
propaganda	n. 宣传, 鼓吹
publish	v. 出版; 公布
disseminate	v. 散布, 传播
foresee	v. 预见, 预知
anticipate	v. 预期, 预料
expect	v. 预料, 预期
await	v. 等候, 期待
pastime	n. 娱乐, 消遣
entertain	v. 娱乐; 招待
recreation	n. 休闲, 娱乐
amuse	v. 逗乐
gossip	n. 闲聊; 流言蜚语
rumour	n. 谣言, 传闻
consensus	n. 共识, 一致的意见
festival	n. 节日
feast	n. 宴会; 宗教节日
programme	n. 节目; 方案
rehearsal	n. 排练
perform	v. 表演; 执行
imitate	v. 模仿
mimic	v. 模仿; 戏仿
simulate	v. 模拟; 假装
circus	n. 马戏团
magic	n. 魔术; 魔法
drama	n. 戏剧
concert	n. 音乐会
symphony	n. 交响乐
orchestra	n. 管弦乐队
ballet	n. 芭蕾舞
opera	n. 歌剧
comedy	n. 喜剧
tragedy	n. 悲剧
animation	n. 动画片
film	n. 影片; 胶卷
movie	n. 电影
artist	n. 艺术家
craftsman	n. 工匠
painter	n. 画家
role	n. 角色; 作用
scene	n. 景色; 现场; 镜头
stage	n. 舞台; 阶段
gallery	n. 美术馆
exhibition	n. 展览会
aesthetic	adj. 审美的 n. 审美观
collect	v. 收集; 收藏
select	v. 选择 adj. 精选的
opt	v. 选择
photograph	n. 照片
portrait	n. 肖像
painting	n. 油画; 绘画
sculpture	n. 雕塑
draw	v. 画; 拉; 拔出
depict	v. 描述; 描绘
describe	v. 描述, 形容
carve	v. 雕刻; 切下
improvise	v. 即兴创作
musical	adj. 音乐的
classical	adj. 古典的
jazz	n. 爵士乐
rock	n. 摇滚乐; 岩石
hip-hop	n. 嘻哈文化
pop	n. 流行音乐
lyric	n. 抒情词 adj. 抒情的
band	n. 乐队; 带子; 范围
solo	n. 独奏 adj. 单独的
melody	n. 乐曲; 旋律
rhythm	n. 节奏, 韵律
tone	n. 音色; 声调; 腔调
tune	n. 曲调 v. 调试
disc	n. 唱片; 磁盘
piano	n. 钢琴
violin	n. 小提琴
cello	n. 大提琴
guitar	n. 吉他
harmonica	n. 口琴
trumpet	n. 喇叭, 小号
drum	n. 鼓
flute	n. 长笛
competition	n. 竞赛; 比赛
tournament	n. 锦标赛
Olympic	adj. 奥林匹克的
sponsor	n. 赞助人 v. 赞助
patron	n. 赞助人; 顾客
athlete	n. 运动员
champion	n. 冠军 v. 支持
spectator	n. 观众
volunteer	n. 志愿者 v. 自愿做
famous	adj. 著名的
well-known	adj. 众所周知的
energetic	adj. 充满活力的
vigorous	adj. 活跃的; 积极的
stadium	n. 体育场
gym	n. 体育馆; 健身房
training	n. 训练; 培训
exercise	n. 锻炼; 习题 v. 锻炼
indoor	adj. 室内的
outdoor	adj. 室外的
yoga	n. 瑜伽
sprawl	v. 伸开四肢; 蔓延
stretch	v. 伸展; 伸长
strain	v. 拉紧; 拉伤 n. 张力
chess	n. 国际象棋
badminton	n. 羽毛球
golf	n. 高尔夫球
billiards	n. 台球
soccer	n. 足球
tennis	n. 网球
volleyball	n. 排球
hockey	n. 曲棍球; 冰球
goal	n. 球门; 进球; 目的
bat	n. 球拍, 球棒
racket	n. 球拍
kick	v. n. 踢
knock	v. 敲, 击
flip	v. 掷; 快速翻动
pitch	v. 投, 掷 n. 球场
throw	v. 投, 掷, 抛
toss	v. 扔, 抛
slide	v. 滑动 n. 滑行
slip	v. 滑跤; 滑落
glide	v. 滑动, 掠过
tumble	v. 摔倒, 滚下
ski	v. 滑雪 n. 滑雪板
skate	v. 滑冰
cycling	n. 骑自行车运动
dive	v. 跳水; 潜水
drift	v. 飘移, 漂流
jump	v. 跳; 暴涨
leap	v. 跳, 跃
plunge	v. 纵身投入; 猛跌
hop	v. 单脚跳; 齐足跳
bounce	v. 反弹, 弹起
tent	n. 帐篷
camp	n. 营地
picnic	n. 野餐
hunt	n. 打猎 v. 猎取; 搜寻
race	n. 赛跑; 种族
marathon	n. 马拉松
pedestrian	n. 步行者, 行人
pace	n. 步速; 节奏
step	n. 步伐; 步骤
excursion	n. 远足, 短程旅行
cruise	v. 乘船浏览
trip	n. 旅行 v. 绊倒
vacation	n. 假期
hike	v. n. 徒步旅行
jog	v. 慢跑
stride	v. 大步走
wander	v. 漫步; 走神
linger	v. 逗留, 流连
lag	v. 落后 n. 时间差
climb	v. 攀登, 爬
pull	v. 拉, 拖
drag	v. 拖, 拉, 拽
bend	v. 俯身; 使弯曲
bow	n. v. 鞠躬
stuff	n. 东西; 原料
item	n. 一件商品; 条款
merchandise	n. 商品
souvenir	n. 纪念品
artefact	n. 人造物品; 手工艺品
material	n. 材料 adj. 物质的
raw	adj. 天然的; 未加工的
crude	adj. 天然的; 粗糙的 n. 原油
necessity	n. 必需品
outfit	n. 全套服装 v. 装备
kit	n. 成套工具
utensil	n. 器皿
garbage	n. 垃圾
rubbish	n. 垃圾
trash	n. 垃圾
recycle	v. 回收利用
reuse	v. 再次利用
litter	n. 垃圾 v. 乱丢
waste	n. 废物; 浪费 v. 浪费
junk	n. 废物
landfill	n. 垃圾填埋
sewerage	n. 排水系统
detergent	n. 洗涤剂
lotion	n. 润肤乳
shampoo	n. 洗发剂
soap	n. 肥皂
tub	n. 浴缸; 桶
plug	n. 塞子; 插头
tap	n. 龙头; 轻拍 v. 轻拍
pipe	n. 管子; 烟斗
tube	n. 管; 地铁
mop	n. 拖把 v. 用拖把擦
broom	n. 扫帚
sweep	v. 打扫; 掠过
mattress	n. 床垫
carpet	n. 地毯
rug	n. 小地毯
mat	n. 地毯, 地席
cushion	n. 软垫
pad	n. 衬垫; 便笺本
blanket	n. 毛毯
quilt	n. 被子
sheet	n. 被单; 一张纸
pillow	n. 枕头
sponge	n. 海绵
towel	n. 毛巾
staple	n. 订书钉; 主要部分
nail	n. 指甲; 钉子 v. 钉住
razor	n. 剃刀
shave	v. 剃须
fuse	n. 保险丝; 导火线 v. 融合
cable	n. 电缆; 缆绳
cord	n. 细绳, 粗线
strand	n. 股; 海滨
match	n. 火柴; 比赛 v. 匹配
candle	n. 蜡烛
wax	n. 蜡
portfolio	n. 文件夹
paperback	n. 简装书
pamphlet	n. 小册子
tissue	n. 面巾纸; 薄纸
cover	n. 封面; 盖子
duplicate	v. 重复 n. 副本
memorandum	n. 备忘录
stationery	n. 文具
glue	n. 胶水
ink	n. 墨水
rubber	n. 橡胶; 橡皮擦
scissors	n. 剪刀
shear	v. 剪 n. 大剪刀
edge	n. 边; 刀口
rim	n. 边缘, 外缘
element	n. 元素; 基本部分
factor	n. 因素
section	n. 部分; 章; 节
tag	n. 标签
label	n. 标签
badge	n. 徽章; 标志
bolt	n. 螺栓; 插销
knob	n. 把手; 旋钮
handle	n. 把手 v. 处理
shutter	n. 百叶窗; 快门
curtain	n. 窗帘; 幕布
pane	n. 窗玻璃
opacity	n. 不透明性
jar	n. 罐子; 震动
barrel	n. 桶
bucket	n. 桶
pail	n. 桶, 提桶
phone	n. 电话
bell	n. 钟; 铃
camera	n. 照相机
portable	adj. 便携式的
spotlight	n. 聚光灯
lantern	n. 灯笼
bulb	n. 电灯泡
flashlight	n. 手电筒
refrigerator	n. 冰箱
fridge	n. 冰箱
vacuum	n. 真空; 吸尘器
fan	n. 扇子
switch	n. 开关
hurdle	n. 栏架; 跨栏赛跑
fence	n. 栅栏; 围栏
pedal	n. 踏板
shelf	n. 架子
ladder	n. 梯子
lift	v. 提, 抬 n. 电梯
stool	n. 凳子
drawer	n. 抽屉
umbrella	n. 雨伞
raincoat	n. 雨衣
dredge	n. 挖泥船 v. 挖掘
can	n. 罐头 v. 装罐保存
mill	n. 磨坊 v. 碾碎
forge	n. 锻铁炉 v. 锻造; 伪造
alloy	n. 合金
metal	n. 金属
iron	n. 铁; 熨斗 v. 熨
lead	n. 铅
brass	n. 黄铜
bronze	n. 青铜
cement	n. 水泥 v. 黏结
lime	n. 石灰
plaster	n. 灰泥; 熟石膏
leather	n. 皮革
plastic	n. 塑料
fibre	n. 纤维
fabric	n. 织物, 布料
knit	v. 编织
weave	v. 编织; 编造
canvas	n. 帆布
linen	n. 亚麻布
cotton	n. 棉花; 棉布
nylon	n. 尼龙
lumber	n. 木材
wooden	adj. 木制的
mine	n. 矿; 地雷
pit	n. 深坑; 煤矿
fuel	n. 燃料 v. 加燃料
lubricate	v. 润滑
diamond	n. 钻石; 菱形
crystal	n. 水晶; 晶体
inferior	adj. 差的; 下级的
counterfeit	adj. 假冒的 v. 伪造
fake	adj. 假冒的 n. 假货
fragile	adj. 易碎的; 脆弱的
miniature	adj. 微型的 n. 缩微模型
available	adj. 可用的; 可获得的
durable	adj. 耐用的; 持久的
fashion	n. 时尚 v. 制作
style	n. 风格; 时尚
trend	n. 趋势, 倾向
tendency	n. 趋势
popularity	n. 流行
vogue	n. 流行
prevail	v. 流行; 获胜
model	n. 模型; 模特 v. 模仿
icon	n. 偶像; 图标
idol	n. 偶像
luxury	n. 奢侈; 奢侈品
extravagant	adj. 奢侈的; 过分的
jewellery	n. 珠宝, 首饰
jewel	n. 宝石
gem	n. 宝石; 珍品
jade	n. 玉石, 翡翠
adorn	v. 装饰, 装扮
ornament	n. 装饰品 v. 装饰
embellish	v. 修饰
embroider	v. 刺绣; 渲染
hairdressing	n. 美发, 理发
pigment	n. 色素; 颜料
dye	v. 染色 n. 染料
masquerade	v. 化装; 假扮 n. 化装舞会
veil	n. 面纱; 遮蔽物
costume	n. 戏服; 服装
fascinate	v. 迷住, 深深吸引
decent	adj. 得体的; 尚好的
exquisite	adj. 精致的; 雅致的
grace	n. 优美, 优雅
elegance	n. 典雅, 文雅
perfect	adj. 完美的
appearance	n. 外貌; 出现
cosmetics	n. 化妆品
make-up	n. 化妆品
handsome	adj. 英俊的; 数量大的
charming	adj. 迷人的
pretty	adj. 漂亮的 adv. 相当
beautiful	adj. 美丽的
ugly	adj. 丑陋的
dress	n. 衣服; 连衣裙
clothe	v. 给…穿衣
uniform	n. 制服 adj. 一致的
garment	n. 衣服
laundry	n. 洗衣店; 要洗的衣服
wardrobe	n. 衣柜; 全部服装
overall	n. 罩衣 adj. 全面的
overcoat	n. 大衣
robe	n. 长袍; 浴袍
gown	n. 长外衣; 礼服
sweater	n. 毛衣
jacket	n. 夹克衫
skirt	n. 裙子
jeans	n. 牛仔裤
trousers	n. 裤子
clasp	n. 搭扣 v. 扣住
button	n. 纽扣; 按钮
glove	n. 手套
hat	n. 帽子
cap	n. 帽子
brim	n. 边缘; 帽檐
scarf	n. 围巾
handkerchief	n. 手帕
purse	n. 钱包; 小手提包
wallet	n. 钱包
vest	n. 马甲; 汗衫
wrap	n. 披肩 v. 包, 裹
cloak	n. 披风, 斗篷
collar	n. 衣领; 项圈
sleeve	n. 袖子
sock	n. 短袜
stocking	n. 长筒袜
slipper	n. 拖鞋
boot	n. 靴子
lace	n. 鞋带; 蕾丝
tailor	n. 裁缝 v. 专门制作
sew	v. 缝制
spin	v. 纺; 旋转
stitch	n. 针脚 v. 缝
needle	n. 针
pin	n. 别针 v. 别住
string	n. 线; 一串; 字符串
thread	n. 线; 螺纹
strap	n. 带子 v. 系
stripe	n. 条纹
ribbon	n. 缎带, 丝带
belt	n. 腰带; 地带
chain	n. 链子; 连锁店
bracelet	n. 手镯
necklace	n. 项链
bead	n. 珠子; 小滴
textile	n. 纺织品 adj. 纺织的
velvet	n. 丝绒
wool	n. 毛线; 毛
patch	n. 补丁 v. 补缀
rag	n. 破布
shabby	adj. 破旧的
tight	adj. 紧的
colour	n. 颜色; 颜料
white	adj. 白色的
yellow	adj. 黄色的
brown	adj. 棕色的
grey	adj. 灰色的
pink	adj. 粉红色的
purple	adj. 紫色的
tan	n. 棕黄色 adj. 棕黄色的
fade	v. 褪色; 逐渐消失
stain	v. 染污 n. 污渍
blot	n. 污点
figure	n. 身材; 重要人物; 数字
slender	adj. 苗条的; 微弱的
slight	adj. 纤细的; 轻微的
food	n. 食物
diet	n. 日常饮食; 节食
appetite	n. 食欲; 胃口
treat	v. 请客; 对待; 治疗
cater	v. 提供饮食; 满足需要
provision	n. 供应; 预备
edible	adj. 可以吃的
recipe	n. 食谱; 秘诀
restaurant	n. 餐馆
refectory	n. 食堂, 餐厅
cafeteria	n. 自助餐厅
buffet	n. 自助餐
barbecue	n. 烧烤 v. 烧烤
supper	n. 晚餐; 夜宵
banquet	n. 宴会
refreshment	n. 茶点; 点心
snack	n. 小吃, 零食
appetiser	n. 开胃小吃
cuisine	n. 菜肴; 烹饪
menu	n. 菜单
order	n. 订单 v. 点餐; 命令
takeaway	n. 外卖
chef	n. 厨师
gourmet	n. 美食家
vegetarian	n. 素食者 adj. 素食的
cutlery	n. 餐具
silver	n. 银; 银器 adj. 银的
ceramic	n. 陶瓷制品 adj. 陶瓷的
porcelain	n. 瓷器
bowl	n. 碗
dish	n. 盘, 碟; 菜肴
saucer	n. 茶托, 茶碟
tray	n. 托盘
fork	n. 餐叉; 分岔处
knife	n. 刀
spoon	n. 调羹; 匙
glass	n. 玻璃杯; 玻璃
mug	n. 马克杯
kettle	n. 水壶
pan	n. 平底锅
pot	n. 锅; 壶
stove	n. 炉子
furnace	n. 熔炉
oven	n. 烤箱
tin	n. 罐头; 锡
lid	n. 盖子
drink	v. 喝; 喝酒 n. 饮料
beverage	n. 饮料
juice	n. 果汁
soda	n. 苏打水; 汽水
coffee	n. 咖啡
alcohol	n. 酒精, 酒
liquor	n. 烈性酒
whisky	n. 威士忌
brandy	n. 白兰地
drunk	adj. 醉的
tobacco	n. 烟草
cigarette	n. 香烟
sober	adj. 清醒的
vegetable	n. 蔬菜
tomato	n. 番茄
potato	n. 马铃薯
pea	n. 豌豆
bean	n. 豆
cucumber	n. 黄瓜
cabbage	n. 卷心菜
onion	n. 洋葱
mushroom	n. 蘑菇 v. 蘑菇状扩散
eggplant	n. 茄子
carrot	n. 胡萝卜
turnip	n. 芜菁
radish	n. 樱桃萝卜
peel	n. 皮 v. 剥皮
strip	v. 剥去 n. 条, 带
hull	n. 外壳; 船体 v. 剥壳
cherry	n. 樱桃
berry	n. 浆果
grape	n. 葡萄
papaya	n. 番木瓜
peach	n. 桃子
pear	n. 梨子
plum	n. 李子
orange	n. 橙子
melon	n. 甜瓜
lemon	n. 柠檬
kiwi	n. 猕猴桃
crop	n. 庄稼; 产量
corn	n. 玉米; 谷物
grain	n. 谷物; 颗粒
wheat	n. 小麦
reap	v. 收割; 收获
flour	n. 面粉
porridge	n. 麦片粥
paste	n. 面团; 糨糊
livestock	n. 家畜, 牲畜
chicken	n. 鸡
turkey	n. 火鸡
beef	n. 牛肉
pork	n. 猪肉
mutton	n. 羊肉
sausage	n. 香肠
fish	n. 鱼 v. 钓鱼
pond	n. 池塘
rod	n. 杆, 竿
dairy	n. 乳制品 adj. 乳制的
milk	n. 奶 v. 挤奶
yogurt	n. 酸奶
cream	n. 奶油
cheese	n. 奶酪
butter	n. 黄油
salad	n. 色拉
sandwich	n. 三明治
hamburger	n. 汉堡包
loaf	n. 一条面包 v. 闲逛
pie	n. 派, 馅饼
pizza	n. 比萨饼
pasta	n. 意大利面食
spaghetti	n. 意大利面条
soup	n. 汤
pudding	n. 布丁
biscuit	n. 饼干
jam	n. 果酱
nut	n. 坚果; 螺母
chocolate	n. 巧克力
ice cream	n. 冰激凌
vanilla	n. 香草 adj. 香草味的
mustard	n. 芥末
wasabi	n. 山葵
pepper	n. 柿子椒; 胡椒粉
ginger	n. 姜
garlic	n. 蒜
scallion	n. 葱
vinegar	n. 醋
salt	n. 盐
sugar	n. 糖
candy	n. 糖果
honey	n. 蜂蜜
flavour	n. 味道; 风格
sour	adj. 酸的
sweet	adj. 甜的; 愉快的
bitter	adj. 苦的; 痛苦的
spicy	adj. 辛辣的
delicious	adj. 美味的
yummy	adj. 美味的
tasty	adj. 美味的, 可口的
hunger	n. 饥饿; 渴望
thirsty	adj. 渴的; 渴望的
spice	n. 香料
sauce	n. 酱汁
ketchup	n. 番茄酱
perfume	n. 香味; 香水
ingredient	n. 原料; 因素
supplement	n. 营养补剂 v. 补充
digest	v. 消化; 理解
cook	v. 烹调 n. 厨师
bake	v. 烧烤
fry	v. 油煎
roast	v. 烤 n. 烤肉
toast	n. 烤面包片 v. 干杯; 烤
suck	v. 吮吸
swallow	v. 咽下, 吞下 n. 燕子
lick	v. 舔
chew	v. 咀嚼
gum	n. 口香糖; 树胶
soak	v. 浸泡; 使湿透
dip	v. 蘸, 浸
squeeze	v. 挤压
stir	v. 搅动; 行动
grind	v. 碾碎
slice	v. 切成薄片 n. 薄片
"""


class Command(BaseCommand):
    help = 'Import chapters 9-12 for 刘洪波雅思真经'

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
            existing_max = book.memberships.order_by('-order').values_list('order', flat=True).first() or 0
            new_words = new_memberships = 0

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
