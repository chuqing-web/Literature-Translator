from app.services.math_text import is_formula_like_text, sanitize_math_translation, soft_unwrap


def test_soft_unwrap_joins_pdf_word_wraps():
    src = "Index\nTerms—Cardiovascular\nimage\nsegmentation,"
    assert soft_unwrap(src) == "Index Terms—Cardiovascular image segmentation,"
    zh = "索引\n术语——心血管\n图像分割，"
    assert soft_unwrap(zh) == "索引术语——心血管图像分割，"


def test_soft_unwrap_keeps_paragraph_break():
    src = "First paragraph.\n\nSecond paragraph."
    assert soft_unwrap(src) == "First paragraph.\n\nSecond paragraph."


def test_soft_unwrap_keeps_link_list_breaks():
    src = (
        "Demo: https://sam2.metademolab.com\n"
        "Code: https://github.com/facebookresearch/sam2\n"
        "Website: https://ai.meta.com/sam2"
    )
    out = soft_unwrap(src)
    assert out.count("\n") == 2
    assert "Demo:" in out.split("\n")[0]
    assert "Code:" in out.split("\n")[1]


def test_soft_unwrap_restores_flattened_link_list():
    flat = (
        "演示：https://sam2.metademolab.com "
        "代码：https://github.com/facebookresearch/sam2 "
        "网站：https://ai.meta.com/sam2"
    )
    out = soft_unwrap(flat)
    assert out.count("\n") == 2
    assert out.split("\n")[0].startswith("演示")
    assert out.split("\n")[1].startswith("代码")
    assert out.split("\n")[2].startswith("网站")


def test_detects_equation_and_softmax():
    assert is_formula_like_text("at = softmax(QKT /")
    assert is_formula_like_text("x_{t+1} = Ax_t + Bu_t + w_t")
    assert is_formula_like_text("LDice = 1 −DSC = 1 −")


def test_detects_split_equation_tail():
    assert is_formula_like_text("pdk)V,\n(3)")
    assert is_formula_like_text("√d_k)V, (3)")
    assert is_formula_like_text("(3)")


def test_rejects_normal_prose():
    assert not is_formula_like_text(
        "State Space Models (SSM) describe systems in terms of their internal states."
    )
    assert not is_formula_like_text(
        "An encoder with these blocks is included in the complete U-Mamba network architecture."
    )


def test_sanitize_strips_invented_latex():
    src = "The fundamental form is denoted as follows:"
    zh = (
        "其基本形式如下：\n"
        "$$x_{t+1} = Ax_t + Bu_t + w_t$$\n"
        "其中 $x_t$ 为输入状态向量，$A$ 为状态转移矩阵。"
    )
    out = sanitize_math_translation(src, zh)
    assert "$$" not in out
    assert "$" not in out
    assert "状态转移矩阵" not in out
    assert "其基本形式如下" in out


def test_sanitize_unwraps_inline_and_unescapes():
    src = "For observation yt, calculated using the observation matrix C,"
    zh = "对于使用观测矩阵 $C$、直通矩阵 $D$ 以及观测噪声 $v\\_t$ 计算得到的观测值 $y\\_t$，"
    out = sanitize_math_translation(src, zh)
    assert "$" not in out
    assert "v_t" in out
    assert "y_t" in out
    assert "观测矩阵 C" in out


def test_sanitize_keeps_where_qkv_prose():
    src = (
        "where Q, K, and V are the query, key, and value matrices that "
        "are derived from the state vector xt, and dk is the dimension of the key vectors. "
        "This mechanism enables the model to effectively capture intricate dependencies."
    )
    zh = (
        "其中 Q、K 和 V 是由状态向量 x_t 导出的查询、键和值矩阵，"
        "d_k 为键向量的维度。该机制使模型能够通过关注输入序列中的相关成分，"
        "有效捕获复杂依赖关系。"
    )
    out = sanitize_math_translation(src, zh)
    assert "查询" in out
    assert "键向量" in out
    assert "复杂依赖" in out


def test_sanitize_keeps_intro_drops_fabricated_eq():
    src = "The selective attention mechanism can be represented as:"
    zh = "选择性注意力机制可表示为：\n$$a_t = softmax(QK^T / \\sqrt{d_k})V$$"
    out = sanitize_math_translation(src, zh)
    assert "可表示为" in out
    assert "softmax" not in out
    assert "$$" not in out


def test_sanitize_keeps_source_latex():
    src = "We minimize $\\mathcal{L} = \\sum_i x_i$."
    zh = "我们最小化 $\\mathcal{L} = \\sum_i x_i$。"
    assert sanitize_math_translation(src, zh) == zh


def test_detects_author_lines():
    from app.services.math_text import is_author_line_text

    assert is_author_line_text(
        "Ting Yu Tsai, Liangqiao Gui, Yineng Chen, Li Lin, Shu Hu, Connie W. Tsao, Xin Li, Shao Lin,"
    )
    assert is_author_line_text("Ming-Ching Chang∗, Hongtu Zhu, Xin Wang∗")
    assert not is_author_line_text(
        "Deep learning models have achieved significant success in segmenting cardiovascular structures."
    )
    assert not is_author_line_text("Department of Computer Science, Stanford University")
