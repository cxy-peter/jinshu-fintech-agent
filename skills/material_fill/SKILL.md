# 理财发行材料生成

输入：product_name、start、term_days、frequency_days、count；Pydantic Schema 在 jinshu/python_skills.py。

执行：参数验证 → 复用 jinshu.tools.issuance → 将排期与产品要素映射为 Word → 幂等命名输出 → 检索材料复核口径。

输出：排期行、Word文件名、SHA256、下载路径、待复核事项。来源方法为过往发行材料替换及报表自动化，本次改为合成数据个人原型；不是调用公司内部程序。

Loop允许改变检索词、top-k和审核过的回答模板；不改变产品期限、日历、模板事实或实际发行决定。
