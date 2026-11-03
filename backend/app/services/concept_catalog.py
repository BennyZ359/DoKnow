"""Curated concept assertions, not generated lesson titles or inferred evidence."""


def entity(key, name, kind, description, example, reason, *aliases):
    return {"key": key, "name": name, "kind": kind, "description": description,
            "example": example, "learning_reason": reason, "aliases": list(aliases)}


def relation(source, kind, target, explanation):
    return {"source": source, "kind": kind, "target": target, "explanation": explanation}


E, R = entity, relation


def machine_learning():
    return {
        "focus": "machine-learning",
        "summary": "探索机器学习的概念、数学基础、算法与工具，以及它们之间的具体联系。",
        "entities": [
            E("machine-learning", "机器学习", "domain", "通过数据形成模型，并用模型对新输入作出预测或发现结构的研究领域。", "根据历史房屋数据预测新房屋的价格。", "理解整个领域中的任务、模型和评估如何联系。", "ML", "Machine Learning"),
            E("supervised", "监督学习", "concept", "使用包含输入和目标标签的样本学习输入到目标的映射。", "用带房价标签的房屋记录训练预测器。", "理解回归和分类的共同训练方式。", "Supervised Learning"),
            E("unsupervised", "无监督学习", "concept", "在没有指定目标标签的数据中发现结构。", "按消费行为把用户分为若干群体。", "区分有标签预测和数据结构发现。", "Unsupervised Learning"),
            E("regression", "回归", "concept", "以连续数值为预测目标的任务。", "预测价格为 85.6 万元。", "识别需要输出数值的学习任务。"),
            E("classification", "分类", "concept", "以离散类别为预测目标的任务。", "判断邮件属于正常邮件还是垃圾邮件。", "识别类别预测任务并选择相应评价方法。"),
            E("linear-regression", "线性回归", "method", "用特征的线性组合预测连续目标的模型。", "用面积与房龄的加权和预测价格。", "连接特征、参数、损失和优化。", "Linear Regression"),
            E("logistic-regression", "逻辑回归", "method", "把线性组合转换为概率的常用分类模型。", "估计一封邮件是垃圾邮件的概率。", "理解名称包含回归但用于分类的模型。", "Logistic Regression"),
            E("kmeans", "K-means", "method", "按与簇中心的距离反复分配样本和更新中心的聚类方法。", "将用户分成三个行为群体。", "认识无监督学习的具体算法。", "K均值"),
            E("feature", "特征", "concept", "供模型使用的输入变量或表示。", "房屋面积、房龄和地理位置。", "知道原始问题如何表示成模型输入。"),
            E("label", "标签", "concept", "监督学习中样本对应的已知目标值。", "房屋的成交价或邮件的人工分类。", "避免混淆输入变量和需要预测的答案。"),
            E("vector", "向量", "concept", "按顺序组织的一组数，可用于表示特征和参数。", "用 [面积, 房龄] 表示一套房屋。", "理解模型如何表示一个样本。"),
            E("matrix", "矩阵", "concept", "按行列排列的数值结构，可组织多条向量和表达线性变换。", "每一行是一套房屋，每一列是一项特征。", "理解批量计算和数据维度。"),
            E("linear-algebra", "线性代数", "domain", "研究向量、矩阵、线性方程与线性变换的数学分支。", "通过矩阵乘法批量计算预测结果。", "为模型表示和线性运算提供基础。"),
            E("probability", "概率", "concept", "用于描述事件不确定性的数学量。", "模型输出某邮件属于垃圾邮件的概率。", "理解概率预测、统计假设与不确定性。"),
            E("derivative", "导数", "concept", "描述函数值随一个变量变化的局部变化率。", "二次函数在某点的切线斜率。", "为理解参数变化如何影响损失打基础。"),
            E("gradient", "梯度", "concept", "多元函数各偏导数组成的向量，指向局部最陡上升方向。", "分别计算损失对各个模型参数的偏导。", "理解优化算法用什么信息更新参数。"),
            E("gradient-descent", "梯度下降", "method", "沿负梯度方向迭代更新参数以减小目标函数的方法。", "参数减去学习率乘以梯度。", "理解训练模型的常见优化过程。", "Gradient Descent", "GD"),
            E("loss", "损失函数", "concept", "将模型预测与训练目标之间的差异转换为优化目标的函数。", "用平方误差衡量数值预测与标签的偏差。", "明确模型训练正在减小什么量。", "Loss Function"),
            E("mse", "均方误差", "concept", "预测值与实际值之差的平方的平均值。", "将每套房屋价格预测误差平方后求平均。", "理解回归的一种常见损失与评价量。", "MSE"),
            E("cross-entropy", "交叉熵", "concept", "用于比较目标分布与预测概率分布的量，常用作分类损失。", "对模型赋给真实类别的低概率施加较大惩罚。", "理解概率分类中如何形成训练目标。"),
            E("learning-rate", "学习率", "concept", "控制参数每次更新步长的系数。", "把梯度乘以 0.01 后从参数中减去。", "解释训练发散或收敛缓慢的常见原因。"),
            E("overfitting", "过拟合", "concept", "模型过度适应训练样本而在新样本上表现较差的现象。", "训练误差很低，独立测试数据误差却很高。", "区分记住训练数据和获得可迁移规律。"),
            E("regularization", "正则化", "method", "通过约束或惩罚等方式限制模型拟合复杂度的方法。", "在损失中加入参数平方和惩罚。", "理解改善泛化的一种常见手段。"),
            E("generalization", "泛化能力", "concept", "模型在未参与训练的新样本上完成目标任务的能力。", "对新收集的房屋记录仍有合理预测误差。", "明确模型评价需要面向新数据。"),
            E("cross-validation", "交叉验证", "method", "在多组训练与验证划分上重复评估的方法。", "五折划分中轮流用一折做验证。", "理解模型选择中的验证流程。"),
            E("precision", "精确率", "concept", "在被预测为正类的样本中，真正正类所占的比例。", "被识别为垃圾邮件的邮件中有多少确实是垃圾邮件。", "区分误报与漏报对应的指标。", "Precision"),
            E("python", "Python", "tool", "用于编程、数据处理与机器学习实验的通用编程语言。", "编写训练脚本并读取评估结果。", "把概念落实为可运行的实验。"),
            E("numpy", "NumPy", "tool", "提供多维数组和数值运算的 Python 库。", "用二维数组保存特征矩阵并进行矩阵乘法。", "理解数值数据和批量运算的实际工具。"),
            E("sklearn", "scikit-learn", "tool", "提供常用机器学习模型、数据处理和评估接口的 Python 库。", "拟合线性回归模型并进行交叉验证。", "快速构建可比较的基线实验。", "sklearn"),
            E("housing", "房价预测", "application", "根据房屋特征估计连续价格的预测应用。", "以面积和房龄为输入，预测成交价。", "将回归知识应用到明确问题。"),
            E("spam", "垃圾邮件识别", "application", "根据邮件内容或统计特征区分邮件类别的应用。", "将一封新邮件标为垃圾邮件或正常邮件。", "理解分类模型与实际误判成本。"),
        ],
        "relations": [
            R("supervised", "part_of", "machine-learning", "监督学习是机器学习中的一种学习范式。"),
            R("unsupervised", "part_of", "machine-learning", "无监督学习研究没有目标标签时的数据结构。"),
            R("supervised", "contrasts", "unsupervised", "两者的重要区别是训练样本是否提供目标标签。"),
            R("supervised", "requires", "label", "监督训练需要已知目标值作为学习信号。"),
            R("supervised", "uses", "feature", "监督模型从输入特征预测标签。"),
            R("regression", "part_of", "supervised", "回归是监督学习中的连续目标预测任务。"),
            R("classification", "part_of", "supervised", "分类是监督学习中的类别预测任务。"),
            R("regression", "contrasts", "classification", "回归预测连续数值，分类预测离散类别。"),
            R("linear-regression", "applied_to", "regression", "线性回归用于连续数值预测。"),
            R("logistic-regression", "applied_to", "classification", "逻辑回归通常用于分类而不是连续数值回归。"),
            R("kmeans", "part_of", "unsupervised", "K-means 根据样本分布聚类，不以已知类别标签为训练目标。"),
            R("feature", "uses", "vector", "一个样本的多项数值特征可以组织成向量。"),
            R("vector", "part_of", "linear-algebra", "向量是线性代数研究的基本对象。"),
            R("matrix", "part_of", "linear-algebra", "矩阵用于表达线性变换和组织线性运算。"),
            R("matrix", "uses", "vector", "矩阵的行和列都可以看作向量。"),
            R("linear-regression", "requires", "vector", "线性模型的特征和权重常以向量表示。"),
            R("linear-regression", "requires", "matrix", "批量线性预测可以写成矩阵乘法。"),
            R("gradient", "requires", "derivative", "梯度由对多个变量的偏导数组成。"),
            R("gradient-descent", "requires", "gradient", "梯度下降使用梯度决定参数更新方向。"),
            R("gradient-descent", "uses", "learning-rate", "学习率缩放每次参数更新的步长。"),
            R("gradient-descent", "optimizes", "loss", "梯度下降以减小损失函数值为优化目标。"),
            R("linear-regression", "uses", "mse", "普通线性回归常以平方误差作为训练目标。"),
            R("mse", "is_a", "loss", "均方误差可以作为回归模型的损失函数。"),
            R("mse", "measures", "regression", "均方误差衡量连续值预测的平均平方偏差。"),
            R("cross-entropy", "is_a", "loss", "交叉熵可以作为概率分类模型的训练损失。"),
            R("cross-entropy", "requires", "probability", "交叉熵涉及对预测概率分布的计算。"),
            R("logistic-regression", "uses", "probability", "逻辑回归把线性输入转换为类别概率。"),
            R("logistic-regression", "uses", "cross-entropy", "二分类逻辑回归常使用二元交叉熵目标。"),
            R("linear-regression", "uses", "gradient-descent", "梯度下降是拟合线性回归参数的一种方法，并非唯一方法。"),
            R("regularization", "optimizes", "generalization", "恰当的正则化可帮助改善模型在新样本上的表现。"),
            R("regularization", "uses", "loss", "惩罚型正则化通过修改训练目标限制参数。"),
            R("overfitting", "contrasts", "generalization", "训练数据表现好不等于新数据表现好。"),
            R("overfitting", "part_of", "machine-learning", "过拟合是机器学习模型训练与评价中的核心问题。"),
            R("cross-validation", "measures", "generalization", "交叉验证提供模型在留出数据上的表现估计。"),
            R("precision", "measures", "classification", "精确率衡量分类预测中正类预测的准确程度。"),
            R("numpy", "requires", "python", "使用 NumPy 需要理解基本 Python 编程。"),
            R("numpy", "uses", "matrix", "二维数组可承载矩阵运算。"),
            R("sklearn", "requires", "python", "scikit-learn 提供 Python 模型与评估接口。"),
            R("sklearn", "uses", "numpy", "scikit-learn 的数值输入常使用 NumPy 数组。"),
            R("sklearn", "uses", "linear-regression", "scikit-learn 提供线性回归估计器。"),
            R("sklearn", "uses", "cross-validation", "scikit-learn 提供交叉验证工具。"),
            R("linear-regression", "applied_to", "housing", "房价预测可以使用线性回归建立基线。"),
            R("logistic-regression", "applied_to", "spam", "垃圾邮件分类可使用逻辑回归建立基线。"),
            R("housing", "uses", "feature", "房价预测使用面积、房龄等输入特征。"),
            R("spam", "uses", "precision", "邮件过滤需要检查被判为垃圾邮件的预测是否可靠。"),
        ],
    }


