"""内置深度学习知识库。

用于两种场景：

1. 未配置 LLM 时作为规则式回答的来源（离线可用）；
2. 配置 LLM 时作为检索上下文（简易 RAG）。

检索采用关键词命中打分，够用且无需向量库依赖。
"""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_LABEL = "DeepVision 内置知识库 · 深度学习基础"


@dataclass(frozen=True)
class KnowledgeEntry:
    id: str
    title: str
    keywords: tuple[str, ...]
    content: str


ENTRIES: tuple[KnowledgeEntry, ...] = (
    KnowledgeEntry(
        id="gradient",
        title="梯度消失与梯度爆炸",
        keywords=("梯度消失", "梯度爆炸", "消失", "爆炸", "gradient", "反向传播"),
        content=(
            "梯度消失 / 爆炸是深层网络训练时反向传播的问题。链式法则会逐层相乘梯度："
            "若每层梯度都小于 1，乘到浅层时趋近于 0（消失）；都大于 1 则指数放大（爆炸）。\n"
            "常见成因：Sigmoid / Tanh 在饱和区导数接近 0、权重初始化过大或过小、层数过深。\n"
            "对应办法：换用 ReLU 类激活函数、合理的权重初始化（如 He 初始化）、"
            "加入批归一化、使用残差连接，以及把学习率控制在合适范围。"
        ),
    ),
    KnowledgeEntry(
        id="overfit",
        title="过拟合与欠拟合",
        keywords=("过拟合", "欠拟合", "泛化", "验证集", "overfit"),
        content=(
            "过拟合指模型在训练集上表现好、在验证集上变差，说明它记住了噪声。"
            "典型信号是训练损失持续下降而验证损失开始上升。\n"
            "缓解手段：增加数据、减小网络容量、加入正则化（L2 / Dropout）、"
            "早停（在验证损失回升时停止）、以及做数据标准化。\n"
            "欠拟合则相反：训练损失本身降不下去，通常需要更大容量、更长训练或更高学习率。"
        ),
    ),
    KnowledgeEntry(
        id="learning-rate",
        title="学习率的选取",
        keywords=("学习率", "learning rate", "lr", "步长"),
        content=(
            "学习率决定每次参数更新的幅度。过大时损失剧烈震荡甚至发散（变成 NaN），"
            "过小时收敛极慢、容易停在平台区。\n"
            "经验起点：Adam 常用 1e-3，SGD 常用 1e-2 到 1e-1。"
            "判断方法：训练损失若在前几个 epoch 就变成 NaN，先降到原来的 1/10；"
            "若损失下降过于平缓，可适当放大。"
        ),
    ),
    KnowledgeEntry(
        id="activation",
        title="激活函数的选择",
        keywords=("激活函数", "relu", "sigmoid", "tanh", "非线性"),
        content=(
            "激活函数为网络引入非线性。没有激活函数，多层线性变换等价于一层。\n"
            "ReLU 计算快、缓解梯度消失，是隐藏层的默认选择；"
            "Sigmoid 输出在 0~1，适合二分类概率，但深层易饱和；"
            "Tanh 输出在 -1~1，比 Sigmoid 更居中，但仍会饱和。\n"
            "实践建议：隐藏层优先 ReLU，输出层的激活由任务决定（分类用 Softmax / Sigmoid）。"
        ),
    ),
    KnowledgeEntry(
        id="hidden-size",
        title="隐藏层数量与神经元规模",
        keywords=("隐藏层", "神经元", "层数", "units", "宽度", "深度"),
        content=(
            "隐藏层的宽度（每层神经元数）和深度（层数）共同决定表达能力。"
            "一个常用的经验是：第一层宽度不低于输入特征数的 1~2 倍。\n"
            "表格数据通常 1~3 个隐藏层就足够，层数过多反而更难训练、更易过拟合。\n"
            "从较小的网络开始，观察验证损失，再逐步加宽或加深。"
        ),
    ),
    KnowledgeEntry(
        id="dropout",
        title="Dropout 的作用",
        keywords=("dropout", "丢弃", "正则"),
        content=(
            "Dropout 在训练时按概率随机把一部分神经元输出置零，迫使网络不依赖个别神经元，"
            "从而降低过拟合。\n"
            "典型取值 0.2~0.5，只作用于隐藏层；预测时需要关闭"
            "（PyTorch 用 model.eval()，否则结果会不稳定）。"
        ),
    ),
    KnowledgeEntry(
        id="batchnorm",
        title="批归一化（BatchNorm）",
        keywords=("batchnorm", "批归一化", "归一化层", "bn"),
        content=(
            "批归一化在每个 mini-batch 上把该层输入重新标准化，再学习缩放与偏移。"
            "它让各层输入分布更稳定，允许更大的学习率并加快收敛。\n"
            "注意：BatchNorm 在训练和推理行为不同，推理要切换到 eval 模式。"
        ),
    ),
    KnowledgeEntry(
        id="loss",
        title="损失函数的选择",
        keywords=("损失函数", "交叉熵", "mse", "均方误差", "loss"),
        content=(
            "分类任务常用交叉熵（CrossEntropy），它配合 Softmax 输出概率分布，"
            "梯度性质更好；回归任务常用均方误差（MSE）。\n"
            "不要在分类任务上用 MSE：它对概率的惩罚过弱，收敛明显更慢。"
        ),
    ),
    KnowledgeEntry(
        id="split",
        title="训练集与验证集的划分",
        keywords=("验证集", "划分", "训练集", "测试集", "比例"),
        content=(
            "训练集用于更新参数，验证集用于观察泛化并做选择。"
            "常见比例是 8:2 或 7:3；数据很少时可以用交叉验证。\n"
            "关键点：标准化、编码等预处理统计量只能从训练集计算，否则验证结果会偏乐观。"
        ),
    ),
    KnowledgeEntry(
        id="normalize",
        title="特征标准化",
        keywords=("标准化", "归一化", "z-score", "缩放", "特征"),
        content=(
            "把数值特征缩放到相近量级（例如 z-score：减均值除标准差）能显著改善训练。"
            "否则量纲大的特征会主导梯度，导致收敛慢或不稳定。\n"
            "务必只用训练集统计量，再套用到验证集与预测数据上。"
        ),
    ),
    KnowledgeEntry(
        id="output-shape",
        title="输出层单元数与任务类型",
        keywords=("输出层", "单元数", "分类", "回归", "类别数"),
        content=(
            "分类任务的输出层单元数应等于类别数，配合交叉熵使用；"
            "回归任务的输出层通常只有 1 个单元，损失用 MSE。\n"
            "如果输出单元数与类别数不一致，训练会出现维度错误或结果无意义。"
        ),
    ),
    KnowledgeEntry(
        id="curve",
        title="如何看训练曲线",
        keywords=("曲线", "准确率", "loss 曲线", "指标", "收敛"),
        content=(
            "同时看训练损失与验证损失：两者都下降是健康状态；"
            "训练下降而验证回升是过拟合；两者都平稳不降可能是学习率过小或容量不足。\n"
            "准确率曲线建议与损失一起看——准确率在类别不平衡时容易给出乐观印象。"
        ),
    ),
    KnowledgeEntry(
        id="batchsize",
        title="Batch Size 的影响",
        keywords=("batch", "批大小", "mini-batch", "批次"),
        content=(
            "Batch 越大，梯度估计越稳定、吞吐更高，但泛化有时略差且内存占用更高；"
            "Batch 越小，噪声更大，反而可能帮助跳出局部区域。\n"
            "常见起点是 32 或 64。改变 batch 时通常需要同步调整学习率。"
        ),
    ),
    KnowledgeEntry(
        id="encode",
        title="类别特征编码",
        keywords=("独热", "one-hot", "编码", "类别特征", "字符串"),
        content=(
            "神经网络只接受数值，类别特征需要编码。"
            "取值互不相关的类别（如颜色）用独热编码；有序类别可以用整数编码。\n"
            "独热编码会让输入维度增加：k 个类别产生 k 维，"
            "所以画布中「输入层特征数」要按编码后的维度填写。"
        ),
    ),
)


def _score(entry: KnowledgeEntry, question: str) -> int:
    text = question.lower()
    score = 0
    for keyword in entry.keywords:
        if keyword.lower() in text:
            score += 3 if len(keyword) > 1 else 1
    if entry.title.lower() in text:
        score += 5
    return score


def search(question: str, limit: int = 3) -> list[KnowledgeEntry]:
    """按关键词命中排序返回最相关的条目。"""
    scored = [(_score(entry, question), entry) for entry in ENTRIES]
    scored.sort(key=lambda item: item[0], reverse=True)
    hits = [entry for score, entry in scored if score > 0]
    if not hits:
        # 没有命中时退回前两条，保证回答仍有来源
        return list(ENTRIES[:2])
    return hits[:limit]
