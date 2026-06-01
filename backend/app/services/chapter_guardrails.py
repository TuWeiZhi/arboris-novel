# AIMETA P=章节护栏_后置一致性检查|R=禁止角色检测_全知视角检测_登场协议检查_AI味检测_红线检查|NR=不含LLM调用|E=none|X=internal|A=检测_验证|D=re|S=none|RD=./README.ai
"""
ChapterGuardrails: 章节后置一致性检查服务

核心职责：
1. 检测正文中是否出现禁止角色的名字
2. 检测全知视角的 cue 词
3. 检测新角色登场是否符合协议
4. 检测 AI 味特征（禁用词、句式单一、口语化不足）
5. 检测红线问题（一票否决）
6. 输出违规列表，供自动修复使用
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class Violation:
    """违规记录"""
    type: str  # forbidden_name | omniscient_cue | sudden_familiarity | ai_taste | red_line
    severity: str  # high | medium | low
    description: str
    position: Optional[int] = None  # 违规位置（字符索引）
    context: Optional[str] = None  # 违规上下文（前后 50 字）


@dataclass
class GuardrailResult:
    """护栏检查结果"""
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    red_line_triggered: bool = False  # 红线一票否决

    def add_violation(self, violation: Violation):
        self.violations.append(violation)
        if violation.type == "red_line":
            self.red_line_triggered = True
        self.passed = False


class ChapterGuardrails:
    """
    章节护栏检查器。

    检查维度：
    A) ForbiddenNameMention：正文出现 forbidden_characters 中任意名字（高优先级）
    B) OmniscientCue：出现全知视角的 cue 词（中优先级）
    C) SuddenFamiliarity：新角色首次出现前 120 字内没有介绍痕迹（中优先级）
    D) AITaste：AI 味特征检测（禁用词、句式单一、口语化不足）
    E) RedLine：红线一票否决（反派降智、时间线错乱、战力崩坏等）
    """

    # 全知视角 cue 词列表
    OMNISCIENT_CUES = [
        r"与此同时",
        r"另一边",
        r"此时某地",
        r"殊不知",
        r"他并不知道",
        r"她并不知道",
        r"他们并不知道",
        r"如果他知道",
        r"如果她知道",
        r"在他不知道的地方",
        r"在她不知道的地方",
        r"远在.*的.*正在",
        r"而此刻.*却",
    ]

    # 介绍性词汇（用于检测角色登场是否有介绍）
    INTRO_INDICATORS = [
        r"看见",
        r"看到",
        r"注意到",
        r"发现",
        r"出现",
        r"走来",
        r"走进",
        r"站着",
        r"坐着",
        r"一个.*人",
        r"一位",
        r"陌生",
        r"不认识",
        r"第一次见",
        r"从未见过",
        r"身穿",
        r"穿着",
        r"长相",
        r"面容",
        r"身材",
        r"气质",
    ]

    # AI 味禁用词（高频 AI 生成特征词）
    AI_TASTE_BANNED_PHRASES = [
        # 结构性连接词（AI 最典型特征）
        "首先，", "其次，", "最后，", "第一，", "第二，", "第三，",
        "综上所述", "更关键的是", "值得注意的是", "不言而喻",
        "毋庸置疑", "显而易见", "由此可见", "总而言之",
        # 过度修饰词
        "不禁", "油然而生", "心中涌起一股", "深深地",
        "缓缓地说道", "淡淡地说道", "微微一笑",
        "嘴角微微上扬", "眼中闪过一丝", "心中暗想",
        # AI 式情绪标签
        "心中五味杂陈", "百感交集", "思绪万千",
        "内心深处", "灵魂深处", "骨子里",
        # AI 式总结句
        "这一刻", "此时此刻", "就这样",
        "不知不觉中", "恍惚间", "刹那间",
        # 过度正式的对话标签
        "郑重其事", "一本正经", "语重心长",
        "意味深长", "若有所思", "恍然大悟",
    ]

    # 红线检查项（一票否决）
    RED_LINE_PATTERNS = {
        "反派降智": [
            r"敌人.*竟然.*就这样",
            r"反派.*轻[易而].*放[过了]",
            r"对手.*呆.*愣.*不知所措",
        ],
        "机械降神": [
            r"就在这时.*突然出现.*一个.*[高手大能老者]",
            r"关键时刻.*神秘.*力量",
            r"危急关头.*不知名的.*相助",
        ],
        "主角双标": [
            r"他可以.*但别人不行",
            r"自己.*却要求别人",
        ],
    }

    # 句式结构前缀（用于检测句式单一性）
    SENTENCE_PREFIXES_PATTERN = re.compile(
        r"^(他|她|我|你|这|那|一|在|从|到|就|也|都|才|又|再|还|却|但|可|而|若|虽|即|便|纵|哪怕|虽然|但是|可是|然而|因此|所以|于是|不过|只是|如果|假如|倘若|即使)",
    )

    def __init__(self):
        self._omniscient_pattern = re.compile(
            "|".join(self.OMNISCIENT_CUES), re.IGNORECASE
        )
        self._intro_pattern = re.compile(
            "|".join(self.INTRO_INDICATORS), re.IGNORECASE
        )
        self._banned_pattern = re.compile(
            "|".join(re.escape(p) for p in self.AI_TASTE_BANNED_PHRASES)
        )

    def check(
        self,
        generated_text: str,
        forbidden_characters: List[str],
        allowed_new_characters: Optional[List[str]] = None,
        pov: Optional[str] = None,
    ) -> GuardrailResult:
        """
        执行护栏检查。

        Args:
            generated_text: 生成的章节正文
            forbidden_characters: 禁止出现的角色名列表
            allowed_new_characters: 本章允许登场的新角色列表
            pov: 本章视角角色名

        Returns:
            GuardrailResult: 检查结果
        """
        result = GuardrailResult(passed=True)

        # A) 检测禁止角色名
        self._check_forbidden_names(generated_text, forbidden_characters, result)

        # B) 检测全知视角 cue
        self._check_omniscient_cues(generated_text, result)

        # C) 检测新角色登场协议
        if allowed_new_characters:
            self._check_character_introduction(
                generated_text, allowed_new_characters, result
            )

        # D) 检测 AI 味特征
        self._check_ai_taste(generated_text, result)

        # E) 检测红线问题
        self._check_red_lines(generated_text, result)

        return result

    def _check_ai_taste(self, text: str, result: GuardrailResult):
        """
        AI 味预检（快速筛查，非最终判定）。

        注意：这只是第一道快速筛查，真正的 AI 味检测由 AI Review 的 LLM 完成。
        预检结果 severity 设为 low，不触发自动返工，仅作为 LLM 评审的参考信号。
        """
        flagged_phrases = []

        # D1) 禁用词预检（仅标记，不阻断）
        for match in self._banned_pattern.finditer(text):
            phrase = match.group()
            if phrase not in flagged_phrases:
                flagged_phrases.append(phrase)

        if flagged_phrases:
            result.add_violation(
                Violation(
                    type="ai_taste",
                    severity="low",  # 降级为 low，不触发返工
                    description=f"AI 味预检：发现 {len(flagged_phrases)} 个可疑词（{', '.join(flagged_phrases[:5])}{'...' if len(flagged_phrases) > 5 else ''}），待 LLM 评审确认",
                )
            )

        # D2) 句式单一性预检
        sentences = re.split(r"[。！？]", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) >= 5:
            prefixes = []
            for s in sentences:
                match = self.SENTENCE_PREFIXES_PATTERN.match(s)
                if match:
                    prefixes.append(match.group())
                else:
                    prefixes.append("")
            max_streak = 1
            streak = 1
            streak_prefix = ""
            for i in range(1, len(prefixes)):
                if prefixes[i] and prefixes[i] == prefixes[i - 1]:
                    streak += 1
                    if streak > max_streak:
                        max_streak = streak
                        streak_prefix = prefixes[i]
                else:
                    streak = 1
            if max_streak >= 4:
                result.add_violation(
                    Violation(
                        type="ai_taste",
                        severity="low",
                        description=f"AI 味预检：连续 {max_streak} 句以「{streak_prefix}」开头，句式单一",
                    )
                )

    def _check_red_lines(self, text: str, result: GuardrailResult):
        """检测红线问题（一票否决）"""
        for rule_name, patterns in self.RED_LINE_PATTERNS.items():
            for pattern_str in patterns:
                pattern = re.compile(pattern_str)
                match = pattern.search(text)
                if match:
                    pos = match.start()
                    context = self._extract_context(text, pos)
                    result.add_violation(
                        Violation(
                            type="red_line",
                            severity="high",
                            description=f"红线违规「{rule_name}」：{match.group()[:50]}",
                            position=pos,
                            context=context,
                        )
                    )

    def _check_forbidden_names(
        self, text: str, forbidden_characters: List[str], result: GuardrailResult
    ):
        """检测禁止角色名"""
        for name in forbidden_characters:
            if not name:
                continue
            # 使用正则进行精确匹配（避免部分匹配）
            pattern = re.compile(re.escape(name))
            for match in pattern.finditer(text):
                pos = match.start()
                context = self._extract_context(text, pos)
                result.add_violation(
                    Violation(
                        type="forbidden_name",
                        severity="high",
                        description=f"出现了禁止角色「{name}」的名字",
                        position=pos,
                        context=context,
                    )
                )

    def _check_omniscient_cues(self, text: str, result: GuardrailResult):
        """检测全知视角 cue 词"""
        for match in self._omniscient_pattern.finditer(text):
            pos = match.start()
            cue = match.group()
            context = self._extract_context(text, pos)
            result.add_violation(
                Violation(
                    type="omniscient_cue",
                    severity="medium",
                    description=f"出现全知视角 cue 词「{cue}」",
                    position=pos,
                    context=context,
                )
            )

    def _check_character_introduction(
        self, text: str, new_characters: List[str], result: GuardrailResult
    ):
        """检测新角色登场是否有介绍"""
        for name in new_characters:
            if not name:
                continue
            # 找到角色名首次出现的位置
            pattern = re.compile(re.escape(name))
            match = pattern.search(text)
            if not match:
                continue  # 角色未出现，不算违规

            pos = match.start()
            # 检查前 120 字是否有介绍性词汇
            intro_range = max(0, pos - 120)
            intro_text = text[intro_range:pos]
            
            if not self._intro_pattern.search(intro_text):
                context = self._extract_context(text, pos)
                result.add_violation(
                    Violation(
                        type="sudden_familiarity",
                        severity="medium",
                        description=f"新角色「{name}」首次出现前缺少介绍性描写",
                        position=pos,
                        context=context,
                    )
                )

    def _extract_context(self, text: str, pos: int, window: int = 50) -> str:
        """提取违规位置的上下文"""
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        return f"...{text[start:end]}..."

    def format_violations_for_rewrite(self, result: GuardrailResult) -> str:
        """
        将违规列表格式化为可供 rewrite prompt 使用的文本。
        按严重程度排序：red_line > high > medium > low
        """
        if result.passed:
            return ""

        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_violations = sorted(
            result.violations, key=lambda v: severity_order.get(v.severity, 99)
        )

        lines = ["检测到以下违规，需要修复："]
        if result.red_line_triggered:
            lines.append("⚠️ 存在一票否决级红线违规，必须优先处理！")
            lines.append("")
        for i, v in enumerate(sorted_violations, 1):
            tag = {"red_line": "🚫红线", "ai_taste": "🤖AI味", "forbidden_name": "⛔禁名", "omniscient_cue": "👁全知", "sudden_familiarity": "👤登场"}.get(v.type, v.type)
            lines.append(f"{i}. [{v.severity.upper()}][{tag}] {v.description}")
            if v.context:
                lines.append(f"   上下文：{v.context}")
        return "\n".join(lines)