def software_graph(topic):
    agent = any(word in topic for word in ("agent", "智能体", "大模型"))
    web = any(word in topic for word in ("前端", "网页", "javascript", "vue", "react", "frontend"))
    root = "agent" if agent else "web" if web else "python"
    entities = [
        E("python", "Python", "tool", "可用于脚本、数据处理和应用开发的编程语言。", "编写读取文件并整理数据的程序。", "学习表达和执行计算任务的工具。"),
        E("function", "函数", "concept", "通过参数接收输入，并封装可调用行为的程序单元。", "定义 total(price, count) 返回总价。", "理解如何组织可复用计算。"),
        E("type", "数据类型", "concept", "规定数据值及其可用操作的类别。", "数字 3 可以相加，字符串 '3' 表示文本。", "避免类型混淆造成错误。"),
        E("object", "对象", "concept", "由状态与行为构成的程序抽象。", "用一个对象表示当前任务的名称和状态。", "理解复杂数据和行为如何组织。"),
        E("json", "JSON", "concept", "使用对象、数组和基本值表达结构化数据的文本格式。", "用 {\"name\":\"Lin\"} 传递姓名。", "理解接口如何传输结构化信息。"),
        E("http", "HTTP", "concept", "以请求和响应交换资源表示的应用层协议。", "请求服务器提供一份 JSON 数据。", "理解客户端与服务端的交互。"),
        E("api", "API", "concept", "软件组件向调用者提供功能的约定接口。", "调用函数或网络端点获取天气数据。", "理解工具、模型与应用之间的连接方式。"),
        E("exception", "异常处理", "method", "识别并处理程序执行中非正常情况的机制。", "文件不存在时给出提示而不是继续读取。", "让程序能够处理实际输入和失败。"),
    ]
    relations = [
        R("python", "uses", "function", "Python 程序可使用函数封装和复用逻辑。"),
        R("python", "uses", "type", "Python 的值具有数据类型。"),
        R("python", "uses", "object", "Python 采用对象模型组织值与行为。"),
        R("function", "requires", "type", "理解函数的输入和输出需要明确数据类型。"),
        R("json", "uses", "type", "JSON 定义了对象、数组、字符串、数值等值类型。"),
        R("api", "uses", "http", "网络 API 可以通过 HTTP 请求和响应提供服务。"),
        R("api", "uses", "json", "网络 API 常使用 JSON 表达请求和响应数据。"),
        R("exception", "applied_to", "api", "API 调用需要处理超时、错误响应和解析失败。"),
        R("function", "part_of", "object", "对象的方法是与对象关联的可调用行为。"),
    ]
    if agent:
        entities += [
            E("agent", "AI Agent", "domain", "结合模型决策、工具和状态执行目标任务的系统。", "查找材料、提取证据并完成整理任务。", "理解模型如何与行动流程结合。", "智能体"),
            E("llm", "大语言模型", "tool", "对语言及相关表示进行生成和理解的模型。", "根据上下文提出下一次工具调用。", "理解智能体的推理与生成来源及局限。", "LLM"),
            E("tool-call", "工具调用", "method", "按约定参数调用外部能力并返回结果的机制。", "调用只读搜索工具并把结果交回模型。", "使智能体能够与外部信息或系统交互。"),
            E("state", "任务状态", "concept", "当前目标、执行历史和中间结果的表示。", "记录已搜索资料和待处理问题。", "理解多步骤任务如何保持上下文。"),
            E("prompt", "提示词", "concept", "向模型传递任务、上下文和输出约束的输入。", "要求从材料提取结论并标明出处。", "明确模型当前要完成的职责。"),
            E("rag", "检索增强生成", "method", "在生成前检索相关材料并作为上下文提供给模型。", "检索本地文档片段后生成带来源的回答。", "连接已有知识和模型输出。", "RAG"),
            E("retrieval", "信息检索", "method", "从资料集合中找出与查询相关的内容。", "按关键词和语义匹配查找文档片段。", "理解检索结果如何支撑回答。"),
            E("evaluation", "任务评测", "method", "使用明确任务与结果标准检查系统表现的方法。", "检查回答是否有出处、任务是否按要求完成。", "用可检查结果评估智能体能力。"),
        ]
        relations += [R("agent", "uses", "llm", "智能体可使用语言模型作出下一步决策。"), R("agent", "uses", "tool-call", "工具调用使智能体能够执行外部操作。"), R("agent", "uses", "state", "任务状态保存多步骤执行所需上下文。"), R("llm", "uses", "prompt", "模型通过提示输入获得任务和上下文。"), R("tool-call", "uses", "api", "工具通过明确接口接收参数并返回结果。"), R("tool-call", "requires", "json", "结构化工具参数需要遵守约定数据格式。"), R("agent", "requires", "python", "本示例用 Python 组织模型调用和执行循环。"), R("rag", "uses", "retrieval", "RAG 先取回相关材料，再用于生成。"), R("rag", "uses", "llm", "语言模型利用检索上下文生成回答。"), R("rag", "applied_to", "agent", "智能体可把检索增强生成作为资料问答能力。"), R("evaluation", "measures", "agent", "任务评测检查智能体在具体任务上的表现。"), R("exception", "applied_to", "tool-call", "工具执行需要处理错误、超时与无效返回。")]
    elif web:
        entities += [
            E("web", "前端开发", "domain", "构建用户在浏览器中使用的界面和交互。", "制作能够搜索和展示知识概念的页面。", "把内容、样式和行为组织成可用界面。"),
            E("html", "HTML", "tool", "用于表达网页内容及其语义结构的标记语言。", "用标题和表单标签组织页面内容。", "理解网页的结构与语义。"),
            E("css", "CSS", "tool", "用于描述文档呈现和布局的样式语言。", "用 Grid 排列页面区域。", "理解布局和视觉呈现的控制方式。"),
            E("js", "JavaScript", "tool", "用于编写网页等应用行为的编程语言。", "监听按钮点击并更新界面。", "实现与用户输入相关的逻辑。", "JS"),
            E("dom", "DOM", "concept", "文档内容可被程序访问和修改的对象表示。", "读取输入元素并更新一段文字。", "连接文档结构和程序操作。"),
            E("event", "事件", "concept", "对点击、输入等动作或状态变化的通知。", "点击节点时打开概念详情。", "理解交互如何触发程序行为。"),
            E("responsive", "响应式布局", "method", "根据视口和设备条件调整页面呈现的方法。", "手机上把两栏改成单栏。", "让界面适应不同屏幕。"),
        ]
        relations += [R("web", "uses", "html", "前端通过 HTML 组织文档内容。"), R("web", "uses", "css", "前端通过 CSS 控制视觉和布局。"), R("web", "uses", "js", "前端通过 JavaScript 表达交互逻辑。"), R("dom", "uses", "object", "DOM 以对象表示文档节点。"), R("js", "uses", "dom", "JavaScript 可通过 DOM 接口读取和修改文档。"), R("dom", "uses", "event", "DOM 节点可接收和处理事件。"), R("js", "uses", "function", "JavaScript 用函数定义行为和事件处理器。"), R("web", "uses", "api", "界面可通过 API 与服务端交换数据。"), R("responsive", "uses", "css", "响应式布局通常使用 CSS 布局与媒体查询。"), R("responsive", "applied_to", "web", "响应式布局帮助网页适应不同屏幕。")]
    else:
        entities += [
            E("list", "列表", "concept", "Python 中可变的有序容器。", "用列表保存多条交易记录。", "理解批量数据如何组织。"),
            E("dict", "字典", "concept", "Python 中通过键关联值的映射容器。", "用姓名和年龄两个键表示一条记录。", "理解按字段组织结构化数据。"),
            E("loop", "循环", "concept", "重复执行指定逻辑的控制结构。", "逐条计算列表中交易的金额。", "表达重复和批量处理行为。"),
            E("file", "文件读写", "method", "将外部文件内容读入程序或把结果写入文件。", "读取并更新一份 JSON 记账文件。", "使程序能够保存和恢复结果。"),
            E("testing", "测试", "method", "通过给定输入和检查结果来验证程序行为。", "验证零金额和无效金额的处理。", "用可重复检查发现逻辑错误。"),
        ]
        relations += [R("list", "is_a", "type", "列表是 Python 的一种容器类型。"), R("dict", "is_a", "type", "字典是 Python 的一种映射类型。"), R("loop", "uses", "list", "循环可以逐项处理列表元素。"), R("loop", "part_of", "python", "Python 提供 for 和 while 控制结构。"), R("file", "uses", "json", "结构化文件读写可采用 JSON 格式。"), R("file", "requires", "exception", "可靠的文件操作需要处理文件缺失和内容错误。"), R("testing", "applied_to", "function", "函数可通过输入与预期返回值进行测试。"), R("list", "contrasts", "dict", "列表主要按位置访问，字典按键访问。")]
    if web and not agent:
        entities = [item for item in entities if item["key"] != "python"]
        relations = [item for item in relations if "python" not in (item["source"], item["target"])]
    return {"focus": root, "summary": "以知识实体为中心，探索概念、方法、工具及其跨知识关系。", "entities": entities, "relations": relations}


def catalog_graph(topic):
    text = topic.casefold()
    if any(term in text for term in ("机器学习", "machine learning", "深度学习", "人工智能")):
        return machine_learning()
    if any(term in text for term in ("python", "前端", "网页", "javascript", "vue", "react", "frontend", "agent", "智能体", "大模型")):
        return software_graph(text)
    return None
